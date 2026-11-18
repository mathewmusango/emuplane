"""The control's own S3 API — what the console's pages call, over a real socket as the bearer token."""

from __future__ import annotations

import re
from urllib.parse import quote

from conftest import ACCOUNT, api, s3


def listing_date(host: str, bucket: str) -> str:
    """The creation date ListBuckets answers for one bucket."""
    _, _, body = s3(host, "GET", "/?x-id=ListBuckets")
    found = re.search(
        rf"<Bucket>.*?<Name>{bucket}</Name>.*?<CreationDate>([^<]*)</CreationDate>",
        body.decode(),
        re.S,
    )
    return found.group(1) if found else ""

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
    # The listing is account-wide, so the row reports the bucket's own region.
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


def test_the_versions_page_lists_versions_and_deletes_one(console, gateway):
    name = "versions-api-bucket"
    assert (
        api(console, "POST", "/api/s3/buckets", page(bucket=name, versioning=True))[0]
        == 200
    )
    assert s3(gateway, "PUT", f"/{name}/a.txt", body=b"one")[0] == 200
    assert s3(gateway, "PUT", f"/{name}/a.txt", body=b"two")[0] == 200

    query = f"/api/s3/versions?account={ACCOUNT}&region=us-east-1&bucket={name}"
    status, body = api(console, "GET", query)
    assert status == 200, body
    rows = body["versions"]
    assert len(rows) == 2
    assert {row["latest"] for row in rows} == {True, False}
    assert all(row["key"] == "a.txt" for row in rows)

    old = next(row for row in rows if not row["latest"])
    status, body = api(
        console,
        "POST",
        "/api/s3/object-version-delete",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": name,
            "key": "a.txt",
            "version_id": old["version_id"],
        },
    )
    assert status == 200, body

    _, after = api(console, "GET", query)
    assert len(after["versions"]) == 1
    assert after["versions"][0]["version_id"] != old["version_id"]


def test_an_incomplete_upload_is_listed_with_its_parts_and_can_be_aborted(console, gateway):
    name = "uploads-api-bucket"
    assert api(console, "POST", "/api/s3/buckets", page(bucket=name))[0] == 200
    status, created = api(
        console,
        "POST",
        "/api/s3/multipart-create",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": name,
            "key": "big.bin",
            "content_type": "application/octet-stream",
        },
    )
    assert status == 200, created
    upload_id = created["upload_id"]
    part = f"/{name}/big.bin?partNumber=1&uploadId={upload_id}"
    assert s3(gateway, "PUT", part, body=b"first part")[0] == 200

    query = f"/api/s3/uploads?account={ACCOUNT}&region=us-east-1&bucket={name}"
    status, listed = api(console, "GET", query)
    assert status == 200, listed
    assert [row["upload_id"] for row in listed["uploads"]] == [upload_id]
    assert listed["uploads"][0]["key"] == "big.bin"

    status, parts = api(
        console,
        "GET",
        f"/api/s3/upload-parts?account={ACCOUNT}&region=us-east-1&bucket={name}"
        f"&key=big.bin&upload_id={upload_id}",
    )
    assert status == 200, parts
    assert [row["part_number"] for row in parts["parts"]] == ["1"]

    assert (
        api(
            console,
            "POST",
            "/api/s3/multipart-abort",
            {
                "account": ACCOUNT,
                "region": "us-east-1",
                "bucket": name,
                "key": "big.bin",
                "upload_id": upload_id,
            },
        )[0]
        == 200
    )
    _, after = api(console, "GET", query)
    assert after["uploads"] == []


