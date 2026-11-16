"""The calls the control makes as an account's root.

A 12-digit access key is an account root with no verified signature, so these
sign with a credential *name* and `Signature=local` — the property the gateway
already relies on, and the reason nothing in this module holds a secret.

The endpoint is an argument: `app.py` picks the node for the region and passes it
in, and the tests point it at a socket they control.
"""

from __future__ import annotations

import http.client
from datetime import datetime, timezone
from urllib.parse import urlsplit

# Signed, sized or inferred here; a caller may not supply them.
RESERVED = ("host", "authorization", "content-length", "content-type")


def request(
    endpoint: str,
    service: str,
    account: str,
    region: str,
    method: str,
    path: str,
    body: str = "",
    extra_headers: dict | None = None,
) -> tuple[int, str]:
    """One signed call, answered as `(status, body text)`.

    `extra_headers` carries the few S3 create-time headers
    (`x-amz-object-ownership`, object lock) that only exist on the request
    itself.
    """
    url = urlsplit(endpoint)
    host = f"{url.hostname}:{url.port or 80}"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    data = (body or "").encode()
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
        headers["Content-Type"] = (
            "application/xml" if service == "s3" else "application/json"
        )
    for name, value in (extra_headers or {}).items():
        if name.lower() not in RESERVED:
            headers[name] = value
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=10)
    try:
        conn.request(method, path, body=data or None, headers=headers)
        response = conn.getresponse()
        return response.status, response.read().decode(errors="replace")
    except OSError as exc:
        return 0, str(exc)
    finally:
        conn.close()
