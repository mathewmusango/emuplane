#!/usr/bin/env python3
"""Reset a principal's password from the host: `password.py <principal> [--account REF] [--password VALUE | --link]`."""

from __future__ import annotations

import secrets
import sys

import app  # the live stores and the same revocation the API uses


def resolve(name: str, account_ref: str) -> tuple[str, dict] | None:
    """`(account, record)`: the account named, or the only one holding that principal."""
    accounts = []
    if account_ref:
        account = app.ACCOUNTS.by_ref(account_ref)
        accounts = [account] if account is not None else []
    else:
        accounts = [
            account
            for account in app.ACCOUNTS.accounts.values()
            if app.ACCOUNTS._key(name) in (account.get("users") or {})
        ]
    for account in accounts:
        record = app.USERS.get(account["account_id"], name)
        if record is not None:
            return account["account_id"], record
    return None


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print(__doc__, file=sys.stderr)
        return 2
    username = args[0]
    account_ref = ""
    if "--account" in args:
        index = args.index("--account")
        account_ref = args[index + 1] if index + 1 < len(args) else ""
        if not account_ref:
            print("--account needs an account id or name", file=sys.stderr)
            return 2

    found = resolve(username, account_ref)
    if found is None:
        hint = (
            "no such principal in that account"
            if account_ref
            else f"no such principal: {username} (name the account with --account)"
        )
        print(hint, file=sys.stderr)
        return 1
    account_id, record = found

    if "--link" in args:
        token = app.mint_reset(record["username"], account_id)
        base = app.CONSOLE_URL or ""
        print(f"{base}/reset?token={token}")
        print(
            f"one-time link for {record['username']} in {account_id}, valid "
            f"{app.RESET_SECONDS // 60} min — it is not retrievable again",
            file=sys.stderr,
        )
        return 0

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

    password = supplied or secrets.token_urlsafe(12)
    app.USERS.set_password(account_id, record["username"], password)
    app.purge_user_sessions(account_id, record["username"])
    print(f"password reset for {record['username']} in {account_id}")
    if not supplied:
        print(f"new password: {password}  (shown once)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
