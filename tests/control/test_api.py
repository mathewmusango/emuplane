"""The control's own S3 API — what the console's pages call.

These run the real `ControlHandler` behind a real socket, authenticated with the
deployment's bearer token, and check the answers the pages rely on.
"""

from __future__ import annotations

from conftest import ACCOUNT, api, s3

PUBLIC_ACCESS = {
    "BlockPublicAcls": True,
    "IgnorePublicAcls": True,
    "BlockPublicPolicy": True,
    "RestrictPublicBuckets": True,
}


def page(**overrides) -> dict:
    """Exactly what the create page posts, with one field varied."""
    payload = {
        "account": ACCOUNT,
        "region": "us-east-1",
        "namespace": "global",
        "ownership": "BucketOwnerEnforced",
        "block_public_access": PUBLIC_ACCESS,
        "versioning": False,
        "tags": [],
        "encryption": "AES256",
        "bucket_key": True,
        "object_lock": False,
    }
    payload.update(overrides)
    return payload


def test_create_needs_a_name(console):
    status, body = api(console, "POST", "/api/s3/buckets", page(bucket=""))
    assert status == 400
    assert "name is required" in body["error"]


def test_create_refuses_a_region_the_account_has_not_enabled(console):
    status, body = api(
        console,
        "POST",
        "/api/s3/buckets",
        page(bucket="api-off-region-bucket", region="eu-central-1"),
    )
    assert status == 403
    assert "not enabled" in body["error"]


def test_create_answers_the_name_the_server_composed(console):
    status, body = api(
        console,
        "POST",
        "/api/s3/buckets",
        page(bucket="api-regional-bucket", namespace="regional"),
    )
    assert status == 200, body
    assert body["bucket"] == f"api-regional-bucket.{ACCOUNT}-us-east-1-an"
    assert body["created"] is True


def test_a_name_held_in_another_region_is_refused(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="api-dup-bucket"))[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/buckets",
        page(bucket="api-dup-bucket", region="us-west-2"),
    )
    assert status == 409
    assert "already exists" in body["error"]


def test_a_browse_row_carries_the_bucket_own_region(console):
    assert (
        api(
            console,
            "POST",
            "/api/s3/buckets",
            page(bucket="api-west-row-bucket", region="us-west-2"),
        )[0]
        == 200
    )

    status, body = api(
        console, "GET", f"/api/browse?account={ACCOUNT}&region=all&service=s3"
    )
    assert status == 200
    regions = {row["name"]: row.get("region") for row in body["resources"]}
    # The listing is account-wide, so the row must report the bucket's own region
    # rather than the one it was asked in.
    assert regions["api-west-row-bucket"] == "us-west-2"


def test_the_child_listings_answer(console):
    for section in ("table-buckets", "file-systems"):
        status, body = api(
            console, "GET", f"/api/s3/{section}?account={ACCOUNT}&region=us-east-1"
        )
        assert status == 200, body
        assert body["ok"] is True
        assert isinstance(body["items"], list)


def test_bucket_head_says_where_the_bucket_is(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="head-api-bucket"))[0] == 200

    status, body = api(
        console,
        "GET",
        f"/api/s3/bucket-head?account={ACCOUNT}&region=us-east-1&bucket=head-api-bucket",
    )
    assert status == 200, body
    assert body["exists"] is True and body["region"] == "us-east-1"


def test_bucket_head_names_the_region_a_pasted_link_forgot(console):
    status, body = api(
        console,
        "POST",
        "/api/s3/buckets",
        page(bucket="head-api-west-bucket", region="us-west-2"),
    )
    assert status == 200, body

    status, body = api(
        console,
        "GET",
        f"/api/s3/bucket-head?account={ACCOUNT}&region=us-east-1&bucket=head-api-west-bucket",
    )
    assert status == 200, body
    assert body["exists"] is True and body["region"] == "us-west-2"


