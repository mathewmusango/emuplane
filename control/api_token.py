#!/usr/bin/env python3
"""The control's API bearer token, hashed in the `settings` store: `token.py --status` or `--rotate`."""

from __future__ import annotations

import hashlib
import secrets
import sys
from datetime import datetime, timezone

from store import Store

KEY = "admin_token"


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def load(store: Store) -> dict:
    return store.payloads("settings").get(KEY) or {}


def status() -> int:
    record = load(Store())
    if not record.get("hash"):
        print("token: none set — bearer API access is off")
        return 0
    print(
        "token: set "
        f"(created {record.get('created_at', 'unknown')}, "
        f"rotations {record.get('rotations', 0)})"
    )
    return 0


def rotate() -> int:
    store = Store()
    previous = load(store)
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    store.put(
        "settings",
        KEY,
        {
            "hash": digest(token),
            "created_at": now,
            "rotations": int(previous.get("rotations", 0)) + 1,
        },
    )
    # Shown once, on stdout, to whoever asked for the rotation. Nothing logs it.
    print(token)
    print(
        "token rotated: store this value, it is not retrievable "
        "(only a hash is kept)",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    if "--status" in sys.argv[1:]:
        return status()
    if "--rotate" in sys.argv[1:]:
        return rotate()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
