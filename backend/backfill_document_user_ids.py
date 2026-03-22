#!/usr/bin/env python3
"""Backfill legacy DocumentRecord.user_id values from Clerk IDs to UserProfile IDs."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

from db import DocumentRecord, UserProfile, close_db, init_db


async def run(dry_run: bool) -> None:
    await init_db()
    try:
        updated = 0
        users = await UserProfile.find(UserProfile.clerk_user_id != None).to_list()  # noqa: E711
        for user in users:
            if not user.clerk_user_id:
                continue
            docs = await DocumentRecord.find({"user_id": user.clerk_user_id}).to_list()
            for doc in docs:
                if dry_run:
                    print(f"would update {doc.id}: {doc.user_id} -> {user.id}")
                    updated += 1
                    continue
                doc.user_id = str(user.id)
                await doc.save()
                updated += 1
                print(f"updated {doc.id}: {user.clerk_user_id} -> {user.id}")

        action = "would update" if dry_run else "updated"
        print(f"{action} {updated} document record(s)")
    finally:
        await close_db()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print changes without saving them")
    args = parser.parse_args()

    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
