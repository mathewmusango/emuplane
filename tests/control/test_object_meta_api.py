"""The reads beside an object — tags, annotations, Object Lock — where absence is a state, not a failure."""

from __future__ import annotations

from urllib.parse import quote

from conftest import ACCOUNT, api, s3

BUCKET = "api-object-meta-bucket"
LOCKED = "api-object-meta-locked"
S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"


def _bucket(console, name: str, object_lock: bool = False) -> None:
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
            "versioning": object_lock,
            "tags": [],
            "encryption": "AES256",
            "bucket_key": True,
            "object_lock": object_lock,
            "bucket": name,
        },
    )
    assert status in (200, 400), body  # 400 when an earlier test made it


def _object(console, bucket: str, key: str, body: str = "held") -> None:
    status, answer = api(
        console,
        "POST",
        "/api/s3/object",
        {"account": ACCOUNT, "region": "us-east-1", "bucket": bucket, "key": key, "body": body},
    )
    assert status == 200, answer


def _meta(console, bucket: str, key: str):
    return api(
        console,
        "GET",
        f"/api/s3/object-meta?account={ACCOUNT}&region=us-east-1"
        f"&bucket={bucket}&key={quote(key, safe='')}",
    )


def _annotation(console, bucket: str, key: str, name: str):
    return api(
        console,
        "GET",
        f"/api/s3/object-annotation?account={ACCOUNT}&region=us-east-1"
        f"&bucket={bucket}&key={quote(key, safe='')}&name={quote(name, safe='')}",
    )


def _path(bucket: str, key: str) -> str:
    return f"/{bucket}/{quote(key, safe='')}"


def test_a_bare_object_reads_back_as_no_tags_no_annotations_and_no_lock(console):
    _bucket(console, BUCKET)
    _object(console, BUCKET, "plain.txt")

    status, body = _meta(console, BUCKET, "plain.txt")
    assert status == 200, body
    assert body["tags"] == []
    assert body["annotations"] == []
    # Object Lock is not configured on this bucket, which is a state, not a fault.
    assert body["retention"] is None
    assert body["legal_hold"] is None
    assert body["errors"] == {}


def test_the_tag_set_annotations_and_lock_states_are_read_back(console, gateway):
    _bucket(console, LOCKED, object_lock=True)
    _object(console, LOCKED, "held.txt")

    tagging = (
        f'<Tagging xmlns="{S3_NS}"><TagSet>'
        "<Tag><Key>stage</Key><Value>prod</Value></Tag>"
        "</TagSet></Tagging>"
    )
    status, _headers, text = s3(gateway, "PUT", _path(LOCKED, "held.txt") + "?tagging", body=tagging.encode())
    assert status == 200, text

    status, _headers, text = s3(
        gateway,
        "PUT",
        _path(LOCKED, "held.txt") + "?annotation&annotationName=note",
        body=b"first note",
    )
    assert status == 200, text

    retention = (
        f'<Retention xmlns="{S3_NS}"><Mode>GOVERNANCE</Mode>'
        "<RetainUntilDate>2030-01-01T00:00:00Z</RetainUntilDate></Retention>"
    )
    status, _headers, text = s3(gateway, "PUT", _path(LOCKED, "held.txt") + "?retention", body=retention.encode())
    assert status == 200, text

    legal_hold = f'<LegalHold xmlns="{S3_NS}"><Status>ON</Status></LegalHold>'
    status, _headers, text = s3(
        gateway, "PUT", _path(LOCKED, "held.txt") + "?legal-hold", body=legal_hold.encode()
    )
    assert status == 200, text

    status, body = _meta(console, LOCKED, "held.txt")
    assert status == 200, body
    assert body["tags"] == [{"Key": "stage", "Value": "prod"}]
    assert [row["name"] for row in body["annotations"]] == ["note"]
    assert body["annotations"][0]["size"] == str(len(b"first note"))
    assert "GOVERNANCE" in (body["retention"] or "")
    assert "2030-01-01" in (body["retention"] or "")
    assert "ON" in (body["legal_hold"] or "")

    # ...and one annotation's own content, which is the read the row opens.
    status, answer = _annotation(console, LOCKED, "held.txt", "note")
    assert status == 200, answer
    assert answer["body"] == "first note"