def test_bucket_head_reports_a_name_that_is_not_there(console):
    status, body = api(
        console,
        "GET",
        f"/api/s3/bucket-head?account={ACCOUNT}&region=us-east-1&bucket=head-api-nowhere",
    )
    assert status == 200, body
    assert body["exists"] is False


def test_an_object_read_carries_what_only_a_head_knows(
    console,
):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="head-api-objects"))[0] == 200
    assert (
        api(
            console,
            "POST",
            "/api/s3/object",
            {
                "account": ACCOUNT,
                "region": "us-east-1",
                "bucket": "head-api-objects",
                "key": "notes/head.txt",
                "body": "read me",
            },
        )[0]
        == 200
    )

    status, body = api(
        console,
        "GET",
        f"/api/s3/object?account={ACCOUNT}&region=us-east-1&bucket=head-api-objects&key=notes/head.txt",
    )
    assert status == 200, body
    assert body["body"] == "read me"
    assert body["etag"] and body["last_modified"]
    assert body["size"] == len("read me")
    assert body["content_type"] == "text/plain"


def test_an_object_is_copied_to_another_bucket(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="copy-api-source"))[0] == 200
    assert api(console, "POST", "/api/s3/buckets", page(bucket="copy-api-destination"))[0] == 200
    assert (
        api(
            console,
            "POST",
            "/api/s3/object",
            {
                "account": ACCOUNT,
                "region": "us-east-1",
                "bucket": "copy-api-source",
                "key": "notes/one.txt",
                "body": "copied through the console",
            },
        )[0]
        == 200
    )

    status, body = api(
        console,
        "POST",
        "/api/s3/object-copy",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "copy-api-source",
            "key": "notes/one.txt",
            "destination": "copy-api-destination",
            "destination_key": "archive/one.txt",
        },
    )
    assert status == 200, body
    assert body["destination"] == "copy-api-destination"
    assert body["destination_key"] == "archive/one.txt"
    assert body["etag"]

    status, copied = api(
        console,
        "GET",
        f"/api/s3/object?account={ACCOUNT}&region=us-east-1&bucket=copy-api-destination&key=archive/one.txt",
    )
    assert status == 200, copied
    assert copied["body"] == "copied through the console"


def test_a_copy_to_a_missing_bucket_is_refused(console):
    status, body = api(
        console,
        "POST",
        "/api/s3/object-copy",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "copy-api-source",
            "key": "notes/one.txt",
            "destination": "copy-api-nowhere",
            "destination_key": "x.txt",
        },
    )
    assert status == 400
    assert "BucketNotFound" in body["error"]


def test_versioning_can_be_enabled_and_suspended_from_the_bucket_page(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="settings-api-bucket"))[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-settings-edit",
        {"account": ACCOUNT, "region": "us-east-1", "bucket": "settings-api-bucket", "versioning": True},
    )
    assert status == 200, body
    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1&bucket=settings-api-bucket",
    )
    assert read["settings"]["versioning"] is True

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-settings-edit",
        {"account": ACCOUNT, "region": "us-east-1", "bucket": "settings-api-bucket", "versioning": False},
    )
    assert status == 200, body
    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1&bucket=settings-api-bucket",
    )
    assert read["settings"]["versioning"] is False


def test_default_encryption_can_be_changed_from_the_bucket_page(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="settings-api-crypt"))[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-settings-edit",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "settings-api-crypt",
            "encryption": "aws:kms",
            "bucket_key": True,
        },
    )
    assert status == 200, body

    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1&bucket=settings-api-crypt",
    )
    assert read["settings"]["encryption"] == "aws:kms"
    assert read["settings"]["bucket_key"] is True


def test_an_unknown_encryption_is_refused_by_the_bucket_page(console):
    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-settings-edit",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "settings-api-crypt",
            "encryption": "rot13",
        },
    )
    assert status == 400
    assert "unknown encryption" in body["error"]


