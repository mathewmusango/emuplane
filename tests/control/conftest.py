"""The control and its gateway, running in this process.

`app.py` refuses to import without a store, so this installs an in-memory
stand-in for `store.Store` — same string-per-key contract DynamoDB has — seeds two
accounts and one bearer token, and then runs the *real* `ControlHandler` and
`GatewayHandler` on ephemeral ports. Past that boundary nothing is mocked:
requests are real HTTP, signed the way a client signs them, and forwarded to the
stand-in emulator from `tests/conftest.py`.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import sys
import threading
import types
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
ACCOUNT = "111111111111"
OTHER = "222222222222"
TOKEN = "test-bearer-token"


def store_double() -> types.ModuleType:
    """`store.Store` over dicts: the calls `app.py` makes, nothing more."""

    module = types.ModuleType("store")

    class StoreNotProvisioned(RuntimeError):
        pass

    class Store:
        tables: dict[str, dict[str, str]] = {}

        def __init__(self, dynamo=None) -> None:
            self.dynamo = dynamo
            self.ready = True

        def verify_tables(self) -> None:
            self.ready = True

        def get(self, store: str, key: str) -> str | None:
            return self.tables.get(store, {}).get(key)

        def items(self, store: str) -> list[tuple[str, str]]:
            return list(self.tables.get(store, {}).items())

        def payloads(self, store: str) -> dict[str, dict]:
            found = {}
            for key, payload in self.items(store):
                try:
                    value = json.loads(payload)
                except ValueError:
                    continue
                if isinstance(value, dict):
                    found[key] = value
            return found

        def put(self, store: str, key: str, payload) -> None:
            body = payload if isinstance(payload, str) else json.dumps(payload)
            self.tables.setdefault(store, {})[key] = body

        def delete(self, store: str, key: str) -> None:
            self.tables.get(store, {}).pop(key, None)

        def delete_prefix(self, store: str, prefix: str) -> None:
            for key in [k for k in self.tables.get(store, {}) if k.startswith(prefix)]:
                self.delete(store, key)

        def replace_all(self, store: str, rows: dict[str, str]) -> None:
            existing = set(self.tables.get(store, {}))
            for key, payload in rows.items():
                self.put(store, key, payload)
            for key in existing - set(rows):
                self.delete(store, key)

    module.Store = Store
    module.StoreNotProvisioned = StoreNotProvisioned
    return module


def _account(account_id: str, alias: str) -> dict:
    return {
        "account_id": account_id,
        "alias": alias,
        "root": alias,
        "created_at": "2026-01-01 00:00:00Z",
        "regions": ["us-east-1", "us-west-2"],
        "users": {alias: {"username": alias, "role": "root"}},
    }


@pytest.fixture(scope="session")
def control(s3_endpoint):
    """`app` imported against the stand-in store and the stand-in emulator."""
    module = store_double()
    module.Store.tables = {
        "accounts": {
            ACCOUNT: json.dumps(_account(ACCOUNT, "test")),
            OTHER: json.dumps(_account(OTHER, "other")),
        },
        "settings": {
            "admin_token": json.dumps(
                {"hash": hashlib.sha256(TOKEN.encode()).hexdigest()}
            )
        },
    }
    os.environ["EP_BACKEND_URL"] = s3_endpoint
    os.environ["EP_GATEWAY_URL"] = "http://gateway.test"
    os.environ["EP_CONSOLE_URL"] = "http://console.test"
    os.environ["EP_POLL_SECONDS"] = "3600"

    sys.modules.pop("app", None)
    sys.modules["store"] = module
    if str(ROOT / "control") not in sys.path:
        sys.path.insert(0, str(ROOT / "control"))
    import app  # noqa: PLC0415 - imported once, after the store is in place

    return app


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


@pytest.fixture(scope="session")
def console(control):
    server, port = _serve(control.ControlHandler)
    yield f"127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture(scope="session")
def gateway(control):
    server, port = _serve(control.GatewayHandler)
    yield f"127.0.0.1:{port}"
    server.shutdown()


def _connection(host: str):
    name, _, port = host.partition(":")
    return http.client.HTTPConnection(name, int(port), timeout=15)


def api(host: str, method: str, path: str, payload=None, token: str = TOKEN):
    """One control-API call, as the bearer token (the deployment credential)."""
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if data:
        headers["Content-Type"] = "application/json"
    connection = _connection(host)
    try:
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        text = response.read().decode(errors="replace")
        try:
            return response.status, json.loads(text or "{}")
        except ValueError:
            return response.status, text
    finally:
        connection.close()


def s3(host: str, method: str, path: str, account: str = ACCOUNT,
       region: str = "us-east-1", body: bytes = b"", headers: dict | None = None):
    """One S3 call, signed the way a client signs it (credential scope only)."""
    sent = {
        "Host": host,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={account}/20261116/{region}/s3"
            "/aws4_request, SignedHeaders=host, Signature=test"
        ),
        "x-amz-date": "20261116T120000Z",
        "Content-Length": str(len(body)),
    }
    sent.update(headers or {})
    connection = _connection(host)
    try:
        connection.request(method, path, body=body or None, headers=sent)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()