def test_a_long_version_list_is_paged_rather_than_cut_short(console, gateway):
    name = "paging-api-bucket"
    assert (
        api(console, "POST", "/api/s3/buckets", page(bucket=name, versioning=True))[0]
        == 200
    )
    for body in (b"one", b"two", b"three"):
        assert s3(gateway, "PUT", f"/{name}/p.txt", body=body)[0] == 200

    base = f"/api/s3/versions?account={ACCOUNT}&region=us-east-1&bucket={name}"
    status, first = api(console, "GET", base + "&max_keys=2")
    assert status == 200, first
    assert len(first["versions"]) == 2
    assert first["truncated"] is True
    assert first["next_key_marker"]

    status, rest = api(
        console,
        "GET",
        base
        + f"&max_keys=2&key_marker={first['next_key_marker']}"
        + f"&version_id_marker={first['next_version_id_marker']}",
    )
    assert status == 200, rest
    seen = [row["version_id"] for row in first["versions"] + rest["versions"]]
    assert len(seen) == 3, seen
    assert len(set(seen)) == 3, seen
    assert rest["truncated"] is False


def test_incomplete_uploads_and_their_parts_are_paged_too(console, gateway):
    name = "paging-uploads-bucket"
    assert api(console, "POST", "/api/s3/buckets", page(bucket=name))[0] == 200
    uploads = {}
    for key in ("a.bin", "b.bin"):
        status, created = api(
            console,
            "POST",
            "/api/s3/multipart-create",
            {"account": ACCOUNT, "region": "us-east-1", "bucket": name, "key": key},
        )
        assert status == 200, created
        uploads[key] = created["upload_id"]

    base = f"/api/s3/uploads?account={ACCOUNT}&region=us-east-1&bucket={name}"
    status, first = api(console, "GET", base + "&max_uploads=1")
    assert status == 200, first
    assert len(first["uploads"]) == 1
    assert first["truncated"] is True
    assert first["next_key_marker"]

    status, rest = api(
        console,
        "GET",
        base
        + f"&max_uploads=1&key_marker={first['next_key_marker']}"
        + f"&upload_id_marker={first['next_upload_id_marker']}",
    )
    assert status == 200, rest
    seen = [row["upload_id"] for row in first["uploads"] + rest["uploads"]]
    assert sorted(seen) == sorted(uploads.values()), seen

    part = f"/{name}/a.bin?partNumber={{}}&uploadId={uploads['a.bin']}"
    for number in (1, 2):
        assert s3(gateway, "PUT", part.format(number), body=b"part")[0] == 200
    parts = (
        f"/api/s3/upload-parts?account={ACCOUNT}&region=us-east-1&bucket={name}"
        f"&key=a.bin&upload_id={uploads['a.bin']}"
    )
    status, first_parts = api(console, "GET", parts + "&max_parts=1")
    assert status == 200, first_parts
    assert [row["part_number"] for row in first_parts["parts"]] == ["1"]
    assert first_parts["truncated"] is True
    assert first_parts["next_part_number_marker"] == "1"

    status, next_parts = api(
        console,
        "GET",
        parts + f"&max_parts=1&part_number_marker={first_parts['next_part_number_marker']}",
    )
    assert status == 200, next_parts
    assert [row["part_number"] for row in next_parts["parts"]] == ["2"]


def test_object_ownership_is_switched_and_the_acl_follows(console, gateway):
    """The Permissions tab states whether ACLs work; the core lets it be changed."""
    name = "ownership-api-bucket"
    assert api(console, "POST", "/api/s3/buckets", page(bucket=name))[0] == 200
    assert s3(gateway, "PUT", f"/{name}/report.txt", body=b"hello")[0] == 200

    settings = f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1&bucket={name}"
    _, before = api(console, "GET", settings)
    assert before["settings"]["ownership"] == "BucketOwnerEnforced"

    acl = {
        "account": ACCOUNT,
        "region": "us-east-1",
        "bucket": name,
        "key": "report.txt",
        "canned_acl": "private",
    }
    # Enforced means no ACL at all, not even a private one.
    status, refused = api(console, "POST", "/api/s3/object-acl", acl)
    assert status == 400, refused
    assert "AccessControlListNotSupported" in refused["error"]

    status, switched = api(
        console,
        "POST",
        "/api/s3/bucket-settings-edit",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": name,
            "ownership": "BucketOwnerPreferred",
        },
    )
    assert status == 200, switched
    _, after = api(console, "GET", settings)
    assert after["settings"]["ownership"] == "BucketOwnerPreferred"

    assert api(console, "POST", "/api/s3/object-acl", acl)[0] == 200

    # ...and back, so the bucket's own answer is what the page follows both ways.
    assert (
        api(
            console,
            "POST",
            "/api/s3/bucket-settings-edit",
            {
                "account": ACCOUNT,
                "region": "us-east-1",
                "bucket": name,
                "ownership": "BucketOwnerEnforced",
            },
        )[0]
        == 200
    )
    assert api(console, "POST", "/api/s3/object-acl", acl)[0] == 400


