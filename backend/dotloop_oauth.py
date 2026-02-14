#!/usr/bin/env python3
"""OAuth2 authentication flow for Dotloop.

Run this standalone script to obtain access and refresh tokens:

    python dotloop_oauth.py

Prerequisites:
  1. Add DOTLOOP_CLIENT_ID and DOTLOOP_CLIENT_SECRET to demo/.env
  2. Make sure your Dotloop app's redirect URI includes:
     http://localhost:8099/callback
"""

from __future__ import annotations

import os
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import httpx
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("DOTLOOP_CLIENT_ID")
CLIENT_SECRET = os.getenv("DOTLOOP_CLIENT_SECRET")
CALLBACK_PORT = 8099  # Avoid conflict with uvicorn on 8000
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

# Stores the authorization code from the callback
auth_code: str | None = None


class CallbackHandler(BaseHTTPRequestHandler):
    """Handle the OAuth callback from Dotloop."""

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
                    <h1 style="color: green;">Authorization Successful!</h1>
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
            html = f"""
                <html>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: red;">Authorization Failed</h1>
                    <p>Error: {error}</p>
                </body>
                </html>
            """
            self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress request logging


def get_access_token() -> str | None:
    """Run the full OAuth2 authorization code flow."""

    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: DOTLOOP_CLIENT_ID and DOTLOOP_CLIENT_SECRET not found")
        print("   Add them to demo/.env and try again.")
        return None

    print("=" * 60)
    print("DOTLOOP OAUTH2 AUTHENTICATION")
    print("=" * 60)
    print()

    # Step 1: Build authorization URL
    auth_url = (
        f"https://auth.dotloop.com/oauth/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )

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
            "https://auth.dotloop.com/oauth/token",
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
        print("=" * 60)
        print("SUCCESS! Add these to demo/.env:")
        print("=" * 60)
        print()
        print(f"DOTLOOP_API_TOKEN={access_token}")
        print(f"DOTLOOP_REFRESH_TOKEN={refresh_token}")
        print()
        print(f"Note: Token expires in {expires_in} seconds (~{expires_in // 3600} hours)")
        print()

        # Offer to update .env automatically
        update_env = input("Update demo/.env file automatically? (y/n): ").lower()
        if update_env == "y":
            env_path = os.path.join(os.path.dirname(__file__), ".env")
            with open(env_path, "r") as f:
                env_content = f.read()

            if "DOTLOOP_API_TOKEN=" in env_content:
                lines = env_content.split("\n")
                new_lines = []
                for line in lines:
                    if line.startswith("DOTLOOP_API_TOKEN="):
                        new_lines.append(f"DOTLOOP_API_TOKEN={access_token}")
                    elif line.startswith("DOTLOOP_REFRESH_TOKEN="):
                        continue  # Skip old refresh token line
                    else:
                        new_lines.append(line)

                # Insert refresh token after API token
                for i, line in enumerate(new_lines):
                    if line.startswith("DOTLOOP_API_TOKEN="):
                        new_lines.insert(i + 1, f"DOTLOOP_REFRESH_TOKEN={refresh_token}")
                        break

                env_content = "\n".join(new_lines)
            else:
                env_content += f"\nDOTLOOP_API_TOKEN={access_token}\n"
                env_content += f"DOTLOOP_REFRESH_TOKEN={refresh_token}\n"

            with open(env_path, "w") as f:
                f.write(env_content)

            print(".env file updated!")
            print()

        print("Now run: python test_dotloop.py")
        return access_token

    except httpx.HTTPError as e:
        print(f"Failed to get access token: {e}")
        if hasattr(e, "response"):
            print(f"   Response: {e.response.text}")
        return None


if __name__ == "__main__":
    get_access_token()
