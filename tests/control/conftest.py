"""The control and its gateway running in-process: a stand-in `store.Store` over dicts, real HTTP past that boundary."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import sys
import threading
import types
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
# A lab sweep signs as the account under test, so the resources are visible in its console.
ACCOUNT = os.environ.get("EP_LAB_ACCOUNT") or "111111111111"
OTHER = os.environ.get("EP_LAB_ACCOUNT2") or "222222222222"
TOKEN = "test-bearer-token"
EMULATOR = Path(os.environ.get("EP_EMULATOR_SRC") or ROOT.parent / "ministack-src")
LIVE_ENDPOINT = os.environ.get("EP_LAB_EMULATOR")
_VERSION_CACHE: dict[str, str] = {}


def emulator_version() -> str:
    """The emulator under test: its checkout's `pyproject.toml`, or the live node's health."""
    if "version" in _VERSION_CACHE:
        return _VERSION_CACHE["version"]
    version = ""
    if LIVE_ENDPOINT:
        try:
            import urllib.request

            with urllib.request.urlopen(
                LIVE_ENDPOINT.rstrip("/") + "/health", timeout=5
            ) as response:
                version = str(
                    json.loads(response.read().decode() or "{}").get("version") or ""
                )
        except Exception:
            version = ""
    else:
        project = EMULATOR / "pyproject.toml"
        if project.is_file():
            found = re.search(
                r'^version = "([^"]+)"',
                project.read_text(encoding="utf-8"),
                re.MULTILINE,
            )
            version = found.group(1) if found else ""
    _VERSION_CACHE["version"] = version
    return version


def requires(service: str, operation: str) -> None:
    """Skip when the emulator under test predates the operation, per the compatibility chain."""
    version = emulator_version()
    if not version:
        pytest.skip("the emulator's version is unknown, so its operations cannot be decided")
    from compatibility import load

    compat = load()
    if not compat.supports(service, operation, version):
        pytest.skip(
            f"{service}:{operation} arrived in {compat.since(service, operation)}; "
            f"this emulator is {version}"
        )


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