def test_an_acl_is_read_and_written_per_version(console, gateway):
    name = "acl-version-api"
    assert (
        api(
            console,
            "POST",
            "/api/s3/buckets",
            page(bucket=name, versioning=True, ownership="BucketOwnerPreferred"),
        )[0]
        == 200
    )
    assert s3(gateway, "PUT", f"/{name}/report.txt", body=b"one")[0] == 200
    assert s3(gateway, "PUT", f"/{name}/report.txt", body=b"two")[0] == 200

    _, listed = api(
        console,
        "GET",
        f"/api/s3/versions?account={ACCOUNT}&region=us-east-1&bucket={name}",
    )
    older = next(row for row in listed["versions"] if not row["latest"])

    read = (
        f"/api/s3/object-acl?account={ACCOUNT}&region=us-east-1&bucket={name}"
        f"&key=report.txt&version_id={older['version_id']}"
    )
    status, body = api(console, "GET", read)
    assert status == 200, body
    assert body["version_id"] == older["version_id"]
    assert body["owner"]["id"]
    assert {grant["permission"] for grant in body["grants"]} >= {"FULL_CONTROL"}

    status, changed = api(
        console,
        "POST",
        "/api/s3/object-acl",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": name,
            "key": "report.txt",
            "canned_acl": "private",
            "version_id": older["version_id"],
        },
    )
    assert status == 200, changed
    assert changed["version_id"] == older["version_id"]

    # The current version keeps its own ACL: a version write is not a key-wide write.
    status, current = api(
        console,
        "GET",
        f"/api/s3/object-acl?account={ACCOUNT}&region=us-east-1&bucket={name}&key=report.txt",
    )
    assert status == 200, current
    assert current["version_id"] == ""
    assert current["grants"]


def test_the_website_document_is_written_read_and_removed(console, gateway):
    name = "website-api-bucket"
    assert api(console, "POST", "/api/s3/buckets", page(bucket=name))[0] == 200
    documents = f"/api/s3/bucket-documents?account={ACCOUNT}&region=us-east-1&bucket={name}"
    _, before = api(console, "GET", documents)
    assert before["documents"]["website"] is None

    body = (
        '<WebsiteConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        "<IndexDocument><Suffix>index.html</Suffix></IndexDocument>"
        "<ErrorDocument><Key>404.html</Key></ErrorDocument></WebsiteConfiguration>"
    )
    status, saved = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": name,
            "document": "website",
            "body": body,
        },
    )
    assert status == 200, saved

    _, after = api(console, "GET", documents)
    assert "index.html" in after["documents"]["website"]
    assert after["editable"]["website"]["delete"] is True

    status, cleared = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": name,
            "document": "website",
            "action": "clear",
        },
    )
    assert status == 200, cleared
    _, gone = api(console, "GET", documents)
    assert gone["documents"]["website"] is None