def test_tags_annotations_and_lock_are_written_from_the_console(console):
    _bucket(console, LOCKED, object_lock=True)
    _object(console, LOCKED, "console-tags.txt")

    status, body = api(
        console,
        "POST",
        "/api/s3/object-tags",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": LOCKED,
            "key": "console-tags.txt",
            "tags": [
                {"Key": "stage", "Value": "prod"},
                {"Key": "team", "Value": "platform"},
            ],
        },
    )
    assert status == 200, body

    status, body = api(
        console,
        "POST",
        "/api/s3/object-annotation",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": LOCKED,
            "key": "console-tags.txt",
            "name": "review",
            "body": "written from the console",
        },
    )
    assert status == 200, body

    status, body = api(
        console,
        "POST",
        "/api/s3/object-retention",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": LOCKED,
            "key": "console-tags.txt",
            "mode": "GOVERNANCE",
            "until": "2030-01-01T00:00:00Z",
        },
    )
    assert status == 200, body

    status, body = api(
        console,
        "POST",
        "/api/s3/object-legal-hold",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": LOCKED,
            "key": "console-tags.txt",
            "status": "ON",
        },
    )
    assert status == 200, body

    status, meta = _meta(console, LOCKED, "console-tags.txt")
    assert status == 200, meta
    assert {(tag["Key"], tag["Value"]) for tag in meta["tags"]} == {
        ("stage", "prod"),
        ("team", "platform"),
    }
    assert [row["name"] for row in meta["annotations"]] == ["review"]
    assert "GOVERNANCE" in (meta["retention"] or "")
    assert "ON" in (meta["legal_hold"] or "")

    # The same routes remove the tag set, one annotation, and the legal hold.
    assert api(
        console,
        "POST",
        "/api/s3/object-tags",
        {"account": ACCOUNT, "region": "us-east-1", "bucket": LOCKED, "key": "console-tags.txt", "tags": []},
    )[0] == 200
    assert api(
        console,
        "POST",
        "/api/s3/object-annotation",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": LOCKED,
            "key": "console-tags.txt",
            "name": "review",
            "remove": True,
        },
    )[0] == 200
    assert api(
        console,
        "POST",
        "/api/s3/object-legal-hold",
        {"account": ACCOUNT, "region": "us-east-1", "bucket": LOCKED, "key": "console-tags.txt", "status": "OFF"},
    )[0] == 200

    _, cleared = _meta(console, LOCKED, "console-tags.txt")
    assert cleared["tags"] == []
    assert cleared["annotations"] == []
    assert "OFF" in (cleared["legal_hold"] or "")


def test_the_object_writes_refuse_an_unknown_lock_value(console):
    _bucket(console, LOCKED, object_lock=True)
    _object(console, LOCKED, "console-lock.txt")

    status, body = api(
        console,
        "POST",
        "/api/s3/object-retention",
        {
            "account": ACCOUNT,
            "region": "us-east-1",
            "bucket": LOCKED,
            "key": "console-lock.txt",
            "mode": "SOFT",
            "until": "2030-01-01T00:00:00Z",
        },
    )
    assert status == 400
    assert "GOVERNANCE or COMPLIANCE" in body["error"]

    status, body = api(
        console,
        "POST",
        "/api/s3/object-legal-hold",
        {"account": ACCOUNT, "region": "us-east-1", "bucket": LOCKED, "key": "console-lock.txt", "status": "MAYBE"},
    )
    assert status == 400
    assert "ON or OFF" in body["error"]


def test_the_object_writes_need_a_bucket_key_and_name(console):
    _bucket(console, BUCKET)
    status, body = api(
        console,
        "POST",
        "/api/s3/object-tags",
        {"account": ACCOUNT, "region": "us-east-1", "bucket": BUCKET, "tags": []},
    )
    assert status == 400
    assert "bucket and a key" in body["error"]

    status, body = api(
        console,
        "POST",
        "/api/s3/object-annotation",
        {"account": ACCOUNT, "region": "us-east-1", "bucket": BUCKET, "key": "plain.txt", "name": ""},
    )
    assert status == 400
    assert "annotation name" in body["error"]


def test_an_annotation_that_is_not_there_says_so(console):
    _bucket(console, LOCKED, object_lock=True)
    _object(console, LOCKED, "unannotated.txt")

    status, body = _annotation(console, LOCKED, "unannotated.txt", "missing")
    assert status == 404
    assert body["ok"] is False
    assert body["error"]


def test_the_reads_need_a_key(console):
    _bucket(console, BUCKET)

    status, body = api(
        console,
        "GET",
        f"/api/s3/object-meta?account={ACCOUNT}&region=us-east-1&bucket={BUCKET}",
    )
    assert status == 400
    assert "key" in body["error"]

    status, body = api(
        console,
        "GET",
        f"/api/s3/object-annotation?account={ACCOUNT}&region=us-east-1&bucket={BUCKET}&key=plain.txt",
    )
    assert status == 400
    assert "annotation name" in body["error"]


def test_the_reads_need_a_credential(console):
    _bucket(console, BUCKET)
    _object(console, BUCKET, "plain.txt")

    status, _body = api(
        console,
        "GET",
        f"/api/s3/object-meta?account={ACCOUNT}&region=us-east-1"
        f"&bucket={BUCKET}&key=plain.txt",
        token="not-a-token",
    )
    assert status == 401
