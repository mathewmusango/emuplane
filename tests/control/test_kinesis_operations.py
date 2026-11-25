"""Kinesis on the wire: every advertised action, driven through the JSON protocol.

A stream created here is left in place; the delete and deregister actions create the
resource of their own that they remove. The shard-changing actions run on a stream
minted for that run, so a second sweep starts from the same shape.
"""

from __future__ import annotations

import base64
import http.client
import json
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
TARGET = "Kinesis_20131202."
HEADERS = {"Content-Type": "application/x-amz-json-1.0"}
MAX_HASH_KEY = (2**128) - 1


def call(endpoint, action: str, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "kinesis", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, action: str, **params) -> dict:
    status, text = call(endpoint, action, **params)
    # A lab sweep re-runs against the streams an earlier sweep deliberately left behind.
    if status == 200:
        return json.loads(text or "{}")
    assert "ResourceInUse" in text, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def create(endpoint, name: str, shard_count: int = 1) -> str:
    """Ensure a stream exists; a lab sweep re-runs against the stream an earlier sweep left."""
    status, text = call(
        endpoint, "CreateStream", StreamName=name, ShardCount=shard_count
    )
    assert status == 200 or "ResourceInUseException" in text, (
        f"CreateStream answered {status}: {text[:400]}"
    )
    return name


def fresh(label: str) -> str:
    """A stream no earlier run has split, merged or resharded."""
    return f"ops-kinesis-{label}-{uuid.uuid4().hex[:8]}"


def arn(endpoint, name: str) -> str:
    return summary(endpoint, name)["StreamARN"]


def summary(endpoint, name: str) -> dict:
    return ok(endpoint, "DescribeStreamSummary", StreamName=name)[
        "StreamDescriptionSummary"
    ]


def shards(endpoint, name: str) -> list[dict]:
    """Every shard of a stream, across ListShards pages."""
    found: list[dict] = []
    params = {"StreamName": name}
    while True:
        page = ok(endpoint, "ListShards", **params)
        found.extend(page["Shards"])
        if "NextToken" not in page:
            return found
        params["NextToken"] = page["NextToken"]


def ensure_consumer(endpoint, stream_arn: str, name: str) -> dict:
    """Register a consumer; a lab sweep re-runs against the consumer an earlier sweep left."""
    status, text = call(
        endpoint, "RegisterStreamConsumer", StreamARN=stream_arn, ConsumerName=name
    )
    if status == 200:
        return json.loads(text)["Consumer"]
    assert "ResourceInUseException" in text, (
        f"RegisterStreamConsumer answered {status}: {text[:400]}"
    )
    return ok(
        endpoint, "DescribeStreamConsumer", StreamARN=stream_arn, ConsumerName=name
    )["ConsumerDescription"]


def data(payload: str) -> str:
    return base64.b64encode(payload.encode()).decode()


def records_for(endpoint, name: str, shard_id: str, sequence: str, limit: int = 1) -> dict:
    """The records at a sequence number, read through a fresh iterator."""
    iterator = ok(
        endpoint,
        "GetShardIterator",
        StreamName=name,
        ShardId=shard_id,
        ShardIteratorType="AT_SEQUENCE_NUMBER",
        StartingSequenceNumber=sequence,
    )["ShardIterator"]
    return ok(endpoint, "GetRecords", ShardIterator=iterator, Limit=limit)


def policy(stream_arn: str, action: str = "kinesis:GetRecords") -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowRead",
                    "Effect": "Allow",
                    "Principal": {"AWS": ACCOUNT},
                    "Action": action,
                    "Resource": stream_arn,
                }
            ],
        }
    )


def test_create_stream_is_read_back_by_list_and_describe(s3_endpoint):
    ok(s3_endpoint, "CreateStream", StreamName="ops-kinesis-created", ShardCount=1)
    assert "ops-kinesis-created" in ok(s3_endpoint, "ListStreams")["StreamNames"]
    described = ok(s3_endpoint, "DescribeStream", StreamName="ops-kinesis-created")["StreamDescription"]
    assert described["StreamName"] == "ops-kinesis-created"


