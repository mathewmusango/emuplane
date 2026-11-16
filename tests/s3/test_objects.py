"""Writing an object, editing a bucket's settings, emptying a bucket.

Each case drives `control/buckets.py` with the control's own signed client, wired
to the emulator stand-in — so the requests are the ones the console makes.
"""

from __future__ import annotations

import base64

import buckets
import signed

ACCOUNT = "344381301567"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _client(endpoint, region="us-east-1"):
    def call(method, path, body="", headers=None):
        return signed.request(endpoint, "s3", ACCOUNT, region, method, path, body, headers)

    return call


def _raw(endpoint, region="us-east-1"):
    """The same client, answering headers and bytes — what a download needs."""

    def call(method, path):
        return signed.request_bytes(endpoint, "s3", ACCOUNT, region, method, path)

    return call


def _create(client, name, **options):
    result = buckets.create(
        "us-east-1", {"account": ACCOUNT, "bucket": name, **options}, client
    )
    assert result["ok"], result.get("error")


def test_put_object_and_read_it_back(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "objects-bucket")

    written = buckets.put_object("objects-bucket", "notes/one.txt", "hello", client)
    assert written["ok"], written.get("error")

    status, body = client("GET", "/objects-bucket/notes/one.txt")
    assert status == 200
    assert body == "hello"


def test_editing_versioning_access_and_tags_sticks(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "editable-bucket")

    edited = buckets.update_settings(
        "editable-bucket",
        {
            "versioning": True,
            "block_public_access": {
                name: name != "BlockPublicPolicy" for name in buckets.PUBLIC_ACCESS
            },
            "tags": [{"Key": "stage", "Value": "prod"}],
        },
        client,
    )
    assert edited["ok"], edited.get("error")

    settings = buckets.read_settings(
        "editable-bucket", lambda method, path: client(method, path)
    )["settings"]
    assert settings["versioning"] is True
    assert settings["block_public_access"]["BlockPublicPolicy"] is False
    assert settings["tags"] == [{"Key": "stage", "Value": "prod"}]


def test_editing_nothing_is_refused(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "nothing-to-edit")
    result = buckets.update_settings("nothing-to-edit", {}, client)
    assert result["ok"] is False
    assert "nothing to update" in result["error"]


def test_emptying_uses_one_delete_objects_request_per_listing(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "empty-target-bucket")
    for key in ("a.txt", "b/c.txt"):
        assert buckets.put_object("empty-target-bucket", key, "x", client)["ok"]

    emptied = buckets.empty_bucket("empty-target-bucket", client)
    assert emptied["ok"], emptied.get("error")
    assert emptied["removed"] == 2

    status, body = client("GET", "/empty-target-bucket?list-type=2")
    assert status == 200
    assert "a.txt" not in body and "c.txt" not in body


def test_reading_an_object_returns_its_text(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "object-read-bucket")
    assert buckets.put_object("object-read-bucket", "hello.txt", "hi there", client)["ok"]

    read = buckets.read_object("object-read-bucket", "hello.txt", _raw(s3_endpoint))
    assert read["ok"], read.get("error")
    assert read["body"] == "hi there"
    assert read["binary"] is False
    assert read["content_type"] == "text/plain"

    missing = buckets.read_object("object-read-bucket", "nope.txt", _raw(s3_endpoint))
    assert missing["ok"] is False
    assert missing["status"] == 404


def test_a_file_is_uploaded_with_its_own_type_and_offered_as_a_download(s3_endpoint):
    """Bytes from a filesystem: stored as sent, typed as sent, never shown as text."""
    client = _client(s3_endpoint)
    _create(client, "binary-upload-bucket")

    written = buckets.put_object(
        "binary-upload-bucket", "pixel.png", PNG, client, content_type="image/png"
    )
    assert written["ok"], written.get("error")
    assert written["size"] == len(PNG)

    status, headers, data = _raw(s3_endpoint)("GET", "/binary-upload-bucket/pixel.png")
    assert status == 200
    assert data == PNG
    assert headers["content-type"] == "image/png"

    read = buckets.read_object("binary-upload-bucket", "pixel.png", _raw(s3_endpoint))
    assert read["ok"]
    assert read["binary"] is True
    assert read["body"] is None
    assert read["content_type"] == "image/png"
    assert read["size"] == len(PNG)


def test_bytes_without_a_type_are_not_shown_as_text(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "untyped-upload-bucket")
    assert buckets.put_object("untyped-upload-bucket", "blob.bin", b"\x00\x01\x02", client)["ok"]

    read = buckets.read_object("untyped-upload-bucket", "blob.bin", _raw(s3_endpoint))
    assert read["ok"]
    assert read["binary"] is True and read["body"] is None


def test_reading_a_binary_object_never_downloads_it(s3_endpoint):
    """HeadObject first: the type, size and ETag are headers, so the bytes stay put."""
    client = _client(s3_endpoint)
    _create(client, "head-first-bucket")
    assert buckets.put_object(
        "head-first-bucket", "pixel.png", PNG, client, content_type="image/png"
    )["ok"]

    seen = []

    def raw(method, path):
        seen.append(method)
        return signed.request_bytes(s3_endpoint, "s3", ACCOUNT, "us-east-1", method, path)

    read = buckets.read_object("head-first-bucket", "pixel.png", raw)
    assert read["ok"] and read["binary"] is True
    assert read["size"] == len(PNG)
    assert read["etag"] and read["last_modified"]
    assert seen == ["HEAD"]


def test_reading_a_text_object_heads_then_gets(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "head-then-get-bucket")
    assert buckets.put_object("head-then-get-bucket", "note.txt", "hello", client)["ok"]

    seen = []

    def raw(method, path):
        seen.append(method)
        return signed.request_bytes(s3_endpoint, "s3", ACCOUNT, "us-east-1", method, path)

    read = buckets.read_object("head-then-get-bucket", "note.txt", raw)
    assert read["body"] == "hello" and read["binary"] is False
    assert read["etag"] and read["truncated"] is False
    assert seen == ["HEAD", "GET"]


def test_head_bucket_says_where_a_bucket_lives(s3_endpoint):
    here = _client(s3_endpoint)
    _create(here, "head-here-bucket")
    west = buckets.create(
        "us-west-2",
        {"account": ACCOUNT, "bucket": "head-west-bucket", "block_public_access": None},
        _client(s3_endpoint, region="us-west-2"),
    )
    assert west["ok"], west.get("error")

    def head(name):
        return buckets.head_bucket(
            name,
            lambda method, path: signed.request_bytes(
                s3_endpoint, "s3", ACCOUNT, "us-east-1", method, path
            ),
        )

    assert head("head-here-bucket") == {
        "ok": True,
        "exists": True,
        "status": 200,
        "region": "us-east-1",
    }
    # A bucket in another region answers 301 and names it.
    away = head("head-west-bucket")
    assert away["exists"] is True and away["status"] == 301
    assert away["region"] == "us-west-2"
    # A 404 is a name that is not there at all.
    assert head("head-no-such-bucket")["exists"] is False


def test_the_configuration_documents_are_what_s3_has(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "documents-bucket")
    assert buckets.put_object("documents-bucket", "one.txt", "x", client)["ok"]

    documents = buckets.read_documents(
        "documents-bucket", lambda method, path: client(method, path)
    )["documents"]
    # Nothing was configured, so those subresources have no document...
    assert documents["lifecycle"] is None
    assert documents["policy"] is None
    assert documents["cors"] is None
    # ...while the version listing exists and lists the key.
    assert documents["versions"] and "one.txt" in documents["versions"]
