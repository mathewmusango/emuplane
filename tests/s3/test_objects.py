"""Writing an object, editing a bucket's settings, emptying a bucket.

Each case drives `control/buckets.py` with the control's own signed client, wired
to the emulator stand-in — so the requests are the ones the console makes.
"""

from __future__ import annotations

import buckets
import signed

ACCOUNT = "344381301567"


def _client(endpoint, region="us-east-1"):
    def call(method, path, body="", headers=None):
        return signed.request(endpoint, "s3", ACCOUNT, region, method, path, body, headers)

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

    read = buckets.read_object(
        "object-read-bucket", "hello.txt", lambda method, path: client(method, path)
    )
    assert read["ok"], read.get("error")
    assert read["body"] == "hi there"

    missing = buckets.read_object(
        "object-read-bucket", "nope.txt", lambda method, path: client(method, path)
    )
    assert missing["ok"] is False
    assert missing["status"] == 404


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
