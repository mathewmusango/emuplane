#!/usr/bin/env python3
"""Reset a principal's password from the host.

There is no mail transport on this server, so account recovery is a local act
rather than an emailed link: someone who can reach the deployment issues the new
password. This is the platform owner's break-glass path; the same operation is
available over the API (`POST /api/users/<username>/password`, bearer token or a
signed-in administrator).

    python /app/password.py <username>                  # generate, print once
    python /app/password.py <username> --password VALUE  # set a chosen one

Every session that principal holds is dropped, so a reset also ends whatever
was still signed in. `scripts/password.sh` runs this inside the container.
"""

from __future__ import annotations

import secrets
import sys

import app  # the live stores and the same revocation the API uses


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print(__doc__, file=sys.stderr)
        return 2
    username = args[0]
    supplied = ""
    if "--password" in args:
        index = args.index("--password")
        supplied = args[index + 1] if index + 1 < len(args) else ""
        if not supplied:
            print("--password needs a value", file=sys.stderr)
            return 2
    if supplied and len(supplied) < 8:
        print("the password must be at least 8 characters", file=sys.stderr)
        return 1

    record = app.USERS.get(username)
    if record is None:
        print(f"no such user: {username}", file=sys.stderr)
        return 1

    password = supplied or secrets.token_urlsafe(12)
    app.USERS.set_password(record["username"], password)
    app.purge_user_sessions(record.get("account_id", ""), record["username"])
    print(f"password reset for {record['username']}")
    if not supplied:
        print(f"new password: {password}  (shown once)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
