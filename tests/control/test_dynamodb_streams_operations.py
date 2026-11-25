"""DynamoDB Streams on the wire: all 4 advertised operations.

Streams shares DynamoDB's `dynamodb` signing name; the `DynamoDBStreams_20120810`
target prefix is what routes it, exactly as the emulator's own router does. A
table with a stream is created through the main DynamoDB API first, then an item
is written so the stream has a record to read.

The item's value changes on every sweep, because a write that changes nothing
emits no stream record — a re-run must still produce one. The table and item are
left in place; nothing is deleted.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
HEADERS = {"Content-Type": "application/x-amz-json-1.1"}

DDB = "DynamoDB_20120810."
STREAMS = "DynamoDBStreams_20120810."

TABLE = "ops-ddb-streams"
ITEM = "ops-stream-item"
VIEW_TYPE = "NEW_AND_OLD_IMAGES"


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def call(endpoint, prefix: str, action: str, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": prefix + action})
    return signed.request(
        endpoint, "dynamodb", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, prefix: str, action: str, **params) -> dict:
    status, text = call(endpoint, prefix, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def ddb(endpoint, action: str, **params) -> dict:
    return ok(endpoint, DDB, action, **params)


def streams(endpoint, action: str, **params) -> dict:
    return ok(endpoint, STREAMS, action, **params)


# ---------------------------------------------------------------------------
# A table with a stream, and one record in it
# ---------------------------------------------------------------------------


def ensure_table(endpoint) -> str:
    """The table and its stream ARN; an existing table is reused, and a re-run
    that finds it without a stream enables one."""
    status, text = call(
        endpoint,
        DDB,
        "CreateTable",
        TableName=TABLE,
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
        StreamSpecification={"StreamEnabled": True, "StreamViewType": VIEW_TYPE},
    )
    assert status in (200, 400), f"CreateTable answered {status}: {text[:400]}"
    if status == 400:
        assert "ResourceInUseException" in text

    table = ddb(endpoint, "DescribeTable", TableName=TABLE)["Table"]
    if not table.get("LatestStreamArn"):
        ddb(
            endpoint,
            "UpdateTable",
            TableName=TABLE,
            StreamSpecification={"StreamEnabled": True, "StreamViewType": VIEW_TYPE},
        )
        table = ddb(endpoint, "DescribeTable", TableName=TABLE)["Table"]
    assert table["LatestStreamArn"]
    return table["LatestStreamArn"]


def write_record(endpoint) -> None:
    """An item write that always changes the item, so it always emits a record."""
    ddb(
        endpoint,
        "PutItem",
        TableName=TABLE,
        Item={"pk": {"S": ITEM}, "run": {"S": str(time.time_ns())}},
    )


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


def test_list_streams_names_the_table_stream(endpoint):
    stream_arn = ensure_table(endpoint)
    write_record(endpoint)
    answer = streams(endpoint, "ListStreams", TableName=TABLE)
    matching = [s for s in answer["Streams"] if s["TableName"] == TABLE]
    assert matching
    assert matching[0]["StreamArn"] == stream_arn


def test_describe_stream_reports_the_shard_and_view_type(endpoint):
    stream_arn = ensure_table(endpoint)
    write_record(endpoint)
    description = streams(endpoint, "DescribeStream", StreamArn=stream_arn)["StreamDescription"]
    assert description["TableName"] == TABLE
    assert description["StreamStatus"] == "ENABLED"
    assert description["StreamViewType"] == VIEW_TYPE
    assert len(description["Shards"]) == 1
    assert description["KeySchema"] == [{"AttributeName": "pk", "KeyType": "HASH"}]


def test_get_shard_iterator_answers_an_opaque_token(endpoint):
    stream_arn = ensure_table(endpoint)
    write_record(endpoint)
    shard_id = streams(endpoint, "DescribeStream", StreamArn=stream_arn)["StreamDescription"]["Shards"][0]["ShardId"]
    answer = streams(
        endpoint,
        "GetShardIterator",
        StreamArn=stream_arn,
        ShardId=shard_id,
        ShardIteratorType="TRIM_HORIZON",
    )
    assert answer["ShardIterator"]


def test_get_records_reads_the_change_it_wrote(endpoint):
    stream_arn = ensure_table(endpoint)
    write_record(endpoint)
    shard_id = streams(endpoint, "DescribeStream", StreamArn=stream_arn)["StreamDescription"]["Shards"][0]["ShardId"]
    iterator = streams(
        endpoint,
        "GetShardIterator",
        StreamArn=stream_arn,
        ShardId=shard_id,
        ShardIteratorType="TRIM_HORIZON",
    )["ShardIterator"]
    answer = streams(endpoint, "GetRecords", ShardIterator=iterator, Limit=1000)
    assert answer["Records"]
    assert answer["NextShardIterator"]
    record = next(
        r
        for r in answer["Records"]
        if r["eventName"] in ("INSERT", "MODIFY")
        and r["dynamodb"]["Keys"]["pk"]["S"] == ITEM
    )
    assert record["dynamodb"]["SequenceNumber"]
    assert record["dynamodb"]["NewImage"]["pk"]["S"] == ITEM
