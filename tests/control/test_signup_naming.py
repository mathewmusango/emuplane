"""Sign-up names one login and one account, and never confuses the two.

The form used to ask for a single "account name" and use it as both the sign-in
name (unique across the lab) and the account's name (slugged, and suffixed `-2`
when taken) — so the two could disagree the moment either namespace was busy.
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
        return response.status, response.read().decode(errors="replace"), response.getheader("Set-Cookie") or ""
    finally:
        connection.close()


def _signup(host: str, username: str, account: str = "", email: str = ""):
    fields = {
        "username": username,
        "account": account,
        "email": email or f"{username.lower()}@example.com",
        "password": PASSWORD,
        "confirm": PASSWORD,
    }
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


def test_signup_creates_the_login_and_the_account_you_asked_for(console):
    status, _text, cookie = _signup(console, "Alice.Signup", "acme-signup")
    assert status == 302

    me = _meta(console, cookie)["me"]
    assert me["user"] == "Alice.Signup"
    assert me["alias"] == "acme-signup"
    assert me["role"] == "root"


def test_the_account_name_defaults_to_the_user_name(console):
    status, _text, cookie = _signup(console, "bob.signup")
    assert status == 302

    me = _meta(console, cookie)["me"]
    assert me["alias"] == "bob-signup"


def test_an_account_name_that_is_taken_is_refused_rather_than_suffixed(console):
    assert _signup(console, "carol.signup", "shared-name")[0] == 302
    before = _accounts(console)

    status, text, cookie = _signup(console, "carol.other", "shared-name")
    assert status == 400
    assert "already exists" in text
    assert cookie == ""
    assert _accounts(console) == before


def test_defaulting_to_a_taken_account_name_asks_for_one(console):
    assert _signup(console, "joseph", "jo-signup")[0] == 302

    # A different login whose name slugs to the same account name.
    status, text, _cookie = _signup(console, "Jo.Signup")
    assert status == 400
    assert "already exists" in text


def test_a_user_name_held_by_another_account_cannot_be_signed_up_again(console):
    assert _signup(console, "erin.signup")[0] == 302
    before = _accounts(console)

    status, text, _cookie = _signup(console, "erin.signup", "erin-second")
    assert status == 400
    assert "already in use on this lab" in text
    assert _accounts(console) == before


def test_one_name_is_one_identity_whatever_the_case(console):
    assert _signup(console, "Frank.Signup")[0] == 302

    status, text, _cookie = _signup(console, "frank.signup")
    assert status == 400
    assert "already in use on this lab" in text


def test_two_signups_are_two_accounts(console):
    _status, _text, first = _signup(console, "gina.signup")
    _status, _text, second = _signup(console, "harry.signup")

    one = _meta(console, first)["me"]
    two = _meta(console, second)["me"]
    assert one["account"] != two["account"]
