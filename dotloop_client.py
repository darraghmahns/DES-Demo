"""Dotloop API v2 Client for D.E.S.

Ported from doc_intel/backend/dotloop_client_enhanced.py with additions:
  - Auto token refresh on 401 responses
  - download_document() method for pulling PDFs from loops
  - Constructor accepts refresh_token, client_id, client_secret (env fallback)

Full v2 API support: Profiles, Loops, Loop Details, Participants,
Folders, Documents, Templates, Contacts, Loop-It.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)


class DotloopAPIError(Exception):
    """Custom exception for Dotloop API errors."""

    def __init__(self, status_code: int, message: str, response: dict | None = None):
        self.status_code = status_code
        self.message = message
        self.response = response or {}
        super().__init__(f"Dotloop API Error {status_code}: {message}")


class DotloopClient:
    """Enhanced Dotloop API v2 Client.

    Supports:
    - OAuth2 Bearer token authentication with auto-refresh
    - Loop management (create, update, get, find)
    - Loop details (property, financials, dates)
    - Participants management
    - Folder management
    - Document upload/download
    - Templates
    - Profiles
    - Rate limiting awareness
    """

    BASE_URL = "https://api-gateway.dotloop.com/public/v2"
    AUTH_URL = "https://auth.dotloop.com/oauth/token"

    def __init__(
        self,
        api_token: str | None = None,
        refresh_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
    ):
        """Initialise Dotloop client.

        Args:
            api_token: Bearer token. Falls back to DOTLOOP_API_TOKEN env var.
            refresh_token: Refresh token for auto-renewal. Falls back to
                DOTLOOP_REFRESH_TOKEN env var.
            client_id: OAuth client ID for token refresh. Falls back to
                DOTLOOP_CLIENT_ID env var.
            client_secret: OAuth client secret. Falls back to
                DOTLOOP_CLIENT_SECRET env var.
            base_url: Override API base URL (default: production).
            timeout: Request timeout in seconds.
        """
        self._api_token = api_token or os.getenv("DOTLOOP_API_TOKEN", "")
        self._refresh_token = refresh_token or os.getenv("DOTLOOP_REFRESH_TOKEN", "")
        self._client_id = client_id or os.getenv("DOTLOOP_CLIENT_ID", "")
        self._client_secret = client_secret or os.getenv("DOTLOOP_CLIENT_SECRET", "")

        if not self._api_token:
            raise ValueError(
                "Dotloop API token is required. Set DOTLOOP_API_TOKEN or pass api_token."
            )

        self._base_url = base_url or self.BASE_URL
        self._timeout = timeout

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
                "Authorization": f"Bearer {self._api_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )

    def _refresh_access_token(self) -> bool:
        """Attempt to refresh the access token using the refresh token.

        Returns True if refresh succeeded, False otherwise.
        """
        if not all([self._refresh_token, self._client_id, self._client_secret]):
            log.warning("Cannot refresh token: missing refresh_token, client_id, or client_secret")
            return False

        try:
            resp = httpx.post(
                self.AUTH_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                auth=(self._client_id, self._client_secret),
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()

            self._api_token = data["access_token"]
            if "refresh_token" in data:
                self._refresh_token = data["refresh_token"]

            # Rebuild client with new token
            self._client.close()
            self._client = self._build_client()

            log.info("Dotloop token refreshed successfully")
            return True

        except Exception as exc:
            log.error("Token refresh failed: %s", exc)
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
        return "dotloop"

    def _handle_response(
        self, resp: httpx.Response, *, _retry: bool = True
    ) -> dict[str, Any]:
        """Handle API response, extract rate limits, auto-refresh on 401.

        Raises:
            DotloopAPIError: If response status is not 2xx.
        """
        # Track rate limits
        self.rate_limit_remaining = resp.headers.get("X-RateLimit-Remaining")
        self.rate_limit_reset = resp.headers.get("X-RateLimit-Reset")

        # Auto-refresh on 401
        if resp.status_code == 401 and _retry:
            if self._refresh_access_token():
                # Retry the original request with new token
                new_resp = self._client.request(
                    resp.request.method,
                    str(resp.request.url).replace(self._base_url, ""),
                    content=resp.request.content or None,
                )
                return self._handle_response(new_resp, _retry=False)

        if resp.status_code == 429:
            raise DotloopAPIError(
                429,
                "Rate limit exceeded. Wait before retrying.",
                {"reset_ms": self.rate_limit_reset},
            )

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            try:
                error_data = resp.json()
            except Exception:
                error_data = {"detail": resp.text or str(e)}
            message = error_data.get("message") or error_data.get("detail") or resp.text or str(e)
            raise DotloopAPIError(
                resp.status_code,
                message,
                error_data,
            )

        if resp.status_code == 204:
            return {}

        return resp.json()

    # ==================================================================
    # PROFILE MANAGEMENT
    # ==================================================================

    def list_profiles(self) -> list[dict[str, Any]]:
        """List all profiles associated with the authenticated user."""
        resp = self._client.get("/profile")
        data = self._handle_response(resp)
        return data.get("data", [])

    def get_profile(self, profile_id: int) -> dict[str, Any]:
        """Get a specific profile by ID."""
        resp = self._client.get(f"/profile/{profile_id}")
        data = self._handle_response(resp)
        return data.get("data", {})

    # ==================================================================
    # LOOP MANAGEMENT
    # ==================================================================

    def list_loops(
        self,
        profile_id: int,
        batch_size: int = 20,
        batch_number: int = 1,
        sort: str = "updated:desc",
        filter_updated_min: str | None = None,
        transaction_type: str | None = None,
        include_details: bool = False,
    ) -> dict[str, Any]:
        """List loops for a profile with optional filtering.

        Args:
            profile_id: The profile ID.
            batch_size: Results per page (max 100).
            batch_number: Page number.
            sort: Sort order (e.g. "updated:desc", "created:asc").
            filter_updated_min: ISO timestamp for filtering.
            transaction_type: Filter by type (e.g. "PURCHASE_OFFER").
            include_details: Include full loop details.
        """
        params: dict[str, Any] = {
            "batch_size": min(batch_size, 100),
            "batch_number": batch_number,
            "sort": sort,
            "include_details": str(include_details).lower(),
        }
        if filter_updated_min:
            params["filter"] = f"updated_min={filter_updated_min}"
        if transaction_type:
            params["filter"] = f"transaction_type={transaction_type}"

        resp = self._client.get(f"/profile/{profile_id}/loop", params=params)
        return self._handle_response(resp)

    def find_existing_loop(
        self, profile_id: int, name: str
    ) -> dict[str, Any] | None:
        """Find a loop by name (searches recent loops)."""
        result = self.list_loops(profile_id, batch_size=50, sort="updated:desc")
        loops = result.get("data", [])
        for loop in loops:
            if loop.get("name") == name:
                return loop
        return None

    def get_loop(self, profile_id: int, loop_id: int) -> dict[str, Any]:
        """Get a specific loop by ID."""
        resp = self._client.get(f"/profile/{profile_id}/loop/{loop_id}")
        data = self._handle_response(resp)
        return data.get("data", {})

    def create_loop(
        self,
        profile_id: int,
        name: str,
        transaction_type: str = "PURCHASE_OFFER",
        status: str = "PRE_OFFER",
    ) -> dict[str, Any]:
        """Create a new loop.

        Args:
            profile_id: The profile ID.
            name: Loop name (usually property address or buyer name).
            transaction_type: Type of transaction.
            status: Initial status.
        """
        payload = {
            "name": name,
            "transactionType": transaction_type,
            "status": status,
        }
        resp = self._client.post(f"/profile/{profile_id}/loop", json=payload)
        data = self._handle_response(resp)
        return data.get("data", {})

    def update_loop(
        self,
        profile_id: int,
        loop_id: int,
        name: str | None = None,
        transaction_type: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing loop (partial updates supported)."""
        payload: dict[str, str] = {}
        if name is not None:
            payload["name"] = name
        if transaction_type is not None:
            payload["transactionType"] = transaction_type
        if status is not None:
            payload["status"] = status

        resp = self._client.patch(
            f"/profile/{profile_id}/loop/{loop_id}", json=payload
        )
        data = self._handle_response(resp)
        return data.get("data", {})

    # ==================================================================
    # LOOP-IT (SIMPLIFIED LOOP CREATION)
    # ==================================================================

    def loop_it(
        self,
        profile_id: int,
        name: str,
        transaction_type: str,
        status: str,
        street_name: str | None = None,
        street_number: str | None = None,
        city: str | None = None,
        state: str | None = None,
        zip_code: str | None = None,
        participants: list[dict] | None = None,
        template_id: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a loop with property and participants in one call (Loop-It API)."""
        payload: dict[str, Any] = {
            "name": name,
            "transactionType": transaction_type,
            "status": status,
        }
        if street_name:
            payload["streetName"] = street_name
        if street_number:
            payload["streetNumber"] = street_number
        if city:
            payload["city"] = city
        if state:
            payload["state"] = state
        if zip_code:
            payload["zipCode"] = zip_code
        if participants:
            payload["participants"] = participants
        if template_id:
            payload["templateId"] = template_id
        payload.update(kwargs)

        resp = self._client.post(
            f"/loop-it?profile_id={profile_id}", json=payload
        )
        data = self._handle_response(resp)
        return data.get("data", {})

    # ==================================================================
    # LOOP DETAILS
    # ==================================================================

    def get_loop_details(
        self, profile_id: int, loop_id: int
    ) -> dict[str, Any]:
        """Get detailed loop information (property, financials, dates, etc.)."""
        resp = self._client.get(
            f"/profile/{profile_id}/loop/{loop_id}/detail"
        )
        data = self._handle_response(resp)
        return data.get("data", {})

    @staticmethod
    def _strip_empty_values(details: dict[str, Any]) -> dict[str, Any]:
        """Remove empty string values from loop details sections.

        Dotloop's API rejects empty strings in many fields (e.g. prices,
        dates).  Only send fields that actually have data.
        """
        cleaned: dict[str, Any] = {}
        for section_name, section_data in details.items():
            if isinstance(section_data, dict):
                filtered = {
                    k: v for k, v in section_data.items()
                    if v is not None and v != ""
                }
                if filtered:
                    cleaned[section_name] = filtered
            else:
                cleaned[section_name] = section_data
        return cleaned

    def update_loop_details(
        self,
        profile_id: int,
        loop_id: int,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        """Update loop details (partial updates supported).

        Args:
            profile_id: The profile ID.
            loop_id: The loop ID.
            details: Dict with sections like::

                {
                    "Property Address": {"Street Name": "Main", ...},
                    "Financials": {"Purchase/Sale Price": "500000", ...},
                    "Contract Dates": {"Closing Date": "12/31/2024", ...},
                }

        Empty string values are automatically stripped before sending,
        since Dotloop rejects them with a 400.
        """
        cleaned = self._strip_empty_values(details)
        if not cleaned:
            return {}

        resp = self._client.patch(
            f"/profile/{profile_id}/loop/{loop_id}/detail", json=cleaned
        )
        data = self._handle_response(resp)
        return data.get("data", {})

    # ==================================================================
    # PARTICIPANTS
    # ==================================================================

    def list_participants(
        self, profile_id: int, loop_id: int
    ) -> list[dict[str, Any]]:
        """List all participants in a loop."""
        resp = self._client.get(
            f"/profile/{profile_id}/loop/{loop_id}/participant"
        )
        data = self._handle_response(resp)
        return data.get("data", [])

    def get_participant(
        self, profile_id: int, loop_id: int, participant_id: int
    ) -> dict[str, Any]:
        """Get a specific participant."""
        resp = self._client.get(
            f"/profile/{profile_id}/loop/{loop_id}/participant/{participant_id}"
        )
        data = self._handle_response(resp)
        return data.get("data", {})

    def add_participant(
        self,
        profile_id: int,
        loop_id: int,
        full_name: str,
        email: str,
        role: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Add a participant to a loop.

        Args:
            profile_id: The profile ID.
            loop_id: The loop ID.
            full_name: Participant's full name.
            email: Participant's email.
            role: Participant role (BUYER, SELLER, LISTING_AGENT, etc.).
            **kwargs: Optional fields (Phone, Company Name, etc.).
        """
        payload: dict[str, Any] = {
            "fullName": full_name,
            "email": email,
            "role": role,
        }
        payload.update(kwargs)

        resp = self._client.post(
            f"/profile/{profile_id}/loop/{loop_id}/participant", json=payload
        )
        data = self._handle_response(resp)
        return data.get("data", {})

    def update_participant(
        self,
        profile_id: int,
        loop_id: int,
        participant_id: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update a participant (partial updates supported)."""
        resp = self._client.patch(
            f"/profile/{profile_id}/loop/{loop_id}/participant/{participant_id}",
            json=kwargs,
        )
        data = self._handle_response(resp)
        return data.get("data", {})

    def delete_participant(
        self, profile_id: int, loop_id: int, participant_id: int
    ) -> None:
        """Delete a participant from a loop."""
        resp = self._client.delete(
            f"/profile/{profile_id}/loop/{loop_id}/participant/{participant_id}"
        )
        self._handle_response(resp)

    # ==================================================================
    # FOLDERS
    # ==================================================================

    def list_folders(
        self,
        profile_id: int,
        loop_id: int,
        include_documents: bool = False,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        """List all folders in a loop."""
        params = {
            "include_documents": str(include_documents).lower(),
            "include_archived": str(include_archived).lower(),
        }
        resp = self._client.get(
            f"/profile/{profile_id}/loop/{loop_id}/folder", params=params
        )
        data = self._handle_response(resp)
        return data.get("data", [])

    def get_folder(
        self,
        profile_id: int,
        loop_id: int,
        folder_id: int,
        include_documents: bool = True,
    ) -> dict[str, Any]:
        """Get a specific folder."""
        params = {"include_documents": str(include_documents).lower()}
        resp = self._client.get(
            f"/profile/{profile_id}/loop/{loop_id}/folder/{folder_id}",
            params=params,
        )
        data = self._handle_response(resp)
        return data.get("data", {})

    def create_folder(
        self, profile_id: int, loop_id: int, name: str
    ) -> dict[str, Any]:
        """Create a new folder in a loop."""
        resp = self._client.post(
            f"/profile/{profile_id}/loop/{loop_id}/folder", json={"name": name}
        )
        data = self._handle_response(resp)
        return data.get("data", {})

    def update_folder(
        self, profile_id: int, loop_id: int, folder_id: int, name: str
    ) -> dict[str, Any]:
        """Rename a folder."""
        resp = self._client.patch(
            f"/profile/{profile_id}/loop/{loop_id}/folder/{folder_id}",
            json={"name": name},
        )
        data = self._handle_response(resp)
        return data.get("data", {})

    def find_or_create_folder(
        self, profile_id: int, loop_id: int, folder_name: str
    ) -> dict[str, Any]:
        """Find a folder by name or create it if it doesn't exist."""
        folders = self.list_folders(profile_id, loop_id)
        for folder in folders:
            if folder.get("name") == folder_name:
                return folder
        return self.create_folder(profile_id, loop_id, folder_name)

    # ==================================================================
    # DOCUMENTS
    # ==================================================================

    def list_documents(
        self, profile_id: int, loop_id: int, folder_id: int
    ) -> list[dict[str, Any]]:
        """List all documents in a folder."""
        resp = self._client.get(
            f"/profile/{profile_id}/loop/{loop_id}/folder/{folder_id}/document"
        )
        data = self._handle_response(resp)
        return data.get("data", [])

    def get_document(
        self, profile_id: int, loop_id: int, folder_id: int, document_id: int
    ) -> dict[str, Any]:
        """Get document metadata."""
        resp = self._client.get(
            f"/profile/{profile_id}/loop/{loop_id}/folder/{folder_id}/document/{document_id}"
        )
        data = self._handle_response(resp)
        return data.get("data", {})

    def upload_document(
        self,
        profile_id: int,
        loop_id: int,
        folder_id: int,
        file_path: str,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        """Upload a document to a folder.

        Args:
            profile_id: The profile ID.
            loop_id: The loop ID.
            folder_id: The folder ID.
            file_path: Path to the PDF file.
            file_name: Optional custom filename.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_name is None:
            file_name = path.name

        with open(file_path, "rb") as f:
            files = {"file": (file_name, f, "application/pdf")}
            # Multipart upload needs a separate client without JSON content-type
            upload_client = httpx.Client(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_token}",
                    "Accept": "application/json",
                },
                timeout=self._timeout,
            )
            try:
                resp = upload_client.post(
                    f"/profile/{profile_id}/loop/{loop_id}/folder/{folder_id}/document",
                    files=files,
                )
                data = self._handle_response(resp)
                return data.get("data", {})
            finally:
                upload_client.close()

    def download_document(
        self,
        profile_id: int,
        loop_id: int,
        folder_id: int,
        document_id: int,
    ) -> bytes:
        """Download a document's PDF bytes from Dotloop.

        Args:
            profile_id: The profile ID.
            loop_id: The loop ID.
            folder_id: The folder ID.
            document_id: The document ID.

        Returns:
            Raw PDF bytes.

        Raises:
            DotloopAPIError: If the download fails.
        """
        url = (
            f"/profile/{profile_id}/loop/{loop_id}"
            f"/folder/{folder_id}/document/{document_id}"
        )
        resp = self._client.get(url, headers={"Accept": "application/pdf"})

        # Track rate limits
        self.rate_limit_remaining = resp.headers.get("X-RateLimit-Remaining")
        self.rate_limit_reset = resp.headers.get("X-RateLimit-Reset")

        if resp.status_code == 401 and self._refresh_access_token():
            resp = self._client.get(url, headers={"Accept": "application/pdf"})

        if resp.status_code != 200:
            try:
                error_data = resp.json()
            except Exception:
                error_data = {"detail": resp.text[:200]}
            raise DotloopAPIError(
                resp.status_code,
                error_data.get("detail", f"Download failed ({resp.status_code})"),
                error_data,
            )

        return resp.content

    # ==================================================================
    # TEMPLATES
    # ==================================================================

    def list_templates(self, profile_id: int) -> list[dict[str, Any]]:
        """List all loop templates for a profile."""
        resp = self._client.get(f"/profile/{profile_id}/loop-template")
        data = self._handle_response(resp)
        return data.get("data", [])

    def get_template(
        self, profile_id: int, template_id: int
    ) -> dict[str, Any]:
        """Get a specific template."""
        resp = self._client.get(
            f"/profile/{profile_id}/loop-template/{template_id}"
        )
        data = self._handle_response(resp)
        return data.get("data", {})

    # ==================================================================
    # CONTACTS
    # ==================================================================

    def list_contacts(
        self, batch_size: int = 20, batch_number: int = 1
    ) -> dict[str, Any]:
        """List all contacts in the user's directory."""
        params = {
            "batch_size": min(batch_size, 100),
            "batch_number": batch_number,
        }
        resp = self._client.get("/contact", params=params)
        return self._handle_response(resp)

    def get_contact(self, contact_id: int) -> dict[str, Any]:
        """Get a specific contact."""
        resp = self._client.get(f"/contact/{contact_id}")
        data = self._handle_response(resp)
        return data.get("data", {})

    def create_contact(self, **kwargs: Any) -> dict[str, Any]:
        """Create a new contact.

        Args:
            **kwargs: firstName, lastName, email, phone, address, city, state,
                      zipCode, etc.
        """
        resp = self._client.post("/contact", json=kwargs)
        data = self._handle_response(resp)
        return data.get("data", {})
