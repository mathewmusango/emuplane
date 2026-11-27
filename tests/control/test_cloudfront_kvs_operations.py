"""CloudFront KeyValueStore data plane: the six advertised operations, REST/JSON.

Signed with the `cloudfront-keyvaluestore` scope. The store itself is created on the
management plane (`cloudfront`), and both planes share it by ARN, so the suite creates
`ops-kvs-data` through `CreateKeyValueStore` and then drives the data plane with it.
Every mutating call sends `If-Match` with the ETag the previous read answered, and the
suite re-reads it before each write because one write invalidates it.
"""

from __future__ import annotations

import json
import re
import secrets

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/json"}

KVS_NAME = "ops-kvs-data"
RUN = secrets.token_hex(3)

_STATE: dict = {}


def mgmt(endpoint, method, path, body=b""):
    return signed.request_bytes(endpoint, "cloudfront", ACCOUNT, REGION, method, path, body)


def call(endpoint, method, path, body=b"", headers=None, query=""):
    if query:
        path = f"{path}?{query}"
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    if isinstance(body, str):
        body = body.encode()
    return signed.request_bytes(
        endpoint, "cloudfront-keyvaluestore", ACCOUNT, REGION, method, path, body, headers
    )


def ok(endpoint, method, path, body=b"", headers=None, query=""):
    status, headers_out, payload = call(endpoint, method, path, body, headers, query)
    assert status == 200, f"{method} {path} answered {status}: {payload[:400]!r}"
    return json.loads(payload or b"{}"), headers_out


def status_of(endpoint, method, path, body=b"", headers=None, query=""):
    return call(endpoint, method, path, body, headers, query)


def etag_of(headers: dict) -> str:
    for key, value in headers.items():
        if key.lower() == "etag":
            return value.strip('"')
    return ""


def ensure_store(endpoint) -> str:
    """The store's ARN, created on the management plane once.

    Read from the emulator's own answer: 1.5.42 changed it to end in the store's Id
    rather than its Name, so constructing it here would pin one release.
    """
    if "arn" not in _STATE:
        status, _headers, payload = mgmt(endpoint, "GET", "/2020-05-31/key-value-store")
        assert status == 200, payload[:300]
        if KVS_NAME.encode() not in payload:
            status, _headers, payload = mgmt(
                endpoint,
                "POST",
                "/2020-05-31/key-value-store",
                f"<KeyValueStore><Name>{KVS_NAME}</Name></KeyValueStore>".encode(),
            )
            assert status == 201, payload[:300]
        found = re.search(rb"<ARN>([^<]+)</ARN>", payload)
        assert found, payload[:300]
        _STATE["arn"] = found.group(1).decode()
    return _STATE["arn"]


def current_etag(endpoint) -> str:
    _body, headers = ok(endpoint, "GET", f"/key-value-stores/{ensure_store(endpoint)}")
    return etag_of(headers)


def test_describe_key_value_store_reads_it(endpoint):
    arn = ensure_store(endpoint)
    body, headers = ok(endpoint, "GET", f"/key-value-stores/{arn}")
    assert body["KvsARN"] == arn
    assert body["Status"] == "READY"
    assert etag_of(headers)


def test_put_key_writes_it(endpoint):
    arn = ensure_store(endpoint)
    key = f"ops-put-{RUN}"
    body, _headers = ok(
        endpoint,
        "PUT",
        f"/key-value-stores/{arn}/keys/{key}",
        {"Value": "put-value"},
        headers={"If-Match": current_etag(endpoint)},
    )
    assert body["ItemCount"] >= 1
    read, _headers = ok(endpoint, "GET", f"/key-value-stores/{arn}/keys/{key}")
    assert read["Value"] == "put-value"


def test_get_key_reads_it(endpoint):
    arn = ensure_store(endpoint)
    key = f"ops-get-{RUN}"
    ok(
        endpoint,
        "PUT",
        f"/key-value-stores/{arn}/keys/{key}",
        {"Value": "get-value"},
        headers={"If-Match": current_etag(endpoint)},
    )
    body, _headers = ok(endpoint, "GET", f"/key-value-stores/{arn}/keys/{key}")
    assert body["Key"] == key
    assert body["Value"] == "get-value"


def test_list_keys_lists_them(endpoint):
    arn = ensure_store(endpoint)
    key = f"ops-list-{RUN}"
    ok(
        endpoint,
        "PUT",
        f"/key-value-stores/{arn}/keys/{key}",
        {"Value": "listed"},
        headers={"If-Match": current_etag(endpoint)},
    )
    body, _headers = ok(endpoint, "GET", f"/key-value-stores/{arn}/keys", query="MaxResults=50")
    assert key in {item["Key"] for item in body["Items"]}


def test_update_keys_batches_puts_and_deletes(endpoint):
    arn = ensure_store(endpoint)
    deleted = f"ops-delete-{RUN}"
    ok(
        endpoint,
        "PUT",
        f"/key-value-stores/{arn}/keys/{deleted}",
        {"Value": "gone"},
        headers={"If-Match": current_etag(endpoint)},
    )
    body, _headers = ok(
        endpoint,
        "POST",
        f"/key-value-stores/{arn}/keys",
        {"Puts": [{"Key": f"ops-batch-{RUN}", "Value": "batched"}], "Deletes": [{"Key": deleted}]},
        headers={"If-Match": current_etag(endpoint)},
    )
    assert body["ItemCount"] >= 1
    read, _headers = ok(endpoint, "GET", f"/key-value-stores/{arn}/keys/ops-batch-{RUN}")
    assert read["Value"] == "batched"
    status, _headers, _payload = status_of(
        endpoint, "GET", f"/key-value-stores/{arn}/keys/{deleted}"
    )
    assert status == 404


def test_delete_key_removes_it(endpoint):
    arn = ensure_store(endpoint)
    key = f"ops-removed-{RUN}"
    ok(
        endpoint,
        "PUT",
        f"/key-value-stores/{arn}/keys/{key}",
        {"Value": "temporary"},
        headers={"If-Match": current_etag(endpoint)},
    )
    ok(
        endpoint,
        "DELETE",
        f"/key-value-stores/{arn}/keys/{key}",
        headers={"If-Match": current_etag(endpoint)},
    )
    status, _headers, _payload = status_of(
        endpoint, "GET", f"/key-value-stores/{arn}/keys/{key}"
    )
    assert status == 404
