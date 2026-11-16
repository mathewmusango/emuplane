"""Uploading a file from the operator's machine, and getting it back: bytes and content type kept."""

from __future__ import annotations

import base64
import http.client
from urllib.parse import urlencode

from conftest import ACCOUNT, TOKEN, api

BUCKET = "api-upload-bucket"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _bucket(console) -> None:
    status, body = api(
        console,
        "POST",
        "/api/s3/buckets",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "namespace": "global",
            "ownership": "BucketOwnerEnforced",
            "block_public_access": None,
            "versioning": False,
            "tags": [],
            "encryption": "AES256",
            "bucket_key": True,
            "object_lock": False,
            "bucket": BUCKET,
        },
    )
    assert status in (200, 400), body  # 400 when an earlier test made it


def _connection(host: str):
    name, _, port = host.partition(":")
    return http.client.HTTPConnection(name, int(port), timeout=30)


def upload(host: str, key: str, data: bytes, content_type: str = "application/octet-stream"):
    """POST a file body to the console, as the browser does."""
    path = "/api/s3/object-upload?" + urlencode(
        {"account": ACCOUNT, "region": "us-east-1", "bucket": BUCKET, "key": key}
    )
    connection = _connection(host)
    try:
        connection.request(
            "POST",
            path,
            body=data,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": content_type,
            },
        )
        response = connection.getresponse()
        return response.status, response.read().decode(errors="replace")
    finally:
        connection.close()


def download(host: str, key: str):
    path = "/api/s3/object-download?" + urlencode(
        {"account": ACCOUNT, "region": "us-east-1", "bucket": BUCKET, "key": key}
    )
    connection = _connection(host)
    try:
        connection.request("GET", path, headers={"Authorization": f"Bearer {TOKEN}"})
        response = connection.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        connection.close()


def read(console, key: str):
    return api(
        console,
        "GET",
        f"/api/s3/object?account={ACCOUNT}&region=us-east-1&bucket={BUCKET}&key={key}",
    )


def test_a_file_upload_keeps_its_bytes_and_its_type(console):
    _bucket(console)
    status, body = upload(console, "pixel.png", PNG, "image/png")
    assert status == 200, body

    status, listed = api(
        console,
        "GET",
        f"/api/s3/objects?account={ACCOUNT}&region=us-east-1&bucket={BUCKET}",
    )
    assert status == 200, listed
    row = next(item for item in listed["objects"] if item["key"] == "pixel.png")
    assert row["size"] == str(len(PNG))

    status, read_back = read(console, "pixel.png")
    assert status == 200, read_back
    assert read_back["binary"] is True
    assert read_back["body"] is None
    assert read_back["content_type"] == "image/png"
    assert read_back["size"] == len(PNG)

    status, headers, data = download(console, "pixel.png")
    assert status == 200
    assert data == PNG
    assert headers["content-type"] == "image/png"
    assert "attachment" in headers["content-disposition"]
    assert "pixel.png" in headers["content-disposition"]


def test_a_text_file_is_shown_in_the_page_and_downloadable(console):
    _bucket(console)
    status, body = upload(console, "notes/readme.txt", b"hello from a file\n", "text/plain")
    assert status == 200, body

    status, read_back = read(console, "notes/readme.txt")
    assert status == 200, read_back
    assert read_back["binary"] is False
    assert read_back["body"] == "hello from a file\n"

    status, headers, data = download(console, "notes/readme.txt")
    assert status == 200
    assert data == b"hello from a file\n"
    assert headers["content-type"].startswith("text/plain")


def test_an_upload_needs_a_key(console):
    _bucket(console)
    path = "/api/s3/object-upload?" + urlencode(
        {"account": ACCOUNT, "region": "us-east-1", "bucket": BUCKET}
    )
    connection = _connection(console)
    try:
        connection.request(
            "POST",
            path,
            body=b"x",
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "text/plain"},
        )
        response = connection.getresponse()
        assert response.status == 400
        assert "a bucket and a key are required" in response.read().decode()
    finally:
        connection.close()


def test_a_file_over_the_cap_is_refused(control, console, monkeypatch):
    _bucket(console)
    monkeypatch.setattr(control, "MAX_UPLOAD_BYTES", 8)
    status, body = upload(console, "too-big.bin", b"more than eight bytes")
    assert status == 413
    assert "uploads up to 8" in body


def test_a_missing_object_cannot_be_downloaded(console):
    _bucket(console)
    status, _headers, data = download(console, "nothing-here.bin")
    assert status == 404
    assert b"NoSuchKey" in data or b"does not exist" in data


def test_a_content_type_is_never_forwarded_unchecked(control):
    assert control.safe_content_type("image/png") == "image/png"
    assert control.safe_content_type("text/plain; charset=utf-8") == "text/plain; charset=utf-8"
    # A header is not a place to trust: everything from the first CR/LF is dropped, not forwarded.
    assert control.safe_content_type("text/plain\r\nX-Evil: 1") == "text/plain"
    assert control.safe_content_type("") == "application/octet-stream"
    assert control.safe_content_type("   ") == "application/octet-stream"