def test_the_bucket_page_offers_the_documents_s3_answers(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="documents-api-bucket"))[0] == 200

    status, body = api(
        console,
        "GET",
        f"/api/s3/bucket-documents?account={ACCOUNT}&region=us-east-1&bucket=documents-api-bucket",
    )
    assert status == 200, body
    documents = body["documents"]
    # The ACL exists on every bucket; logging and notifications are answered as
    # empty elements, which is the same state as not configured.
    assert documents["acl"] and "AccessControlPolicy" in documents["acl"]
    assert documents["logging"] is None
    assert documents["notifications"] is None
    assert documents["lifecycle"] is None


CORS = (
    '<CORSConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
    "<CORSRule><AllowedMethod>GET</AllowedMethod><AllowedOrigin>*</AllowedOrigin></CORSRule>"
    "</CORSConfiguration>"
)


def test_a_configuration_document_is_saved_and_cleared_through_the_page(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="documents-api-write"))[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "documents-api-write",
            "document": "cors",
            "action": "save",
            "body": CORS,
        },
    )
    assert status == 200, body

    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-documents?account={ACCOUNT}&region=us-east-1&bucket=documents-api-write",
    )
    assert read["documents"]["cors"] and "CORSRule" in read["documents"]["cors"]
    assert read["editable"]["cors"] == {"delete": True, "kind": "xml", "root": "CORSConfiguration"}

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "documents-api-write",
            "document": "cors",
            "action": "clear",
        },
    )
    assert status == 200, body

    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-documents?account={ACCOUNT}&region=us-east-1&bucket=documents-api-write",
    )
    assert read["documents"]["cors"] is None


def test_a_document_with_the_wrong_root_is_refused_by_the_page(console):
    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "documents-api-write",
            "document": "cors",
            "action": "save",
            "body": "<LifecycleConfiguration/>",
        },
    )
    assert status == 400
    assert "CORSConfiguration" in body["error"]


def test_the_version_listing_cannot_be_written(console):
    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "documents-api-write",
            "document": "versions",
            "action": "save",
            "body": "<x/>",
        },
    )
    assert status == 400
    assert "not a document this page writes" in body["error"]


def test_default_encryption_can_be_removed_from_the_bucket_page(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="crypt-api-remove"))[0] == 200
    assert (
        api(
            console,
            "POST",
            "/api/s3/bucket-settings-edit",
            {
                "account": ACCOUNT,
                "region": "us-east-1",
                "bucket": "crypt-api-remove",
                "encryption": "aws:kms",
                "bucket_key": True,
            },
        )[0]
        == 200
    )

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-settings-edit",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "crypt-api-remove",
            "remove_encryption": True,
        },
    )
    assert status == 200, body

    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1&bucket=crypt-api-remove",
    )
    assert read["settings"]["encryption"] == "AES256"
    assert read["settings"]["bucket_key"] is False


def test_an_object_written_through_the_gateway_is_readable_in_the_console(
    console, gateway
):
    name = "api-object-bucket"
    assert s3(gateway, "PUT", f"/{name}")[0] == 200
    assert s3(gateway, "PUT", f"/{name}/notes/hello.txt", body=b"hi")[0] == 200

    status, body = api(
        console,
        "GET",
        f"/api/s3/objects?account={ACCOUNT}&region=us-east-1&bucket={name}",
    )
    assert status == 200, body
    assert [item["key"] for item in body["objects"]] == ["notes/hello.txt"]


def test_objects_are_read_in_the_bucket_own_region(console):
    """A bucket is signed for its own region; elsewhere is a 301 naming it."""
    name = "api-west-objects-bucket"
    assert (
        api(console, "POST", "/api/s3/buckets", page(bucket=name, region="us-west-2"))[0]
        == 200
    )

    status, body = api(
        console,
        "GET",
        f"/api/s3/objects?account={ACCOUNT}&region=us-east-1&bucket={name}",
    )
    assert status == 301
    assert "us-west-2" in body["error"]
    assert body["region"] == "us-west-2"

    # And the right region is served.
    status, body = api(
        console,
        "GET",
        f"/api/s3/objects?account={ACCOUNT}&region=us-west-2&bucket={name}",
    )
    assert status == 200, body
