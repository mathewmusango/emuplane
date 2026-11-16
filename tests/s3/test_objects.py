"""Writing an object, editing a bucket's settings, emptying a bucket — the requests the console makes."""

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


def test_the_first_listing_answers_too(s3_endpoint):
    """ListObjects v1: the same bucket asked for without `list-type=2`."""
    client = _client(s3_endpoint)
    _create(client, "list-v1-bucket")
    assert buckets.put_object("list-v1-bucket", "one.txt", "x", client)["ok"]

    status, body = client("GET", "/list-v1-bucket")
    assert status == 200
    assert "ListBucketResult" in body
    assert "one.txt" in body and "<Contents>" in body


def test_copying_an_object_copies_its_bytes(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "copy-source-bucket")
    _create(client, "copy-destination-bucket")
    assert buckets.put_object("copy-source-bucket", "notes/one.txt", "copied text", client)[
        "ok"
    ]

    copied = buckets.copy_object(
        "copy-source-bucket",
        "notes/one.txt",
        "copy-destination-bucket",
        "archive/one.txt",
        client,
    )
    assert copied["ok"], copied.get("error")
    assert copied["etag"]

    status, body = client("GET", "/copy-destination-bucket/archive/one.txt")
    assert status == 200
    assert body == "copied text"


def test_a_copy_into_the_same_bucket_names_its_own_key(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "copy-in-place-bucket")
    assert buckets.put_object("copy-in-place-bucket", "one.txt", "same bucket", client)["ok"]

    copied = buckets.copy_object(
        "copy-in-place-bucket", "one.txt", "copy-in-place-bucket", "two.txt", client
    )
    assert copied["ok"], copied.get("error")
    assert client("GET", "/copy-in-place-bucket/two.txt")[1] == "same bucket"


def test_copying_a_missing_source_is_refused(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "copy-missing-source-bucket")
    _create(client, "copy-missing-dest-bucket")

    refused = buckets.copy_object(
        "copy-missing-source-bucket",
        "nope.txt",
        "copy-missing-dest-bucket",
        "whatever.txt",
        client,
    )
    assert refused["ok"] is False
    assert refused["status"] == 404


def test_default_encryption_can_be_changed_after_create(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "encryption-edit-bucket")

    edited = buckets.update_settings(
        "encryption-edit-bucket", {"encryption": "aws:kms", "bucket_key": True}, client
    )
    assert edited["ok"], edited.get("error")

    settings = buckets.read_settings(
        "encryption-edit-bucket", lambda method, path: client(method, path)
    )["settings"]
    assert settings["encryption"] == "aws:kms"
    assert settings["bucket_key"] is True


def test_an_unknown_encryption_is_refused_before_the_call(s3_endpoint):
    refused = buckets.update_settings("any-bucket", {"encryption": "rot13"}, _client(s3_endpoint))
    assert refused["ok"] is False
    assert "unknown encryption" in refused["error"]


def test_an_unset_subresource_is_reported_as_not_configured():
    """S3 answers an unset subresource with an empty element, not a 404: showing that as configuration reads as switched on."""
    answers = {
        "?logging": '<BucketLoggingStatus xmlns="http://s3.amazonaws.com/doc/2006-03-01/" />',
        "?acl": (
            '<AccessControlPolicy xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            "<Owner><ID>abc</ID></Owner></AccessControlPolicy>"
        ),
    }

    def call(_method, path):
        suffix = "?" + path.partition("?")[2]
        return 200, answers.get(suffix, '<Unset xmlns="x" />')

    documents = buckets.read_documents("documents-unit-bucket", call)["documents"]
    assert documents["logging"] is None
    assert documents["notifications"] is None
    assert documents["acl"] is not None
    assert "AccessControlPolicy" in documents["acl"]


CORS = (
    '<CORSConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
    "<CORSRule><AllowedMethod>GET</AllowedMethod><AllowedOrigin>*</AllowedOrigin></CORSRule>"
    "</CORSConfiguration>"
)
LIFECYCLE = (
    '<LifecycleConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
    "<Rule><ID>expire-tmp</ID><Status>Enabled</Status><Filter><Prefix>tmp/</Prefix></Filter>"
    "<Expiration><Days>30</Days></Expiration></Rule></LifecycleConfiguration>"
)


def _four(method, path, body="", headers=None):
    raise AssertionError(f"S3 should not have been called ({method} {path})")


def test_a_configuration_document_can_be_written_read_and_removed(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "cors-document-bucket")
    document = lambda method, path, body="", headers=None: client(method, path, body, headers)  # noqa: E731

    written = buckets.write_document("cors-document-bucket", "cors", CORS, document)
    assert written["ok"], written.get("error")

    documents = buckets.read_documents(
        "cors-document-bucket", lambda method, path: client(method, path)
    )["documents"]
    assert documents["cors"] and "CORSRule" in documents["cors"]

    cleared = buckets.clear_document("cors-document-bucket", "cors", document)
    assert cleared["ok"], cleared.get("error")
    documents = buckets.read_documents(
        "cors-document-bucket", lambda method, path: client(method, path)
    )["documents"]
    assert documents["cors"] is None