def test_delete_stream_removes_the_stream_it_created(s3_endpoint):
    ok(s3_endpoint, "CreateStream", StreamName="ops-kinesis-deleted", ShardCount=1)
    ok(s3_endpoint, "DeleteStream", StreamName="ops-kinesis-deleted")
    status, text = call(s3_endpoint, "DescribeStream", StreamName="ops-kinesis-deleted")
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_describe_stream_reports_the_shards_and_pages_them(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-described", 2)
    described = ok(s3_endpoint, "DescribeStream", StreamName=name)["StreamDescription"]
    assert described["StreamName"] == name
    assert described["StreamARN"].endswith(f":stream/{name}")
    assert described["StreamStatus"] == "ACTIVE"
    assert described["StreamModeDetails"] == {"StreamMode": "PROVISIONED"}
    assert described["RetentionPeriodHours"] == 24
    assert described["EncryptionType"] == "NONE"
    assert described["HasMoreShards"] is False
    assert len(described["Shards"]) == 2

    first, second = described["Shards"]
    assert first["HashKeyRange"]["StartingHashKey"] == "0"
    assert second["HashKeyRange"]["EndingHashKey"] == str(MAX_HASH_KEY)
    assert int(second["HashKeyRange"]["StartingHashKey"]) == (
        int(first["HashKeyRange"]["EndingHashKey"]) + 1
    )
    assert "EndingSequenceNumber" not in first["SequenceNumberRange"]

    page = ok(s3_endpoint, "DescribeStream", StreamName=name, Limit=1)["StreamDescription"]
    assert page["HasMoreShards"] is True
    assert len(page["Shards"]) == 1
    rest = ok(
        s3_endpoint,
        "DescribeStream",
        StreamName=name,
        Limit=1,
        ExclusiveStartShardId=page["Shards"][0]["ShardId"],
    )["StreamDescription"]
    assert rest["HasMoreShards"] is False
    assert rest["Shards"][0]["ShardId"] == second["ShardId"]


def test_describe_stream_summary_reports_the_stream_counters(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-summarised")
    described = summary(s3_endpoint, name)
    assert described["StreamName"] == name
    assert described["StreamARN"].endswith(f":stream/{name}")
    assert described["StreamStatus"] == "ACTIVE"
    assert described["OpenShardCount"] == 1
    assert described["ConsumerCount"] == 0
    assert described["RetentionPeriodHours"] == 24
    assert described["EncryptionType"] == "NONE"
    assert described["EnhancedMonitoring"] == [{"ShardLevelMetrics": []}]
    assert isinstance(described["StreamCreationTimestamp"], int)


def test_list_shards_pages_through_a_stream(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-described", 2)
    page = ok(s3_endpoint, "ListShards", StreamName=name, MaxResults=1)
    assert len(page["Shards"]) == 1
    assert "NextToken" in page
    rest = ok(
        s3_endpoint,
        "ListShards",
        StreamName=name,
        MaxResults=1,
        NextToken=page["NextToken"],
    )
    assert len(rest["Shards"]) == 1
    assert "NextToken" not in rest
    assert [page["Shards"][0]["ShardId"], rest["Shards"][0]["ShardId"]] == [
        "shardId-000000000000",
        "shardId-000000000001",
    ]
    for shard in page["Shards"] + rest["Shards"]:
        assert shard["HashKeyRange"]
        assert shard["SequenceNumberRange"]["StartingSequenceNumber"].isdigit()


def test_put_record_is_read_back_by_get_records(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-records")
    marker = uuid.uuid4().hex
    key = f"pk-{marker}"
    placed = ok(
        s3_endpoint,
        "PutRecord",
        StreamName=name,
        PartitionKey=key,
        Data=data(f"put-record-{marker}"),
    )
    assert placed["ShardId"] == "shardId-000000000000"
    assert placed["SequenceNumber"].isdigit()
    assert placed["EncryptionType"] == "NONE"

    found = records_for(s3_endpoint, name, placed["ShardId"], placed["SequenceNumber"])
    assert found["Records"][0]["SequenceNumber"] == placed["SequenceNumber"]
    assert found["Records"][0]["PartitionKey"] == key
    assert base64.b64decode(found["Records"][0]["Data"]).decode() == f"put-record-{marker}"


def test_put_records_writes_every_record_of_the_batch(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-batch")
    marker = uuid.uuid4().hex
    keys = [f"pk-{marker}-{index}" for index in range(3)]
    payloads = [f"batch-{marker}-{index}" for index in range(3)]
    result = ok(
        s3_endpoint,
        "PutRecords",
        StreamName=name,
        Records=[
            {"PartitionKey": key, "Data": data(payload)}
            for key, payload in zip(keys, payloads)
        ],
    )
    assert result["FailedRecordCount"] == 0
    assert len(result["Records"]) == 3
    assert len({record["SequenceNumber"] for record in result["Records"]}) == 3
    assert result["EncryptionType"] == "NONE"

    first = result["Records"][0]
    found = records_for(s3_endpoint, name, first["ShardId"], first["SequenceNumber"])
    assert found["Records"][0]["SequenceNumber"] == first["SequenceNumber"]
    assert found["Records"][0]["PartitionKey"] == keys[0]
    assert base64.b64decode(found["Records"][0]["Data"]).decode() == payloads[0]


def test_get_shard_iterator_returns_an_iterator_for_the_shard(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-records")
    iterator = ok(
        s3_endpoint,
        "GetShardIterator",
        StreamName=name,
        ShardId="shardId-000000000000",
        ShardIteratorType="LATEST",
    )["ShardIterator"]
    assert isinstance(iterator, str) and iterator

    status, text = call(
        s3_endpoint,
        "GetShardIterator",
        StreamName=name,
        ShardId="shardId-999999999999",
        ShardIteratorType="LATEST",
    )
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_get_records_reads_from_the_iterator_and_advances_it(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-records")
    marker = uuid.uuid4().hex
    first = ok(
        s3_endpoint,
        "PutRecord",
        StreamName=name,
        PartitionKey=f"pk-{marker}-a",
        Data=data(f"first-{marker}"),
    )
    second = ok(
        s3_endpoint,
        "PutRecord",
        StreamName=name,
        PartitionKey=f"pk-{marker}-b",
        Data=data(f"second-{marker}"),
    )
    iterator = ok(
        s3_endpoint,
        "GetShardIterator",
        StreamName=name,
        ShardId=first["ShardId"],
        ShardIteratorType="AT_SEQUENCE_NUMBER",
        StartingSequenceNumber=first["SequenceNumber"],
    )["ShardIterator"]
    page = ok(s3_endpoint, "GetRecords", ShardIterator=iterator, Limit=1)
    assert len(page["Records"]) == 1
    assert page["Records"][0]["SequenceNumber"] == first["SequenceNumber"]
    assert page["MillisBehindLatest"] >= 0

    following = ok(
        s3_endpoint, "GetRecords", ShardIterator=page["NextShardIterator"], Limit=1
    )
    assert following["Records"][0]["SequenceNumber"] == second["SequenceNumber"]

    status, text = call(s3_endpoint, "GetRecords", ShardIterator="not-a-shard-iterator")
    assert status == 400, text[:300]
    assert "ExpiredIteratorException" in text


def test_increase_stream_retention_period_is_read_back(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-retention")
    ok(
        s3_endpoint,
        "IncreaseStreamRetentionPeriod",
        StreamName=name,
        RetentionPeriodHours=48,
    )
    assert summary(s3_endpoint, name)["RetentionPeriodHours"] == 48


def test_decrease_stream_retention_period_restores_the_default(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-retention")
    ok(
        s3_endpoint,
        "IncreaseStreamRetentionPeriod",
        StreamName=name,
        RetentionPeriodHours=48,
    )
    ok(
        s3_endpoint,
        "DecreaseStreamRetentionPeriod",
        StreamName=name,
        RetentionPeriodHours=24,
    )
    assert summary(s3_endpoint, name)["RetentionPeriodHours"] == 24


def test_merge_shards_closes_the_parents_and_adds_one_child(s3_endpoint):
    name = create(s3_endpoint, fresh("merged"), 2)
    parents = sorted(shard["ShardId"] for shard in shards(s3_endpoint, name))
    ok(
        s3_endpoint,
        "MergeShards",
        StreamName=name,
        ShardToMerge=parents[0],
        AdjacentShardToMerge=parents[1],
    )
    after = {shard["ShardId"]: shard for shard in shards(s3_endpoint, name)}
    assert len(after) == 3
    for parent in parents:
        assert after[parent]["SequenceNumberRange"]["EndingSequenceNumber"].isdigit()
    (child,) = [shard for sid, shard in after.items() if sid not in parents]
    assert child["ParentShardId"] == parents[0]
    assert child["AdjacentParentShardId"] == parents[1]
    assert child["HashKeyRange"] == {
        "StartingHashKey": "0",
        "EndingHashKey": str(MAX_HASH_KEY),
    }


def test_split_shard_closes_the_parent_and_adds_two_children(s3_endpoint):
    name = create(s3_endpoint, fresh("split"))
    (parent,) = shards(s3_endpoint, name)
    split_point = (MAX_HASH_KEY + 1) // 2
    ok(
        s3_endpoint,
        "SplitShard",
        StreamName=name,
        ShardToSplit=parent["ShardId"],
        NewStartingHashKey=str(split_point),
    )
    after = {shard["ShardId"]: shard for shard in shards(s3_endpoint, name)}
    assert len(after) == 3
    assert after[parent["ShardId"]]["SequenceNumberRange"]["EndingSequenceNumber"].isdigit()
    children = sorted(
        (shard for sid, shard in after.items() if sid != parent["ShardId"]),
        key=lambda shard: int(shard["HashKeyRange"]["StartingHashKey"]),
    )
    assert [child["ParentShardId"] for child in children] == [
        parent["ShardId"],
        parent["ShardId"],
    ]
    assert children[0]["HashKeyRange"] == {
        "StartingHashKey": parent["HashKeyRange"]["StartingHashKey"],
        "EndingHashKey": str(split_point - 1),
    }
    assert children[1]["HashKeyRange"] == {
        "StartingHashKey": str(split_point),
        "EndingHashKey": parent["HashKeyRange"]["EndingHashKey"],
    }


def test_update_shard_count_reaches_the_target(s3_endpoint):
    name = create(s3_endpoint, fresh("resharded"), 2)
    result = ok(s3_endpoint, "UpdateShardCount", StreamName=name, TargetShardCount=3)
    assert result["StreamName"] == name
    assert result["StreamARN"].endswith(f":stream/{name}")
    assert result["CurrentShardCount"] == 2
    assert result["TargetShardCount"] == 3

    open_shards = sorted(
        (
            shard
            for shard in shards(s3_endpoint, name)
            if "EndingSequenceNumber" not in shard["SequenceNumberRange"]
        ),
        key=lambda shard: int(shard["HashKeyRange"]["StartingHashKey"]),
    )
    assert len(open_shards) == 3
    assert open_shards[0]["HashKeyRange"]["StartingHashKey"] == "0"
    assert open_shards[-1]["HashKeyRange"]["EndingHashKey"] == str(MAX_HASH_KEY)
    for previous, following in zip(open_shards, open_shards[1:]):
        assert int(following["HashKeyRange"]["StartingHashKey"]) == (
            int(previous["HashKeyRange"]["EndingHashKey"]) + 1
        )


def test_start_stream_encryption_is_read_back(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-encrypted")
    ok(
        s3_endpoint,
        "StartStreamEncryption",
        StreamName=name,
        EncryptionType="KMS",
        KeyId="alias/aws/kinesis",
    )
    encrypted = summary(s3_endpoint, name)
    assert encrypted["EncryptionType"] == "KMS"
    assert encrypted["KeyId"] == "alias/aws/kinesis"


def test_stop_stream_encryption_returns_the_stream_to_none(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-encrypted")
    ok(
        s3_endpoint,
        "StartStreamEncryption",
        StreamName=name,
        EncryptionType="KMS",
        KeyId="alias/aws/kinesis",
    )
    ok(
        s3_endpoint,
        "StopStreamEncryption",
        StreamName=name,
        EncryptionType="KMS",
        KeyId="alias/aws/kinesis",
    )
    stopped = summary(s3_endpoint, name)
    assert stopped["EncryptionType"] == "NONE"
    assert "KeyId" not in stopped


def test_enable_enhanced_monitoring_is_read_back(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-monitored")
    metrics = ["IncomingBytes", "OutgoingBytes"]
    result = ok(
        s3_endpoint, "EnableEnhancedMonitoring", StreamName=name, ShardLevelMetrics=metrics
    )
    assert set(metrics) <= set(result["DesiredShardLevelMetrics"])
    assert set(metrics) <= set(
        summary(s3_endpoint, name)["EnhancedMonitoring"][0]["ShardLevelMetrics"]
    )


def test_disable_enhanced_monitoring_removes_the_metric(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-monitored")
    ok(
        s3_endpoint,
        "EnableEnhancedMonitoring",
        StreamName=name,
        ShardLevelMetrics=["IncomingBytes", "OutgoingBytes"],
    )
    result = ok(
        s3_endpoint,
        "DisableEnhancedMonitoring",
        StreamName=name,
        ShardLevelMetrics=["IncomingBytes"],
    )
    assert "IncomingBytes" not in result["DesiredShardLevelMetrics"]
    assert "OutgoingBytes" in result["DesiredShardLevelMetrics"]
    assert "IncomingBytes" not in summary(s3_endpoint, name)["EnhancedMonitoring"][0][
        "ShardLevelMetrics"
    ]


def test_register_stream_consumer_is_read_back(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-consumers")
    stream_arn = arn(s3_endpoint, name)
    consumer = ensure_consumer(s3_endpoint, stream_arn, "ops-kinesis-consumer")
    assert consumer["ConsumerName"] == "ops-kinesis-consumer"
    assert consumer["ConsumerARN"].startswith(
        f"{stream_arn}/consumer/ops-kinesis-consumer:"
    )
    assert consumer["ConsumerStatus"] == "ACTIVE"
    described = ok(
        s3_endpoint, "DescribeStreamConsumer", ConsumerARN=consumer["ConsumerARN"]
    )["ConsumerDescription"]
    assert described["ConsumerARN"] == consumer["ConsumerARN"]
    assert described["StreamARN"] == stream_arn


def test_deregister_stream_consumer_removes_the_consumer_it_registered(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-consumers")
    stream_arn = arn(s3_endpoint, name)

    by_arn = ensure_consumer(s3_endpoint, stream_arn, fresh("consumer-gone"))
    ok(s3_endpoint, "DeregisterStreamConsumer", ConsumerARN=by_arn["ConsumerARN"])
    status, text = call(
        s3_endpoint, "DescribeStreamConsumer", ConsumerARN=by_arn["ConsumerARN"]
    )
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text

    by_name = ensure_consumer(s3_endpoint, stream_arn, fresh("consumer-gone"))
    ok(
        s3_endpoint,
        "DeregisterStreamConsumer",
        StreamARN=stream_arn,
        ConsumerName=by_name["ConsumerName"],
    )
    status, text = call(
        s3_endpoint,
        "DescribeStreamConsumer",
        StreamARN=stream_arn,
        ConsumerName=by_name["ConsumerName"],
    )
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_list_stream_consumers_pages_and_names_them(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-consumers")
    stream_arn = arn(s3_endpoint, name)
    first = ensure_consumer(s3_endpoint, stream_arn, "ops-kinesis-consumer-a")
    second = ensure_consumer(s3_endpoint, stream_arn, "ops-kinesis-consumer-b")

    found: list[dict] = []
    params = {"StreamARN": stream_arn, "MaxResults": 1}
    while True:
        page = ok(s3_endpoint, "ListStreamConsumers", **params)
        found.extend(page["Consumers"])
        if "NextToken" not in page:
            break
        params["NextToken"] = page["NextToken"]
    assert {first["ConsumerName"], second["ConsumerName"]} <= {
        consumer["ConsumerName"] for consumer in found
    }
    for consumer in found:
        assert consumer["ConsumerARN"].startswith(stream_arn)
        assert consumer["ConsumerStatus"] == "ACTIVE"
        assert isinstance(consumer["ConsumerCreationTimestamp"], int)


def test_describe_stream_consumer_reads_by_arn_and_by_name(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-consumers")
    stream_arn = arn(s3_endpoint, name)
    consumer = ensure_consumer(s3_endpoint, stream_arn, "ops-kinesis-consumer-a")
    by_arn = ok(
        s3_endpoint, "DescribeStreamConsumer", ConsumerARN=consumer["ConsumerARN"]
    )["ConsumerDescription"]
    by_name = ok(
        s3_endpoint,
        "DescribeStreamConsumer",
        StreamARN=stream_arn,
        ConsumerName="ops-kinesis-consumer-a",
    )["ConsumerDescription"]
    assert by_name == by_arn
    assert by_arn["ConsumerStatus"] == "ACTIVE"
    assert by_arn["ConsumerCreationTimestamp"] == consumer["ConsumerCreationTimestamp"]


def stream_messages(endpoint, action: str, count: int, **params) -> list[dict]:
    """The first `count` eventstream messages of a long-lived response, then hang up.

    `SubscribeToShard` is held open for up to 300 seconds, so a body read to EOF
    would wait it out. Reading message by message and closing the connection is
    what a real subscriber does at shutdown, and it works against a lab too.
    """
    url = urlsplit(endpoint)
    stamp = datetime.now(timezone.utc)
    body = json.dumps(params).encode()
    headers = {
        "Host": f"{url.hostname}:{url.port or 80}",
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={ACCOUNT}/{stamp:%Y%m%d}/{REGION}/kinesis"
            "/aws4_request, SignedHeaders=host, Signature=local"
        ),
        "x-amz-date": stamp.strftime("%Y%m%dT%H%M%SZ"),
        "Content-Length": str(len(body)),
        "Content-Type": "application/x-amz-json-1.0",
        "X-Amz-Target": TARGET + action,
    }
    connection = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=30)
    try:
        connection.request("POST", "/", body=body, headers=headers)
        response = connection.getresponse()
        assert response.status == 200, response.read()[:400]
        messages = []
        for _ in range(count):
            prefix = response.read(4)
            assert len(prefix) == 4, prefix
            total = int.from_bytes(prefix, "big")
            messages.append(eventstream(prefix + response.read(total - 4)))
        return messages
    finally:
        connection.close()


def eventstream(message: bytes) -> dict:
    """One `application/vnd.amazon.eventstream` message as `{":event-type": payload}`."""
    headers_len = int.from_bytes(message[4:8], "big")
    index, stop = 12, 12 + headers_len
    headers = {}
    while index < stop:
        name_len = message[index]
        index += 1
        name = message[index:index + name_len].decode("ascii")
        index += name_len
        kind = message[index]
        index += 1
        assert kind == 7, f"header {name} has type {kind}, not a string"
        size = int.from_bytes(message[index:index + 2], "big")
        index += 2
        headers[name] = message[index:index + size].decode("utf-8")
        index += size
    return {headers.get(":event-type", ""): json.loads(message[stop:-4] or b"{}")}


def test_subscribe_to_shard_streams_the_backlog(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-subscribe")
    stream_arn = arn(s3_endpoint, name)
    consumer = ensure_consumer(s3_endpoint, stream_arn, "ops-kinesis-consumer-stream")
    marker = uuid.uuid4().hex
    key = f"subscribe-{marker}"
    ok(s3_endpoint, "PutRecord", StreamName=name, PartitionKey=key, Data=data(key))

    initial, pushed = stream_messages(
        s3_endpoint,
        "SubscribeToShard",
        2,
        ConsumerARN=consumer["ConsumerARN"],
        ShardId="shardId-000000000000",
        StartingPosition={"Type": "TRIM_HORIZON"},
    )
    assert "initial-response" in initial
    event = pushed["SubscribeToShardEvent"]
    assert any(
        record["PartitionKey"] == key
        and base64.b64decode(record["Data"]).decode() == key
        for record in event["Records"]
    )
    assert event["ContinuationSequenceNumber"].isdigit()


def test_add_tags_to_stream_is_read_back(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-tagged")
    ok(
        s3_endpoint,
        "AddTagsToStream",
        StreamName=name,
        Tags={"team": "platform", "env": "lab"},
    )
    tags = {
        tag["Key"]: tag["Value"]
        for tag in ok(s3_endpoint, "ListTagsForStream", StreamName=name)["Tags"]
    }
    assert tags["team"] == "platform"
    assert tags["env"] == "lab"


def test_remove_tags_from_stream_leaves_the_other_tag(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-tag-removal")
    marker = uuid.uuid4().hex[:8]
    kept, dropped = f"kept-{marker}", f"dropped-{marker}"
    ok(
        s3_endpoint,
        "AddTagsToStream",
        StreamName=name,
        Tags={kept: "one", dropped: "two"},
    )
    ok(s3_endpoint, "RemoveTagsFromStream", StreamName=name, TagKeys=[dropped])
    tags = {
        tag["Key"]: tag["Value"]
        for tag in ok(s3_endpoint, "ListTagsForStream", StreamName=name)["Tags"]
    }
    assert tags[kept] == "one"
    assert dropped not in tags


def test_list_tags_for_stream_pages_the_tags(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-tagged")
    ok(
        s3_endpoint,
        "AddTagsToStream",
        StreamName=name,
        Tags={"team": "platform", "env": "lab"},
    )
    page = ok(s3_endpoint, "ListTagsForStream", StreamName=name, Limit=1)
    assert page["HasMoreTags"] is True
    (only,) = page["Tags"]
    rest = ok(
        s3_endpoint,
        "ListTagsForStream",
        StreamName=name,
        Limit=1,
        ExclusiveStartTagKey=only["Key"],
    )
    assert rest["HasMoreTags"] is False
    assert {only["Key"], rest["Tags"][0]["Key"]} == {"team", "env"}


def test_put_resource_policy_is_read_back_by_get_resource_policy(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-policy")
    stream_arn = arn(s3_endpoint, name)
    ok(s3_endpoint, "PutResourcePolicy", ResourceARN=stream_arn, Policy=policy(stream_arn))
    stored = json.loads(
        ok(s3_endpoint, "GetResourcePolicy", ResourceARN=stream_arn)["Policy"]
    )
    (statement,) = stored["Statement"]
    assert stored["Version"] == "2012-10-17"
    assert statement["Resource"] == stream_arn
    assert statement["Action"] == "kinesis:GetRecords"
    assert statement["Principal"] == {"AWS": f"arn:aws:iam::{ACCOUNT}:root"}


def test_get_resource_policy_answers_the_stored_document(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-policy")
    stream_arn = arn(s3_endpoint, name)
    ok(
        s3_endpoint,
        "PutResourcePolicy",
        ResourceARN=stream_arn,
        Policy=policy(stream_arn, "kinesis:DescribeStream"),
    )
    stored = json.loads(
        ok(s3_endpoint, "GetResourcePolicy", ResourceARN=stream_arn)["Policy"]
    )
    assert stored["Statement"][0]["Action"] == "kinesis:DescribeStream"


def test_delete_resource_policy_removes_the_policy_it_created(s3_endpoint):
    name = create(s3_endpoint, "ops-kinesis-policy")
    stream_arn = arn(s3_endpoint, name)
    ok(s3_endpoint, "PutResourcePolicy", ResourceARN=stream_arn, Policy=policy(stream_arn))
    ok(s3_endpoint, "DeleteResourcePolicy", ResourceARN=stream_arn)
    assert ok(s3_endpoint, "GetResourcePolicy", ResourceARN=stream_arn)["Policy"] == "{}"

    status, text = call(s3_endpoint, "DeleteResourcePolicy", ResourceARN=stream_arn)
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text
