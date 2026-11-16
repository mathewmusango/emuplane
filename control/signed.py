"""The calls the control makes as an account's root.

A 12-digit access key is an account root with no verified signature, so these
sign with a credential *name* and `Signature=local` — the property the gateway
already relies on, and the reason nothing in this module holds a secret.

The endpoint is an argument: `app.py` picks the node for the region and passes it
in, and the tests point it at a socket they control.

Two readers over one sender: `request` answers text (the shape every existing
caller wants), `request_bytes` answers the headers and the bytes (what an upload,
a download, or a look at an object's stored content type needs).
"""

from __future__ import annotations

import http.client
from datetime import datetime, timezone
from urllib.parse import urlsplit

# Signed, sized or inferred here; a caller may not supply them. `Content-Type` is
# deliberately absent: an upload knows the file's type, and S3 stores what it is
# sent.
RESERVED = ("host", "authorization", "content-length")


def _payload(body) -> bytes:
    return body if isinstance(body, bytes) else (body or "").encode()


def _prepare(endpoint, service, account, region, method, path, body, extra_headers):
    """The connection, payload and headers for one signed call."""
    url = urlsplit(endpoint)
    host = f"{url.hostname}:{url.port or 80}"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    data = _payload(body)
    headers = {
        "Host": host,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={account}/{stamp}/{region}/{service}"
            "/aws4_request, SignedHeaders=host, Signature=local"
        ),
        "x-amz-date": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "Content-Length": str(len(data)),
    }
    if data:
        if isinstance(body, bytes):
            headers["Content-Type"] = "application/octet-stream"
        else:
            headers["Content-Type"] = (
                "application/xml" if service == "s3" else "application/json"
            )
    for name, value in (extra_headers or {}).items():
        if name.lower() not in RESERVED:
            headers[name] = value
    return url, data, headers


def request_bytes(
    endpoint: str,
    service: str,
    account: str,
    region: str,
    method: str,
    path: str,
    body=b"",
    extra_headers: dict | None = None,
) -> tuple[int, dict, bytes]:
    """One signed call, answered as `(status, headers, body bytes)`.

    Headers come back lower-cased, which is how the emulator reads them and how a
    caller names them (`content-type`, `etag`).
    """
    url, data, headers = _prepare(
        endpoint, service, account, region, method, path, body, extra_headers
    )
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=30)
    try:
        conn.request(method, path, body=data or None, headers=headers)
        response = conn.getresponse()
        return (
            response.status,
            {name.lower(): value for name, value in response.getheaders()},
            response.read(),
        )
    except OSError as exc:
        return 0, {}, str(exc).encode()
    finally:
        conn.close()


def request(
    endpoint: str,
    service: str,
    account: str,
    region: str,
    method: str,
    path: str,
    body="",
    extra_headers: dict | None = None,
) -> tuple[int, str]:
    """One signed call, answered as `(status, body text)`.

    `body` may be text or bytes; bytes are sent as they are, which is what a
    binary upload hands over. The answer is decoded leniently because not every
    answer is text (an object read is not).
    """
    status, _headers, payload = request_bytes(
        endpoint, service, account, region, method, path, body, extra_headers
    )
    return status, payload.decode(errors="replace")