def test_an_object_acl_is_read_back(console, gateway):
    name = "acl-read-api"
    assert (
        api(
            console,
            "POST",
            "/api/s3/buckets",
            page(
                bucket=name,
                ownership="BucketOwnerPreferred",
                block_public_access={key: False for key in PUBLIC_ACCESS},
            ),
        )[0]
        == 200
    )
    assert s3(gateway, "PUT", f"/{name}/report.txt", body=b"hello")[0] == 200
    assert (
        api(
            console,
            "POST",
            "/api/s3/object-acl",
            {
                "account": ACCOUNT,
                "region": "us-east-1",
                "bucket": name,
                "key": "report.txt",
                "canned_acl": "public-read",
            },
        )[0]
        == 200
    )

    status, body = api(
        console,
        "GET",
        f"/api/s3/object-acl?account={ACCOUNT}&region=us-east-1&bucket={name}&key=report.txt",
    )
    assert status == 200, body
    assert body["public"] is True
    assert any(grant["uri"].endswith("/AllUsers") for grant in body["grants"])
    assert "READ" in {grant["permission"] for grant in body["grants"]}
    assert body["owner"]["id"]


def test_an_object_changes_storage_class_and_encryption_in_place(console, gateway):
    """S3 has no in-place edit: the change is a copy onto the object itself."""
    name = "actions-api-rewrite"
    assert api(console, "POST", "/api/s3/buckets", page(bucket=name))[0] == 200
    assert s3(gateway, "PUT", f"/{name}/report.txt", body=b"hello")[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/object-rewrite",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": name,
            "key": "report.txt",
            "storage_class": "STANDARD_IA",
        },
    )
    assert status == 200, body
    _status, head, _body = s3(gateway, "HEAD", f"/{name}/report.txt")
    assert head.get("x-amz-storage-class") == "STANDARD_IA"

    status, body = api(
        console,
        "POST",
        "/api/s3/object-rewrite",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": name,
            "key": "report.txt",
            "encryption": "aws:kms",
        },
    )
    assert status == 200, body
    _status, head, _body = s3(gateway, "HEAD", f"/{name}/report.txt")
    assert head.get("x-amz-server-side-encryption") == "aws:kms"


OPEN_PUBLIC_ACCESS = {name: False for name in PUBLIC_ACCESS}


def test_an_object_acl_is_written_when_the_bucket_allows_acls(console, gateway):
    name = "actions-api-acl"
    assert (
        api(
            console,
            "POST",
            "/api/s3/buckets",
            page(
                bucket=name,
                ownership="BucketOwnerPreferred",
                block_public_access=OPEN_PUBLIC_ACCESS,
            ),
        )[0]
        == 200
    )
    assert s3(gateway, "PUT", f"/{name}/report.txt", body=b"hello")[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/object-acl",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": name,
            "key": "report.txt",
            "canned_acl": "public-read",
        },
    )
    assert status == 200, body
    status, _headers, acl = s3(gateway, "GET", f"/{name}/report.txt?acl")
    assert status == 200
    assert b"AllUsers" in acl


def test_an_object_acl_is_refused_where_the_bucket_disables_acls(console, gateway):
    """The bucket owner enforced default has no ACL to write, and S3's own sentence is passed on."""
    name = "actions-api-acl-off"
    assert (
        api(
            console,
            "POST",
            "/api/s3/buckets",
            page(bucket=name, block_public_access=OPEN_PUBLIC_ACCESS),
        )[0]
        == 200
    )
    assert s3(gateway, "PUT", f"/{name}/report.txt", body=b"hello")[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/object-acl",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": name,
            "key": "report.txt",
            "canned_acl": "public-read",
        },
    )
    assert status == 400
    assert "AccessControlListNotSupported" in body["error"]


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
    assert read["settings"]["versioning_status"] == "Enabled"

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
    # Suspended is what S3 calls it: an enabled bucket never goes back to Disabled.
    assert read["settings"]["versioning_status"] == "Suspended"


def test_the_overview_names_when_the_bucket_was_made(console, gateway):
    """ListBuckets carries the only creation date S3 has, so the page reads it from there."""
    name = "settings-api-created"
    assert s3(gateway, "PUT", f"/{name}")[0] == 200

    status, body = api(
        console,
        "GET",
        f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1&bucket={name}",
    )
    assert status == 200, body
    assert body["settings"]["created"] == listing_date(gateway, name)
    assert body["settings"]["created"].endswith("Z")


