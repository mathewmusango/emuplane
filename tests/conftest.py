"""Paths, the emulator's HTTP surface, and the control's own signed client.

The S3 tests talk to a real socket. `signed.request` — the function `app.py`
calls for every root-signed request — signs and sends it; the stand-in server
frames the HTTP and hands the request to the emulator's own `handle_request`, so
the routing, the signing-region check and every handler are the emulator's.
Only the framing is the stand-in's.

`ministack-src` (the emulator) sits beside this repository; tests that need it
skip when it is not checked out.
"""

from __future__ import annotations

import asyncio
import re
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parent.parent
EMULATOR = ROOT.parent / "ministack-src"

sys.path[:0] = [str(ROOT / "control"), str(EMULATOR)]

# The S3 handlers read `AUTH` from `ministack.app`, which drags in the server's
# own dependencies. Nothing here serves IAM, so a stand-in module is enough.
if "ministack.app" not in sys.modules:
    _stub = types.ModuleType("ministack.app")
    _stub.AUTH = False
    sys.modules["ministack.app"] = _stub

import signed  # noqa: E402  (the code the control calls)


@pytest.fixture(scope="session")
def emulator():
    """The real `ministack.services.s3` — the parser, not a mock of it."""
    if not EMULATOR.is_dir():
        pytest.skip("ministack-src is not checked out beside the control")
    from ministack.services import s3

    return s3


@pytest.fixture(scope="session")
def s3_endpoint(emulator):
    """An HTTP endpoint that speaks the emulator's S3 surface — and the two APIs
    the console's other S3 tabs ask (S3 Tables, S3 Files), chosen by the service
    name in the credential scope, exactly as the emulator routes them."""

    handlers = {"s3": emulator}
    for name in ("s3tables", "s3files"):
        try:
            handlers[name] = __import__(
                f"ministack.services.{name}", fromlist=["handle_request"]
            )
        except ImportError:  # pragma: no cover - an older emulator checkout
            pass

    def route(headers: dict):
        auth = headers.get("authorization", "")
        match = re.search(r"Credential=[^/]+/\d{8}/[^/]+/([^/]+)/aws4_request", auth)
        return handlers.get(match.group(1) if match else "s3", emulator)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the test output readable
            pass

        def _serve(self, method):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            split = urlsplit(self.path)
            headers = {key.lower(): value for key, value in self.headers.items()}
            query = parse_qs(split.query, keep_blank_values=True)
            status, out_headers, out_body = asyncio.run(
                route(headers).handle_request(method, split.path, headers, body, query)
            )
            # Handlers return the body as bytes or, for a stored document, as the
            # text they hold; the ASGI layer encodes, and so does this.
            if isinstance(out_body, str):
                out_body = out_body.encode()
            self.send_response(status)
            for key, value in out_headers.items():
                if key.lower() == "content-length":
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(out_body)))
            self.end_headers()
            if method != "HEAD" and out_body:
                self.wfile.write(out_body)

        def do_GET(self):
            self._serve("GET")

        def do_PUT(self):
            self._serve("PUT")

        def do_POST(self):
            self._serve("POST")

        def do_DELETE(self):
            self._serve("DELETE")

        def do_HEAD(self):
            self._serve("HEAD")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="session")
def s3(s3_endpoint):
    """`buckets.create`'s client shape, over the wire, as the root user.

    Nothing is deleted by these tests, so the buckets the matrix creates stay in
    this process's copy of the emulator, readable through the same client.
    """

    def build(account: str, region: str):
        def call(method, path, body="", headers=None):
            return signed.request(
                s3_endpoint, "s3", account, region, method, path, body, headers
            )

        return call

    return build


@pytest.fixture
def recorder():
    """A client that records what was asked for and answers 200, for
    request-shape tests that never need the emulator."""

    class Recorded:
        def __init__(self):
            self.calls = []

        def __call__(self, method, path, body="", headers=None):
            self.calls.append(
                {
                    "method": method,
                    "path": path,
                    "body": body,
                    "headers": dict(headers or {}),
                }
            )
            return 200, ""

    return Recorded()
