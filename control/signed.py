"""The calls the control makes as an account's root: signed with a credential name and `Signature=local`, never a secret."""

from __future__ import annotations

import http.client
from datetime import datetime, timezone
from urllib.parse import urlsplit

# Signed, sized or inferred here; a caller may not supply them, and `Content-Type` stays the upload's.
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
    """One signed call, answered as `(status, headers, body bytes)`, headers lower-cased."""
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
    """One signed call, answered as `(status, body text)`; bytes go out as they are and the answer decodes leniently."""
    status, _headers, payload = request_bytes(
        endpoint, service, account, region, method, path, body, extra_headers
    )
    return status, payload.decode(errors="replace")
