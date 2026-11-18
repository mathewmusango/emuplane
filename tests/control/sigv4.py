"""A real SigV4 signer for lab calls.

The conftest helpers send a literal `Signature=test`, which the emulator accepts
only for a root key with AUTH off. An IAM user's key is verified against its
secret, so a policy test has to sign the request the way an SDK would.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
from datetime import datetime, timezone
from urllib.parse import quote, urlencode


def headers(
    key: str,
    secret: str,
    host: str,
    method: str,
    path: str,
    query: str = "",
    body: bytes = b"",
    region: str = "us-east-1",
    service: str = "s3",
) -> dict:
    stamp = datetime.now(timezone.utc)
    amz_date = stamp.strftime("%Y%m%dT%H%M%SZ")
    day = stamp.strftime("%Y%m%d")
    payload = hashlib.sha256(body).hexdigest()
    signed_headers = "host;x-amz-content-sha256;x-amz-date"
    canonical_headers = (
        f"host:{host}\nx-amz-content-sha256:{payload}\nx-amz-date:{amz_date}\n"
    )
    canonical_request = "\n".join(
        [method, quote(path or "/"), query, canonical_headers, signed_headers, payload]
    )
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )

    def digest(key_bytes: bytes, message: str) -> bytes:
        return hmac.new(key_bytes, message.encode(), hashlib.sha256).digest()

    signing = digest(("AWS4" + secret).encode(), day)
    signing = digest(signing, region)
    signing = digest(signing, service)
    signing = digest(signing, "aws4_request")
    signature = hmac.new(signing, to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "Host": host,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }


def call(
    gateway: str,
    key: str,
    secret: str,
    method: str,
    path: str,
    query: str = "",
    body: bytes = b"",
) -> tuple[int, str]:
    """One signed request to the gateway as that key; `(status, body)`."""
    host, _, port = gateway.partition(":")
    connection = http.client.HTTPConnection(host, int(port or 80), timeout=20)
    try:
        connection.request(
            method,
            path + (f"?{query}" if query else ""),
            body=body or None,
            headers=headers(key, secret, gateway, method, path, query, body),
        )
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        connection.close()


def iam_call(emulator: str, account: str, action: str, region: str = "us-east-1", **params):
    """One IAM query-protocol call as the account root; `(status, body)`."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "control"))
    import signed  # noqa: PLC0415 - only needed by the lab tests

    body = urlencode({"Action": action, "Version": "2010-05-08", **params})
    return signed.request(emulator, "iam", account, region, "POST", "/", body)


def tag(body: str, name: str) -> str:
    """The text of the first `<name>` element, for the IAM XML answers."""
    start = body.find(f"<{name}>")
    if start < 0:
        return ""
    start += len(name) + 2
    return body[start : body.find(f"</{name}>", start)]
