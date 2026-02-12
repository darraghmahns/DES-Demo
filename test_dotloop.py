#!/usr/bin/env python3
"""Quick diagnostic script to verify Dotloop API connectivity.

Usage:
    python test_dotloop.py

Checks:
  1. Environment variables are set
  2. API token is valid (lists profiles)
  3. Profile ID exists and is accessible
  4. Lists recent loops
  5. Shows rate limit status
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    print("=" * 60)
    print("DOTLOOP API DIAGNOSTIC")
    print("=" * 60)
    print()

    # --- Check env vars ---
    token = os.getenv("DOTLOOP_API_TOKEN")
    profile_id = os.getenv("DOTLOOP_PROFILE_ID")
    client_id = os.getenv("DOTLOOP_CLIENT_ID")
    client_secret = os.getenv("DOTLOOP_CLIENT_SECRET")
    refresh_token = os.getenv("DOTLOOP_REFRESH_TOKEN")

    print("Environment Variables:")
    print(f"  DOTLOOP_API_TOKEN:      {'set' if token else 'MISSING'}")
    print(f"  DOTLOOP_REFRESH_TOKEN:  {'set' if refresh_token else 'MISSING'}")
    print(f"  DOTLOOP_CLIENT_ID:      {'set' if client_id else 'MISSING'}")
    print(f"  DOTLOOP_CLIENT_SECRET:  {'set' if client_secret else 'MISSING'}")
    print(f"  DOTLOOP_PROFILE_ID:     {profile_id or 'MISSING'}")
    print()

    if not token:
        print("ERROR: DOTLOOP_API_TOKEN not set. Run dotloop_oauth.py first.")
        sys.exit(1)

    # --- Test connection ---
    from dotloop_client import DotloopClient, DotloopAPIError

    try:
        client = DotloopClient()
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    with client:
        # List profiles
        print("1. Listing profiles...")
        try:
            profiles = client.list_profiles()
            for p in profiles:
                marker = " <-- active" if str(p.get("id")) == profile_id else ""
                print(f"   Profile {p.get('id')}: {p.get('name', 'unnamed')}{marker}")
            print(f"   Found {len(profiles)} profile(s)")
            print()
        except DotloopAPIError as e:
            print(f"   ERROR: {e}")
            if e.status_code == 401:
                print("   Token may be expired. Run dotloop_oauth.py to refresh.")
            sys.exit(1)

        # Get profile details
        if profile_id:
            print(f"2. Getting profile {profile_id}...")
            try:
                profile = client.get_profile(int(profile_id))
                print(f"   Name: {profile.get('name', 'N/A')}")
                print(f"   ID: {profile.get('id', 'N/A')}")
                print()
            except DotloopAPIError as e:
                print(f"   ERROR: {e}")
                print()

        # List recent loops
        if profile_id:
            print("3. Listing recent loops...")
            try:
                result = client.list_loops(int(profile_id), batch_size=5)
                loops = result.get("data", [])
                for loop in loops:
                    print(f"   Loop {loop.get('id')}: {loop.get('name', 'unnamed')}")
                    print(f"      Type: {loop.get('transactionType')} | Status: {loop.get('status')}")
                print(f"   Found {len(loops)} recent loop(s)")
                print()
            except DotloopAPIError as e:
                print(f"   ERROR: {e}")
                print()

        # Rate limit check
        print("4. Rate limit status:")
        print(f"   Remaining: {client.rate_limit_remaining or 'unknown'}")
        print(f"   Reset: {client.rate_limit_reset or 'unknown'}")
        print()

    print("=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
