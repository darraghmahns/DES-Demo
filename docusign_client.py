"""DocuSign eSignature REST API v2.1 client.

Layer 1 of the 3-layer integration pattern (see README.md).
Thin httpx wrapper with Bearer auth, auto token refresh on 401, and rate limit tracking.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


class DocuSignAPIError(Exception):
    """Raised when the DocuSign API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str, response: Any = None):
        self.status_code = status_code
        self.message = message
        self.response = response
        super().__init__(f"DocuSign API {status_code}: {message}")


class DocuSignClient:
    """Low-level DocuSign eSignature REST API v2.1 client."""

    DEFAULT_AUTH_SERVER = "account-d.docusign.com"
    DEFAULT_BASE_URL = "https://demo.docusign.net/restapi"

    def __init__(
        self,
        access_token: str | None = None,
        refresh_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        account_id: str | None = None,
        base_url: str | None = None,
        auth_server: str | None = None,
        timeout: float = 30.0,
    ):
        self._access_token = access_token or os.getenv("DOCUSIGN_ACCESS_TOKEN", "")
        self._refresh_token = refresh_token or os.getenv("DOCUSIGN_REFRESH_TOKEN", "")
        self._client_id = client_id or os.getenv("DOCUSIGN_CLIENT_ID", "")
        self._client_secret = client_secret or os.getenv("DOCUSIGN_CLIENT_SECRET", "")
        self._account_id = account_id or os.getenv("DOCUSIGN_ACCOUNT_ID", "")
        self._auth_server = auth_server or os.getenv("DOCUSIGN_AUTH_SERVER", self.DEFAULT_AUTH_SERVER)
        self._base_url = base_url or os.getenv("DOCUSIGN_BASE_URL", self.DEFAULT_BASE_URL)
        self._timeout = timeout

        if not self._access_token:
            raise ValueError(
                "DocuSign access token is required. Set DOCUSIGN_ACCESS_TOKEN or pass access_token."
            )

        self._client = self._build_client()

        # Rate limit tracking
        self.rate_limit_remaining: str | None = None
        self.rate_limit_reset: str | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )

    def _refresh_access_token(self) -> bool:
        """Attempt to refresh the access token using refresh token or JWT."""
        # Try refresh_token grant first
        if all([self._refresh_token, self._client_id, self._client_secret]):
            try:
                resp = httpx.post(
                    f"https://{self._auth_server}/oauth/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                    },
                    auth=(self._client_id, self._client_secret),
                    timeout=15.0,
                )
                resp.raise_for_status()
                data = resp.json()

                self._access_token = data["access_token"]
                if "refresh_token" in data:
                    self._refresh_token = data["refresh_token"]

                self._client.close()
                self._client = self._build_client()

                # Persist refreshed tokens
                try:
                    from docusign_connector import set_oauth_tokens
                    set_oauth_tokens(
                        access_token=self._access_token,
                        refresh_token=self._refresh_token,
                    )
                except ImportError:
                    pass

                log.info("DocuSign token refreshed via refresh_token")
                return True

            except Exception as exc:
                log.warning("Refresh token grant failed: %s — trying JWT", exc)

        # Fallback to JWT grant
        try:
            from docusign_connector import _obtain_jwt_token
            token = _obtain_jwt_token()
            if token:
                self._access_token = token
                self._client.close()
                self._client = self._build_client()
                log.info("DocuSign token refreshed via JWT")
                return True
        except ImportError:
            pass

        log.error("Cannot refresh token: no refresh_token and JWT unavailable")
        return False

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    @property
    def name(self) -> str:
        return "docusign"

    def _handle_response(
        self, resp: httpx.Response, *, _retry: bool = True
    ) -> dict[str, Any]:
        """Handle API response, extract rate limits, auto-refresh on 401."""
        self.rate_limit_remaining = resp.headers.get("X-RateLimit-Remaining")
        self.rate_limit_reset = resp.headers.get("X-RateLimit-Reset")

        if resp.status_code == 401 and _retry:
            if self._refresh_access_token():
                new_resp = self._client.request(
                    resp.request.method,
                    str(resp.request.url).replace(self._base_url, ""),
                    content=resp.request.content or None,
                )
                return self._handle_response(new_resp, _retry=False)

        if resp.status_code == 429:
            raise DocuSignAPIError(
                429,
                "Rate limit exceeded. Wait before retrying.",
                {"reset": self.rate_limit_reset},
            )

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            try:
                error_data = resp.json()
            except Exception:
                error_data = {"detail": resp.text or str(e)}
            message = (
                error_data.get("message")
                or error_data.get("errorCode")
                or error_data.get("detail")
                or resp.text
                or str(e)
            )
            raise DocuSignAPIError(resp.status_code, message, error_data)

        if resp.status_code == 204:
            return {}

        return resp.json()

    def _account_path(self, path: str) -> str:
        """Build an account-scoped API path."""
        return f"/v2.1/accounts/{self._account_id}{path}"

    # ==================================================================
    # USER INFO (account discovery)
    # ==================================================================

    def get_user_info(self) -> dict[str, Any]:
        """Call /oauth/userinfo to discover account_id and base_uri.

        This uses the auth server, not the API server.
        """
        resp = httpx.get(
            f"https://{self._auth_server}/oauth/userinfo",
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=15.0,
        )
        if resp.status_code != 200:
            raise DocuSignAPIError(resp.status_code, "Failed to get user info", resp.text)
        return resp.json()

    def discover_account_id(self) -> str:
        """Discover and set account_id from userinfo endpoint."""
        info = self.get_user_info()
        accounts = info.get("accounts", [])
        if not accounts:
            raise DocuSignAPIError(400, "No accounts found for this user", info)
        # Prefer the default account
        for acct in accounts:
            if acct.get("is_default"):
                self._account_id = acct["account_id"]
                base_uri = acct.get("base_uri", "")
                if base_uri:
                    self._base_url = f"{base_uri}/restapi"
                    self._client.close()
                    self._client = self._build_client()
                return self._account_id
        # Fallback to first account
        self._account_id = accounts[0]["account_id"]
        return self._account_id

    # ==================================================================
    # ENVELOPES
    # ==================================================================

    def list_envelopes(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        status: str | None = None,
        count: int = 25,
        start_position: int = 0,
        order_by: str = "last_modified",
        order: str = "desc",
        include: str | None = None,
        search_text: str | None = None,
    ) -> dict[str, Any]:
        """List envelopes for the account.

        Args:
            from_date: Required by DocuSign. ISO 8601 start date.
                       Defaults to 30 days ago if not provided.
            status: Filter by status (e.g. 'completed', 'sent', 'created').
            count: Number of results (default 25).
            include: Comma-separated: 'recipients', 'custom_fields', 'documents'.
        """
        if not from_date:
            from datetime import datetime, timezone, timedelta
            from_date = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()

        params: dict[str, Any] = {
            "from_date": from_date,
            "count": str(count),
            "start_position": str(start_position),
            "order_by": order_by,
            "order": order,
        }
        if to_date:
            params["to_date"] = to_date
        if status:
            params["status"] = status
        if include:
            params["include"] = include
        if search_text:
            params["search_text"] = search_text

        resp = self._client.get(self._account_path("/envelopes"), params=params)
        return self._handle_response(resp)

    def get_envelope(
        self, envelope_id: str, include: str | None = None
    ) -> dict[str, Any]:
        """Get envelope details."""
        params = {}
        if include:
            params["include"] = include
        resp = self._client.get(
            self._account_path(f"/envelopes/{envelope_id}"), params=params
        )
        return self._handle_response(resp)

    def create_envelope(
        self,
        email_subject: str,
        status: str = "created",
        documents: list[dict] | None = None,
        recipients: dict | None = None,
        custom_fields: dict | None = None,
        event_notification: dict | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a new envelope.

        Args:
            email_subject: Subject line for the envelope email.
            status: 'created' (draft) or 'sent' (send immediately).
            documents: List of document dicts with documentId, name, documentBase64.
            recipients: Dict with 'signers', 'carbonCopies', etc.
            custom_fields: Dict with 'textCustomFields' list.
            event_notification: Webhook config for this envelope.
        """
        payload: dict[str, Any] = {
            "emailSubject": email_subject,
            "status": status,
        }
        if documents:
            payload["documents"] = documents
        if recipients:
            payload["recipients"] = recipients
        if custom_fields:
            payload["customFields"] = custom_fields
        if event_notification:
            payload["eventNotification"] = event_notification
        payload.update(kwargs)

        resp = self._client.post(self._account_path("/envelopes"), json=payload)
        return self._handle_response(resp)

    def void_envelope(self, envelope_id: str, reason: str = "Voided") -> dict[str, Any]:
        """Void an in-process envelope (must be in 'sent' or 'delivered' state)."""
        payload = {"status": "voided", "voidedReason": reason}
        resp = self._client.put(
            self._account_path(f"/envelopes/{envelope_id}"), json=payload
        )
        return self._handle_response(resp)

    def delete_envelope(self, envelope_id: str) -> dict[str, Any]:
        """Delete a draft envelope (must be in 'created' state)."""
        resp = self._client.delete(
            self._account_path(f"/envelopes/{envelope_id}")
        )
        return self._handle_response(resp)

    def get_envelope(self, envelope_id: str) -> dict[str, Any]:
        """Get envelope details including status."""
        resp = self._client.get(
            self._account_path(f"/envelopes/{envelope_id}")
        )
        return self._handle_response(resp)

    # ==================================================================
    # DOCUMENTS
    # ==================================================================

    def list_documents(self, envelope_id: str) -> dict[str, Any]:
        """List documents in an envelope."""
        resp = self._client.get(
            self._account_path(f"/envelopes/{envelope_id}/documents")
        )
        return self._handle_response(resp)

    def download_document(self, envelope_id: str, document_id: str) -> bytes:
        """Download a document as PDF bytes.

        Args:
            envelope_id: The envelope ID.
            document_id: Numeric ID, or 'combined', 'certificate', 'archive'.
        """
        url = self._account_path(f"/envelopes/{envelope_id}/documents/{document_id}")
        resp = self._client.get(url, headers={"Accept": "application/pdf"})

        self.rate_limit_remaining = resp.headers.get("X-RateLimit-Remaining")
        self.rate_limit_reset = resp.headers.get("X-RateLimit-Reset")

        if resp.status_code == 401 and self._refresh_access_token():
            resp = self._client.get(url, headers={"Accept": "application/pdf"})

        if resp.status_code != 200:
            try:
                error_data = resp.json()
            except Exception:
                error_data = {"detail": resp.text[:200]}
            raise DocuSignAPIError(
                resp.status_code,
                error_data.get("message", f"Download failed ({resp.status_code})"),
                error_data,
            )

        return resp.content

    def download_combined(self, envelope_id: str) -> bytes:
        """Download all documents in an envelope as a single combined PDF."""
        return self.download_document(envelope_id, "combined")

    # ==================================================================
    # RECIPIENTS
    # ==================================================================

    def list_recipients(self, envelope_id: str) -> dict[str, Any]:
        """List all recipients for an envelope."""
        resp = self._client.get(
            self._account_path(f"/envelopes/{envelope_id}/recipients")
        )
        return self._handle_response(resp)

    def add_recipients(
        self,
        envelope_id: str,
        signers: list[dict] | None = None,
        carbon_copies: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Add recipients to an envelope.

        Args:
            envelope_id: The envelope ID.
            signers: List of signer dicts with name, email, recipientId, routingOrder.
            carbon_copies: List of CC recipient dicts.
        """
        payload: dict[str, Any] = {}
        if signers:
            payload["signers"] = signers
        if carbon_copies:
            payload["carbonCopies"] = carbon_copies

        resp = self._client.post(
            self._account_path(f"/envelopes/{envelope_id}/recipients"),
            json=payload,
        )
        return self._handle_response(resp)

    # ==================================================================
    # CUSTOM FIELDS
    # ==================================================================

    def get_custom_fields(self, envelope_id: str) -> dict[str, Any]:
        """Get envelope custom fields."""
        resp = self._client.get(
            self._account_path(f"/envelopes/{envelope_id}/custom_fields")
        )
        return self._handle_response(resp)

    def update_custom_fields(
        self, envelope_id: str, text_fields: list[dict]
    ) -> dict[str, Any]:
        """Update envelope custom fields.

        Args:
            text_fields: List of dicts with 'name', 'value', optional 'fieldId'.
        """
        payload = {"textCustomFields": text_fields}
        resp = self._client.put(
            self._account_path(f"/envelopes/{envelope_id}/custom_fields"),
            json=payload,
        )
        return self._handle_response(resp)