def test_a_lifecycle_document_round_trips(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "lifecycle-document-bucket")
    document = lambda method, path, body="", headers=None: client(method, path, body, headers)  # noqa: E731

    assert buckets.write_document("lifecycle-document-bucket", "lifecycle", LIFECYCLE, document)[
        "ok"
    ]
    documents = buckets.read_documents(
        "lifecycle-document-bucket", lambda method, path: client(method, path)
    )["documents"]
    assert documents["lifecycle"] and "expire-tmp" in documents["lifecycle"]

    assert buckets.clear_document("lifecycle-document-bucket", "lifecycle", document)["ok"]
    documents = buckets.read_documents(
        "lifecycle-document-bucket", lambda method, path: client(method, path)
    )["documents"]
    assert documents["lifecycle"] is None


def test_a_document_with_the_wrong_root_is_refused_before_the_call():
    refused = buckets.write_document("some-bucket", "cors", LIFECYCLE, _four)
    assert refused["ok"] is False
    assert "CORSConfiguration" in refused["error"]


def test_a_policy_must_be_a_json_document():
    refused = buckets.write_document("some-bucket", "policy", "<Policy/>", _four)
    assert refused["ok"] is False
    assert "Statement" in refused["error"]


def test_versions_is_a_listing_and_cannot_be_written():
    refused = buckets.write_document("some-bucket", "versions", "<x/>", _four)
    assert refused["ok"] is False
    assert "not a document this page writes" in refused["error"]


def test_logging_is_switched_off_with_an_empty_document(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "logging-clear-bucket")
    cleared = buckets.clear_document(
        "logging-clear-bucket",
        "logging",
        lambda method, path, body="", headers=None: client(method, path, body, headers),
    )
    assert cleared["ok"], cleared.get("error")


def test_an_acl_cannot_be_removed():
    refused = buckets.clear_document("some-bucket", "acl", _four)
    assert refused["ok"] is False
    assert "no way to remove" in refused["error"]


def test_default_encryption_can_be_removed(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "encryption-remove-bucket")

    removed = buckets.update_settings(
        "encryption-remove-bucket", {"remove_encryption": True}, client
    )
    assert removed["ok"], removed.get("error")

    settings = buckets.read_settings(
        "encryption-remove-bucket", lambda method, path: client(method, path)
    )["settings"]
    # S3 always encrypts; removing the setting falls back to SSE-S3.
    assert settings["encryption"] == "AES256"
    assert settings["bucket_key"] is False


POLICY = (
    '{"Version":"2012-10-17","Statement":[{"Effect":"Deny","Principal":"*",'
    '"Action":"s3:*","Resource":"arn:aws:s3:::policy-document-bucket/*"}]}'
)


def test_a_bucket_policy_is_json_and_round_trips(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "policy-document-bucket")
    document = lambda method, path, body="", headers=None: client(method, path, body, headers)  # noqa: E731

    written = buckets.write_document("policy-document-bucket", "policy", POLICY, document)
    assert written["ok"], written.get("error")
    documents = buckets.read_documents(
        "policy-document-bucket", lambda method, path: client(method, path)
    )["documents"]
    assert documents["policy"] and "Deny" in documents["policy"]

    assert buckets.clear_document("policy-document-bucket", "policy", document)["ok"]
    documents = buckets.read_documents(
        "policy-document-bucket", lambda method, path: client(method, path)
    )["documents"]
    assert documents["policy"] is None


def test_an_acl_is_written_where_s3_allows_acl_s(s3_endpoint):
    client = _client(s3_endpoint)
    created = buckets.create(
        "us-east-1",
        {"account": ACCOUNT, "bucket": "acl-document-bucket", "ownership": "BucketOwnerPreferred"},
        client,
    )
    assert created["ok"], created.get("error")

    current = buckets.read_documents(
        "acl-document-bucket", lambda method, path: client(method, path)
    )["documents"]["acl"]
    assert current

    written = buckets.write_document(
        "acl-document-bucket",
        "acl",
        current,
        lambda method, path, body="", headers=None: client(method, path, body, headers),
    )
    assert written["ok"], written.get("error")


def test_an_acl_is_refused_where_s3_disables_acls(s3_endpoint):
    """Bucket owner enforced is S3's default and means ACLs are off."""
    client = _client(s3_endpoint)
    _create(client, "acl-enforced-bucket")
    current = buckets.read_documents(
        "acl-enforced-bucket", lambda method, path: client(method, path)
    )["documents"]["acl"]

    refused = buckets.write_document(
        "acl-enforced-bucket",
        "acl",
        current,
        lambda method, path, body="", headers=None: client(method, path, body, headers),
    )
    assert refused["ok"] is False
    assert "AccessControlListNotSupported" in refused["error"]


def test_tags_are_replaced_and_removed(s3_endpoint):
    client = _client(s3_endpoint)
    _create(client, "tags-edit-bucket")

    assert buckets.update_settings(
        "tags-edit-bucket", {"tags": [{"Key": "team", "Value": "platform"}]}, client
    )["ok"]
    assert buckets.read_settings(
        "tags-edit-bucket", lambda method, path: client(method, path)
    )["settings"]["tags"] == [{"Key": "team", "Value": "platform"}]

    assert buckets.update_settings("tags-edit-bucket", {"remove_tags": True}, client)["ok"]
    assert buckets.read_settings(
        "tags-edit-bucket", lambda method, path: client(method, path)
    )["settings"]["tags"] == []


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
    # ...including the ones S3 answers with an empty element rather than a 404.
    assert documents["logging"] is None
    assert documents["notifications"] is None
    # ...while the version listing exists and lists the key.
    assert documents["versions"] and "one.txt" in documents["versions"]