def test_a_bucket_created_with_mfa_delete_comes_up_versioned_and_guarded(console):
    """MFA delete is a create-time setting too, and it drags versioning on with it."""
    name = "create-api-mfa"
    status, body = api(
        console,
        "POST",
        "/api/s3/buckets",
        page(bucket=name, mfa_delete="Enabled"),
    )
    assert status == 200, body

    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1&bucket={name}",
    )
    assert read["settings"]["mfa_delete"] == "Enabled"
    assert read["settings"]["versioning_status"] == "Enabled"

    status, body = api(
        console,
        "POST",
        "/api/exec",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "service": "s3",
            "operation": "delete-bucket",
            "params": {"Bucket": name},
        },
    )
    assert status == 409
    assert "turn it off" in body["error"]


def test_enabling_mfa_delete_turns_versioning_on_with_it(console):
    """MFA delete only exists on a versioned bucket, so the control enables versioning in the same call."""
    name = "settings-api-mfa-needs-versioning"
    assert api(console, "POST", "/api/s3/buckets", page(bucket=name))[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-settings-edit",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": name,
            "versioning_status": "Suspended",
            "mfa_delete": "Enabled",
        },
    )
    assert status == 200, body

    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1&bucket={name}",
    )
    assert read["settings"]["mfa_delete"] == "Enabled"
    assert read["settings"]["versioning_status"] == "Enabled"


def test_a_bucket_under_mfa_delete_cannot_be_deleted(console):
    """The flag means the bucket stays until it is turned off, not just that its versions are guarded."""
    name = "settings-api-mfa-no-delete"
    assert api(console, "POST", "/api/s3/buckets", page(bucket=name))[0] == 200
    assert (
        api(
            console,
            "POST",
            "/api/s3/bucket-settings-edit",
            {
                "account": ACCOUNT,
                "region": "us-east-1",
                "bucket": name,
                "mfa_delete": "Enabled",
            },
        )[0]
        == 200
    )

    status, body = api(
        console,
        "POST",
        "/api/exec",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "service": "s3",
            "operation": "delete-bucket",
            "params": {"Bucket": name},
        },
    )
    assert status == 409
    assert "turn it off" in body["error"]

    # Turning the flag off is the way out, and then the delete is the emulator's to answer.
    assert (
        api(
            console,
            "POST",
            "/api/s3/bucket-settings-edit",
            {
                "account": ACCOUNT,
                "region": "us-east-1",
                "bucket": name,
                "mfa_delete": "Disabled",
            },
        )[0]
        == 200
    )
    status, body = api(
        console,
        "POST",
        "/api/exec",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "service": "s3",
            "operation": "delete-bucket",
            "params": {"Bucket": name},
        },
    )
    assert status == 200, body


def test_mfa_delete_is_held_by_the_control_and_refused_by_the_gateway(console, gateway):
    """MiniStack drops MfaDelete, so the control keeps the flag and the gateway is what enforces it."""
    name = "settings-api-mfa"
    assert (
        api(console, "POST", "/api/s3/buckets", page(bucket=name, versioning=True))[0]
        == 200
    )

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-settings-edit",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": name,
            "versioning_status": "Enabled",
            "mfa_delete": "Enabled",
        },
    )
    assert status == 200, body

    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1&bucket={name}",
    )
    assert read["settings"]["mfa_delete"] == "Enabled"
    # The emulator never answers the element, so the console reads the control's own flag.
    assert read["settings"]["mfa_delete_source"] == "control"

    # Two versions, so a version delete has one to name.
    assert s3(gateway, "PUT", f"/{name}/report.txt", body=b"one")[0] == 200
    assert s3(gateway, "PUT", f"/{name}/report.txt", body=b"two")[0] == 200

    status, _headers, body = s3(gateway, "DELETE", f"/{name}/report.txt?versionId=first")
    assert status == 403
    assert b"MFA Delete is enabled" in body

    # The header is what the guard asks for; a plain delete writes a delete marker and was never guarded.
    status, _headers, _body = s3(
        gateway,
        "DELETE",
        f"/{name}/report.txt?versionId=first",
        headers={"x-amz-mfa": "arn:aws:iam::111111111111:mfa/test 123456"},
    )
    assert status != 403
    assert s3(gateway, "DELETE", f"/{name}/report.txt")[0] in (200, 204)

    # Turning it off is the same surface, and the guard goes with the flag.
    assert (
        api(
            console,
            "POST",
            "/api/s3/bucket-settings-edit",
            {
                "account": ACCOUNT,
                "region": "us-east-1",
                "bucket": name,
                "mfa_delete": "Disabled",
            },
        )[0]
        == 200
    )
    assert s3(gateway, "DELETE", f"/{name}/report.txt?versionId=first")[0] != 403


