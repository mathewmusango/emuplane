"""Data Firehose on the wire: all 12 advertised operations, JSON 1.1.

The target prefix is `Firehose_20150804`. A stream is keyed by name, so a stable
stream carries the read, tag and encryption tests; a create or delete test makes
its own. A stream may have no destination, which keeps `PutRecord` from trying to
write to S3; `UpdateDestination` uses a separate stream that is created with an
S3 destination and never receives a record.
"""

from __future__ import annotations

import base64
import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PREFIX = "Firehose_20150804"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
STREAM = "ops-firehose"
DEST_STREAM = "ops-firehose-dest"
ENC_STREAM = "ops-firehose-enc"
PUT_STREAM = "ops-firehose-put"


def call(endpoint, action: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    headers = {"X-Amz-Target": f"{PREFIX}.{action}", **JSON_TYPE}
    return signed.request(endpoint, "firehose", ACCOUNT, REGION, "POST", "/", body, headers)


def ok(endpoint, action: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, action, payload)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def refused(endpoint, action: str, payload: dict | None = None, code: str = "") -> str:
    status, text = call(endpoint, action, payload)
    assert status >= 400, f"{action} unexpectedly answered {status}: {text[:400]}"
    if code:
        assert code in text
    return text


def stream_body(name: str, *, destination: bool = False) -> dict:
    body: dict = {"DeliveryStreamName": name}
    if destination:
        body["ExtendedS3DestinationConfiguration"] = {
            "RoleARN": f"arn:aws:iam::{ACCOUNT}:role/ops-firehose-role",
            "BucketARN": "arn:aws:s3:::ops-firehose-bucket",
        }
    return body


def ensure_stream(endpoint, name: str = STREAM, *, destination: bool = False) -> dict:
    status, text = call(endpoint, "CreateDeliveryStream", stream_body(name, destination=destination))
    assert status == 200 or "ResourceInUseException" in text, text[:300]
    return ok(endpoint, "DescribeDeliveryStream", {"DeliveryStreamName": name})["DeliveryStreamDescription"]


def base64_data(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


# ---------------------------------------------------------------------------
# Streams
# ---------------------------------------------------------------------------


def test_create_delivery_stream_is_read_back(endpoint):
    name = f"ops-firehose-created-{time.time_ns()}"
    created = ok(endpoint, "CreateDeliveryStream", stream_body(name))
    assert created["DeliveryStreamARN"].endswith(f"deliverystream/{name}")
    described = ok(endpoint, "DescribeDeliveryStream", {"DeliveryStreamName": name})["DeliveryStreamDescription"]
    assert described["DeliveryStreamName"] == name
    assert described["DeliveryStreamStatus"] == "ACTIVE"


def test_delete_delivery_stream_removes_the_stream_it_created(endpoint):
    name = f"ops-firehose-deleted-{time.time_ns()}"
    ok(endpoint, "CreateDeliveryStream", stream_body(name))
    ok(endpoint, "DeleteDeliveryStream", {"DeliveryStreamName": name})
    refused(endpoint, "DescribeDeliveryStream", {"DeliveryStreamName": name}, "ResourceNotFoundException")


def test_describe_delivery_stream_reads_the_stream(endpoint):
    described = ensure_stream(endpoint)
    assert described["DeliveryStreamName"] == STREAM
    assert described["DeliveryStreamType"] == "DirectPut"


def test_list_delivery_streams_lists_the_stream(endpoint):
    ensure_stream(endpoint)
    names = ok(endpoint, "ListDeliveryStreams")["DeliveryStreamNames"]
    assert STREAM in names


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


def test_put_record_answers_a_record_id(endpoint):
    ensure_stream(endpoint, PUT_STREAM)
    answer = ok(
        endpoint,
        "PutRecord",
        {"DeliveryStreamName": PUT_STREAM, "Record": {"Data": base64_data("ops record")}},
    )
    assert answer["RecordId"]


def test_put_record_batch_answers_every_record(endpoint):
    ensure_stream(endpoint, PUT_STREAM)
    answer = ok(
        endpoint,
        "PutRecordBatch",
        {
            "DeliveryStreamName": PUT_STREAM,
            "Records": [{"Data": base64_data("one")}, {"Data": base64_data("two")}],
        },
    )
    assert answer["FailedPutCount"] == 0
    assert len(answer["RequestResponses"]) == 2
    assert all(item.get("RecordId") for item in answer["RequestResponses"])


def test_update_destination_changes_the_bucket(endpoint):
    described = ensure_stream(endpoint, DEST_STREAM, destination=True)
    destination_id = described["Destinations"][0]["DestinationId"]
    version = int(described["VersionId"])
    target = "arn:aws:s3:::ops-firehose-updated-bucket"
    ok(
        endpoint,
        "UpdateDestination",
        {
            "DeliveryStreamName": DEST_STREAM,
            "DestinationId": destination_id,
            "CurrentDeliveryStreamVersionId": str(version),
            "ExtendedS3DestinationUpdate": {"BucketARN": target},
        },
    )
    updated = ok(endpoint, "DescribeDeliveryStream", {"DeliveryStreamName": DEST_STREAM})["DeliveryStreamDescription"]
    assert updated["Destinations"][0]["ExtendedS3DestinationDescription"]["BucketARN"] == target
    assert int(updated["VersionId"]) == version + 1


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_delivery_stream_is_read_back_by_list_tags(endpoint):
    ensure_stream(endpoint)
    ok(endpoint, "TagDeliveryStream", {"DeliveryStreamName": STREAM, "Tags": [{"Key": "env", "Value": "ops"}]})
    tags = ok(endpoint, "ListTagsForDeliveryStream", {"DeliveryStreamName": STREAM})["Tags"]
    assert {"Key": "env", "Value": "ops"} in tags


def test_untag_delivery_stream_removes_the_key_it_names(endpoint):
    ensure_stream(endpoint)
    ok(endpoint, "TagDeliveryStream", {"DeliveryStreamName": STREAM, "Tags": [{"Key": "doomed", "Value": "yes"}]})
    ok(endpoint, "UntagDeliveryStream", {"DeliveryStreamName": STREAM, "TagKeys": ["doomed"]})
    keys = {tag["Key"] for tag in ok(endpoint, "ListTagsForDeliveryStream", {"DeliveryStreamName": STREAM})["Tags"]}
    assert "doomed" not in keys


def test_list_tags_for_delivery_stream_lists_the_tags(endpoint):
    ensure_stream(endpoint)
    ok(endpoint, "TagDeliveryStream", {"DeliveryStreamName": STREAM, "Tags": [{"Key": "team", "Value": "platform"}]})
    tags = ok(endpoint, "ListTagsForDeliveryStream", {"DeliveryStreamName": STREAM})["Tags"]
    assert {"Key": "team", "Value": "platform"} in tags


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------


def test_start_delivery_stream_encryption_enables_it(endpoint):
    ensure_stream(endpoint, ENC_STREAM)
    ok(endpoint, "StartDeliveryStreamEncryption", {"DeliveryStreamName": ENC_STREAM})
    described = ok(endpoint, "DescribeDeliveryStream", {"DeliveryStreamName": ENC_STREAM})["DeliveryStreamDescription"]
    assert described["DeliveryStreamEncryptionConfiguration"]["Status"] == "ENABLED"


def test_stop_delivery_stream_encryption_disables_it(endpoint):
    ensure_stream(endpoint, ENC_STREAM)
    ok(endpoint, "StartDeliveryStreamEncryption", {"DeliveryStreamName": ENC_STREAM})
    ok(endpoint, "StopDeliveryStreamEncryption", {"DeliveryStreamName": ENC_STREAM})
    described = ok(endpoint, "DescribeDeliveryStream", {"DeliveryStreamName": ENC_STREAM})["DeliveryStreamDescription"]
    assert described["DeliveryStreamEncryptionConfiguration"]["Status"] == "DISABLED"
