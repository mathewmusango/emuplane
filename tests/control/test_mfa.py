"""MFA: enrolment over the control API, the sign-in challenge, and removal."""

from __future__ import annotations

import http.client
import json

import totp
from conftest import ACCOUNT, api

PASSWORD = "mfa-test-password"
USER = "mfa-test-user"


def _call(host: str, method: str, path: str, payload=None, cookie: str = ""):
    name, _, port = host.partition(":")
    connection = http.client.HTTPConnection(name, int(port), timeout=15)
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {}
    if body:
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = f"emuplane_session={cookie}"
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        text = response.read().decode(errors="replace")
        answer = json.loads(text or "{}")
        return response.status, answer, response.getheader("Set-Cookie") or ""
    finally:
        connection.close()


def _token(set_cookie: str) -> str:
    return set_cookie.split("emuplane_session=", 1)[1].split(";", 1)[0]


def _login(console, code: str = ""):
    payload = {
        "mode": "iam",
        "account": ACCOUNT,
        "username": USER,
        "password": PASSWORD,
    }
    if code:
        payload["code"] = code
    return _call(console, "POST", "/api/auth/login", payload)


def test_enrol_challenge_then_remove(console):
    """A password alone stops being enough once a TOTP device is attached."""
    status, body = api(
        console,
        "POST",
        "/api/users",
        {"username": USER, "password": PASSWORD, "account": ACCOUNT},
    )
    assert status == 200, body

    status, body, cookie = _login(console)
    assert status == 200, body
    assert body["mfa_required"] is False
    session = _token(cookie)

    status, device, _ = _call(console, "POST", "/api/mfa/device", cookie=session)
    assert status == 200, device
    assert device["serial"].startswith(f"arn:aws:iam::{ACCOUNT}:mfa/")

    # A wrong code leaves no device behind and no MFA on the principal.
    status, body, _ = _call(
        console,
        "POST",
        "/api/mfa/enrol",
        {"serial": device["serial"], "seed": device["seed"], "code": "000000"},
        session,
    )
    assert status == 400, body

    status, fresh, _ = _call(console, "POST", "/api/mfa/device", cookie=session)
    assert status == 200, fresh
    status, body, _ = _call(
        console,
        "POST",
        "/api/mfa/enrol",
        {
            "serial": fresh["serial"],
            "seed": fresh["seed"],
            "code": totp.code_at(fresh["seed"]),
        },
        session,
    )
    assert status == 200, body

    status, body, _ = _login(console)
    assert status == 200, body
    assert body["mfa_required"] is True
    assert body["mfa_token"]

    status, body, _ = _call(
        console,
        "POST",
        "/api/auth/mfa",
        {"token": body["mfa_token"], "code": "000000"},
    )
    assert status == 401, body

    status, body, _ = _login(console)
    status, body, cookie = _call(
        console,
        "POST",
        "/api/auth/mfa",
        {"token": body["mfa_token"], "code": totp.code_at(fresh["seed"])},
    )
    assert status == 200, body
    assert body["mfa_required"] is False
    assert _token(cookie)

    status, body, _ = _call(console, "DELETE", "/api/mfa", cookie=_token(cookie))
    assert status == 200, body
    status, body, _ = _login(console)
    assert status == 200, body
    assert body["mfa_required"] is False


def test_an_unassigned_device_can_be_removed(console):
    """A stale device name is not a dead end: the device is listed and deletable."""
    status, body = api(
        console,
        "POST",
        "/api/users",
        {"username": "mfa-cleanup-user", "password": PASSWORD, "account": ACCOUNT},
    )
    assert status == 200, body
    status, body, cookie = _call(
        console,
        "POST",
        "/api/auth/login",
        {
            "mode": "iam",
            "account": ACCOUNT,
            "username": "mfa-cleanup-user",
            "password": PASSWORD,
        },
    )
    assert status == 200, body
    session = _token(cookie)
    status, device, _ = _call(console, "POST", "/api/mfa/device", cookie=session)
    assert status == 200, device

    status, status_body, _ = _call(console, "GET", "/api/mfa", cookie=session)
    assert status == 200, status_body
    assert any(row["serial"] == device["serial"] for row in status_body["devices"])

    status, body, _ = _call(
        console,
        "DELETE",
        f"/api/mfa?serial={device['serial']}",
        cookie=session,
    )
    assert status == 200, body


def test_a_bearer_caller_has_no_principal_to_enrol(console):
    status, body = api(console, "POST", "/api/mfa/device")
    assert status == 400, body