def test_the_public_access_block_can_be_removed_from_the_bucket_page(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="settings-api-pab"))[0] == 200
    query = (
        f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1"
        "&bucket=settings-api-pab"
    )

    _, read = api(console, "GET", query)
    assert read["settings"]["public_access_block_configured"] is True

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-settings-edit",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "settings-api-pab",
            "remove_public_access_block": True,
        },
    )
    assert status == 200, body

    # DeletePublicAccessBlock leaves no configuration behind, not one set to all-false.
    _, read = api(console, "GET", query)
    assert read["settings"]["public_access_block_configured"] is False
    assert set(read["settings"]["block_public_access"].values()) == {False}


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
    # The ACL exists on every bucket; logging and notifications are answered as empty elements.
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


def test_logging_notifications_and_replication_are_written_from_the_page(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="documents-log-bucket"))[0] == 200

    logging = (
        '<BucketLoggingStatus xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        "<LoggingEnabled><TargetBucket>documents-log-bucket</TargetBucket>"
        "<TargetPrefix>logs/</TargetPrefix></LoggingEnabled></BucketLoggingStatus>"
    )
    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "documents-log-bucket",
            "document": "logging",
            "action": "save",
            "body": logging,
        },
    )
    assert status == 200, body

    notifications = (
        '<NotificationConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        "<EventBridgeConfiguration/></NotificationConfiguration>"
    )
    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "documents-log-bucket",
            "document": "notifications",
            "action": "save",
            "body": notifications,
        },
    )
    assert status == 200, body

    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-documents?account={ACCOUNT}&region=us-east-1&bucket=documents-log-bucket",
    )
    assert "logs/" in (read["documents"]["logging"] or "")
    assert "EventBridgeConfiguration" in (read["documents"]["notifications"] or "")

    # Clearing logging writes the empty document S3 switches it off with.
    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "documents-log-bucket",
            "document": "logging",
            "action": "clear",
        },
    )
    assert status == 200, body
    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-documents?account={ACCOUNT}&region=us-east-1&bucket=documents-log-bucket",
    )
    assert read["documents"]["logging"] is None

    # Replication needs both sides versioned, and DeleteBucketReplication clears it.
    assert api(
        console,
        "POST",
        "/api/s3/buckets",
        page(bucket="documents-replica-source", versioning=True),
    )[0] == 200
    assert api(
        console,
        "POST",
        "/api/s3/buckets",
        page(bucket="documents-replica-target", versioning=True),
    )[0] == 200
    replication = (
        '<ReplicationConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"<Role>arn:aws:iam::{ACCOUNT}:role/replication</Role>"
        "<Rule><ID>all</ID><Status>Enabled</Status><Priority>1</Priority>"
        "<Filter><Prefix>data/</Prefix></Filter>"
        "<Destination><Bucket>arn:aws:s3:::documents-replica-target</Bucket></Destination>"
        "</Rule></ReplicationConfiguration>"
    )
    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "documents-replica-source",
            "document": "replication",
            "action": "save",
            "body": replication,
        },
    )
    assert status == 200, body

    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-documents?account={ACCOUNT}&region=us-east-1&bucket=documents-replica-source",
    )
    assert "documents-replica-target" in (read["documents"]["replication"] or "")

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "documents-replica-source",
            "document": "replication",
            "action": "clear",
        },
    )
    assert status == 200, body
    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-documents?account={ACCOUNT}&region=us-east-1&bucket=documents-replica-source",
    )
    assert read["documents"]["replication"] is None


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


