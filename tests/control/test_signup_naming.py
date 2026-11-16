"""An account is created the way AWS creates one: an email, a name, and a root user.

There is no username at sign-up. The account's own principal is `root`, identified
by the email; usernames exist for IAM users, created inside the account afterwards,
and are unique per account rather than across the lab.
"""

from __future__ import annotations

import http.client
import json
import urllib.parse

from conftest import TOKEN, api

PASSWORD = "Pass@word1"


def _call(host: str, method: str, path: str, body: bytes = b"", headers: dict | None = None):
    name, _, port = host.partition(":")
    connection = http.client.HTTPConnection(name, int(port), timeout=15)
    sent = {"Content-Length": str(len(body))}
    sent.update(headers or {})
    try:
        connection.request(method, path, body=body or None, headers=sent)
        response = connection.getresponse()
        return (
            response.status,
            response.read().decode(errors="replace"),
            response.getheader("Set-Cookie") or "",
        )
    finally:
        connection.close()


def _signup(host: str, email: str, account: str = "", password: str = PASSWORD):
    fields = {"email": email, "account": account, "password": password, "confirm": password}
    status, text, cookie = _call(
        host,
        "POST",
        "/signup",
        urllib.parse.urlencode(fields).encode(),
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    return status, text, cookie.split(";")[0]


def _meta(host: str, cookie: str) -> dict:
    status, text, _ = _call(host, "GET", "/api/meta", headers={"Cookie": cookie})
    assert status == 200, text
    return json.loads(text)


def _accounts(host: str) -> int:
    status, body = api(host, "GET", "/api/meta", token=TOKEN)
    assert status == 200, body
    return body["total_accounts"]


def _user(host: str, account: str, username: str, email: str = ""):
    return api(
        host,
        "POST",
        "/api/users",
        {
            "account": account,
            "username": username,
            "email": email or f"{username}@example.com",
            "password": PASSWORD,
            "role": "iam",
        },
    )


def test_signup_creates_the_account_and_its_root(console):
    status, _text, cookie = _signup(console, "alice@example.com", "acme-signup")
    assert status == 302

    me = _meta(console, cookie)["me"]
    assert me["user"] == "root"
    assert me["role"] == "root"
    assert me["alias"] == "acme-signup"


def test_the_root_signs_in_with_the_email(console):
    assert _signup(console, "bob@example.com", "bob-account")[0] == 302

    status, body = api(
        console,
        "POST",
        "/api/auth/login",
        {"mode": "root", "email": "bob@example.com", "password": PASSWORD},
    )
    assert status == 200, body
    assert body["user"] == "root"
    assert body["alias"] == "bob-account"


def test_an_account_name_that_is_taken_is_refused(console):
    assert _signup(console, "carol@example.com", "shared-name")[0] == 302
    before = _accounts(console)

    status, text, cookie = _signup(console, "carol2@example.com", "shared-name")
    assert status == 400
    assert "already exists" in text
    assert cookie == ""
    assert _accounts(console) == before


def test_signup_needs_an_account_name(console):
    status, text, _cookie = _signup(console, "dave@example.com")
    assert status == 400
    assert "account name is required" in text


def test_two_accounts_can_hold_the_same_principal_name(console):
    _s, _t, first = _signup(console, "erin@example.com", "erin-one")
    _s, _t, second = _signup(console, "frank@example.com", "frank-two")
    one = _meta(console, first)["me"]["account"]
    two = _meta(console, second)["me"]["account"]
    assert one != two

    # IAM names are unique inside an account, not across the lab.
    assert _user(console, one, "deploy")[0] == 200
    status, body = _user(console, two, "deploy")
    assert status == 200, body


def test_the_same_principal_name_is_refused_inside_one_account(console):
    _s, _t, cookie = _signup(console, "gina@example.com", "gina-account")
    account = _meta(console, cookie)["me"]["account"]
    assert _user(console, account, "builder")[0] == 200

    status, body = _user(console, account, "Builder")
    assert status == 409
    assert "already taken" in body["error"]


def test_an_iam_user_signs_in_with_the_account_and_the_name(console):
    _s, _t, cookie = _signup(console, "harry@example.com", "harry-account")
    account = _meta(console, cookie)["me"]["account"]
    assert _user(console, account, "worker")[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/auth/login",
        {"mode": "iam", "account": account, "username": "worker", "password": PASSWORD},
    )
    assert status == 200, body
    assert body["user"] == "worker"
    assert body["role"] == "iam"


def test_a_legacy_credential_row_is_rekeyed_by_account(control):
    """Rows written before the account was part of the key are read once and rewritten."""
    import store

    legacy = {
        "username": "legacy-name",
        "email": "legacy@example.com",
        "password_hash": "pbkdf2_sha256$1$AA==$AA==",
        "account_id": "123456789012",
        "role": "root",
        "created_at": "2026-01-01 00:00:00Z",
        "last_login": None,
    }
    store.Store.tables.setdefault("users", {})["legacy-name"] = json.dumps(legacy)

    migrated = control.UserStore(control.DB)
    assert migrated.get("123456789012", "root") is not None
    assert "legacy-name" not in store.Store.tables["users"]


def test_a_legacy_root_principal_is_named_root(control):
    """An account written when the root could be called anything is read back as `root`."""
    import store

    account_id = "123456789013"
    legacy = {
        "account_id": account_id,
        "alias": "legacy-mixed",
        "root": "Mixed.Case",
        "created_at": "2026-01-01 00:00:00Z",
        "regions": ["us-east-1"],
        "auto_regions": [],
        "global_admin": False,
        "default_admin": False,
        "disabled": False,
        "users": {"Mixed.Case": {"username": "Mixed.Case", "role": "root"}},
    }
    store.Store.tables.setdefault("accounts", {})[account_id] = json.dumps(legacy)

    account = control.ACCOUNTS.by_ref(account_id)
    assert account is not None
    assert account["users"]["root"]["username"] == "root"
