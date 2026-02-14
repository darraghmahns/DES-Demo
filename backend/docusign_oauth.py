#!/usr/bin/env python3
"""OAuth2 authentication flow for DocuSign.

Run this standalone script to obtain access and refresh tokens:

    python docusign_oauth.py

Prerequisites:
  1. Add DOCUSIGN_CLIENT_ID and DOCUSIGN_CLIENT_SECRET to .env
  2. In your DocuSign app settings, add this redirect URI:
     http://localhost:8098/callback
"""

from __future__ import annotations

import os
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode

import httpx
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("DOCUSIGN_CLIENT_ID")
CLIENT_SECRET = os.getenv("DOCUSIGN_CLIENT_SECRET")
AUTH_SERVER = os.getenv("DOCUSIGN_AUTH_SERVER", "account-d.docusign.com")
CALLBACK_PORT = 8098  # Avoid conflict with Dotloop (8099) and uvicorn (8000)
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

# Stores the authorization code from the callback
auth_code: str | None = None


class CallbackHandler(BaseHTTPRequestHandler):
    """Handle the OAuth callback from DocuSign."""

    def do_GET(self):
        global auth_code

        query = urlparse(self.path).query
        params = parse_qs(query)

        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            html = """
                <html>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: green;">DocuSign Authorization Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            error = params.get("error", ["Unknown error"])[0]
            error_desc = params.get("error_description", [""])[0]
            html = f"""
                <html>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: red;">Authorization Failed</h1>
                    <p>Error: {error}</p>
                    <p>{error_desc}</p>
                </body>
                </html>
            """
            self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress request logging


def get_access_token() -> str | None:
    """Run the full OAuth2 authorization code flow for DocuSign."""

    if not CLIENT_ID:
        print("ERROR: DOCUSIGN_CLIENT_ID not found")
        print("   Add it to .env and try again.")
        return None

    if not CLIENT_SECRET:
        print("ERROR: DOCUSIGN_CLIENT_SECRET not found")
        print("   Generate a secret key in your DocuSign app settings,")
        print("   then add it to .env as DOCUSIGN_CLIENT_SECRET.")
        return None

    print("=" * 60)
    print("DOCUSIGN OAUTH2 AUTHENTICATION")
    print("=" * 60)
    print()

    # Step 1: Build authorization URL
    auth_params = urlencode({
        "response_type": "code",
        "scope": "signature",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
    })
    auth_url = f"https://{AUTH_SERVER}/oauth/auth?{auth_params}"

    print("Step 1: Opening browser for authorization...")
    print(f"   If browser doesn't open, visit: {auth_url}")
    print()

    webbrowser.open(auth_url)

    # Step 2: Wait for callback
    print("Step 2: Waiting for authorization callback...")
    print(f"   (Local server running on port {CALLBACK_PORT})")
    print()

    server = HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    server.handle_request()  # Handle one request then stop

    if not auth_code:
        print("Failed to get authorization code")
        return None

    print("Authorization code received!")
    print()

    # Step 3: Exchange code for tokens
    print("Step 3: Exchanging code for access token...")

    try:
        response = httpx.post(
            f"https://{AUTH_SERVER}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": REDIRECT_URI,
            },
            auth=(CLIENT_ID, CLIENT_SECRET),
        )
        response.raise_for_status()
        token_data = response.json()

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")

        print("Access token received!")
        print()

        # Step 4: Call userinfo to discover account_id
        print("Step 4: Discovering account info...")

        userinfo_resp = httpx.get(
            f"https://{AUTH_SERVER}/oauth/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15.0,
        )
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()

        account_id = None
        base_uri = None
        accounts = userinfo.get("accounts", [])
        for acct in accounts:
            if acct.get("is_default"):
                account_id = acct["account_id"]
                base_uri = acct.get("base_uri", "")
                break
        if not account_id and accounts:
            account_id = accounts[0]["account_id"]
            base_uri = accounts[0].get("base_uri", "")

        user_name = userinfo.get("name", "Unknown")
        user_email = userinfo.get("email", "Unknown")

        print(f"   User: {user_name} ({user_email})")
        print(f"   Account ID: {account_id}")
        if base_uri:
            print(f"   Base URI: {base_uri}")
        print()

        print("=" * 60)
        print("SUCCESS! Add these to .env:")
        print("=" * 60)
        print()
        print(f"DOCUSIGN_ACCESS_TOKEN={access_token}")
        print(f"DOCUSIGN_REFRESH_TOKEN={refresh_token}")
        if account_id:
            print(f"DOCUSIGN_ACCOUNT_ID={account_id}")
        if base_uri:
            print(f"DOCUSIGN_BASE_URL={base_uri}/restapi")
        print()
        if expires_in:
            print(f"Note: Token expires in {expires_in} seconds (~{expires_in // 3600} hours)")
        print()

        # Offer to update .env automatically
        update_env = input("Update .env file automatically? (y/n): ").lower()
        if update_env == "y":
            env_path = os.path.join(os.path.dirname(__file__), ".env")
            with open(env_path, "r") as f:
                env_content = f.read()

            # Update or add each token
            token_updates = {
                "DOCUSIGN_ACCESS_TOKEN": access_token,
                "DOCUSIGN_REFRESH_TOKEN": refresh_token,
            }
            if account_id:
                token_updates["DOCUSIGN_ACCOUNT_ID"] = account_id
            if base_uri:
                token_updates["DOCUSIGN_BASE_URL"] = f"{base_uri}/restapi"

            for key, value in token_updates.items():
                if f"{key}=" in env_content:
                    lines = env_content.split("\n")
                    new_lines = []
                    for line in lines:
                        if line.startswith(f"{key}="):
                            new_lines.append(f"{key}={value}")
                        else:
                            new_lines.append(line)
                    env_content = "\n".join(new_lines)
                else:
                    env_content = env_content.rstrip("\n") + f"\n{key}={value}\n"

            with open(env_path, "w") as f:
                f.write(env_content)

            print(".env file updated!")
            print()

        return access_token

    except httpx.HTTPError as e:
        print(f"Failed to get access token: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"   Response: {e.response.text}")
        return None


if __name__ == "__main__":
    get_access_token()