POLICY = (
    '{"Version":"2012-10-17","Statement":[{"Effect":"Deny","Principal":"*",'
    '"Action":"s3:*","Resource":"arn:aws:s3:::policy-api-bucket/*"}]}'
)


def test_a_bucket_policy_is_saved_and_removed_through_the_page(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="policy-api-bucket"))[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "policy-api-bucket",
            "document": "policy",
            "action": "save",
            "body": POLICY,
        },
    )
    assert status == 200, body

    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-documents?account={ACCOUNT}&region=us-east-1&bucket=policy-api-bucket",
    )
    assert read["documents"]["policy"] and "Deny" in read["documents"]["policy"]
    assert read["editable"]["policy"]["kind"] == "json"

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-document",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "policy-api-bucket",
            "document": "policy",
            "action": "clear",
        },
    )
    assert status == 200, body
    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-documents?account={ACCOUNT}&region=us-east-1&bucket=policy-api-bucket",
    )
    assert read["documents"]["policy"] is None


def test_tags_are_edited_and_removed_from_the_bucket_page(console):
    assert api(console, "POST", "/api/s3/buckets", page(bucket="tags-api-bucket"))[0] == 200

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-settings-edit",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "tags-api-bucket",
            "tags": [{"Key": "team", "Value": "platform"}],
        },
    )
    assert status == 200, body
    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1&bucket=tags-api-bucket",
    )
    assert read["settings"]["tags"] == [{"Key": "team", "Value": "platform"}]

    status, body = api(
        console,
        "POST",
        "/api/s3/bucket-settings-edit",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": "tags-api-bucket",
            "remove_tags": True,
        },
    )
    assert status == 200, body
    _, read = api(
        console,
        "GET",
        f"/api/s3/bucket-settings?account={ACCOUNT}&region=us-east-1&bucket=tags-api-bucket",
    )
    assert read["settings"]["tags"] == []


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
    # One level deep, as S3 lists: a shared prefix is a folder, not a copy of its keys.
    assert [item["key"] for item in body["objects"]] == ["notes/"]

    status, body = api(
        console,
        "GET",
        f"/api/s3/objects?account={ACCOUNT}&region=us-east-1&bucket={name}&prefix=notes/",
    )
    assert status == 200, body
    assert [item["key"] for item in body["objects"]] == ["notes/hello.txt"]


def test_a_long_object_listing_is_paged_and_a_token_carries_the_rest(console, gateway):
    """ListObjectsV2 answers a page, not the folder; the console asks for the rest with the token it was given."""
    name = "api-paged-bucket"
    assert s3(gateway, "PUT", f"/{name}")[0] == 200
    for index in range(5):
        assert s3(gateway, "PUT", f"/{name}/page-{index}.txt", body=b"x")[0] == 200

    query = f"/api/s3/objects?account={ACCOUNT}&region=us-east-1&bucket={name}&max_keys=2"
    status, body = api(console, "GET", query)
    assert status == 200, body
    assert len(body["objects"]) == 2
    assert body["truncated"] is True
    assert body["next_token"]

    seen = [item["key"] for item in body["objects"]]
    token = body["next_token"]
    while token:
        status, body = api(
            console,
            "GET",
            f"{query}&continuation_token={quote(token, safe='')}",
        )
        assert status == 200, body
        seen += [item["key"] for item in body["objects"]]
        token = body["next_token"] if body["truncated"] else ""
    assert seen == [f"page-{index}.txt" for index in range(5)]


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
