"""DynamoDB on the wire: every advertised operation, driven through the JSON protocol.

A table created here is left in place, and a read proves what a write stored. The two
deletes create their own target (a table, an item), and the Kinesis destination tests
create a stream of their own.
"""

from __future__ import annotations

import json

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
TARGET = "DynamoDB_20120810."
HEADERS = {"Content-Type": "application/x-amz-json-1.0"}
# A streaming destination names a stream, so the tests create one and read its ARN back.
KINESIS = "Kinesis_20131202."
STREAM = "ops-dynamodb-stream"


def _request(endpoint, service: str, target: str, action: str, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": target + action})
    return signed.request(
        endpoint, service, ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def call(endpoint, action: str, **params):
    return _request(endpoint, "dynamodb", TARGET, action, **params)


def ok(endpoint, action: str, **params) -> dict:
    status, text = call(endpoint, action, **params)
    # A lab sweep re-runs against the tables an earlier sweep deliberately left behind.
    if status == 200:
        return json.loads(text or "{}")
    assert "ResourceInUseException" in text, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def create(endpoint, name: str) -> None:
    ok(
        endpoint,
        "CreateTable",
        TableName=name,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def write(endpoint, table: str, item_id: str, **attrs) -> dict:
    """An item set by UpdateItem, so a re-run stores the same values instead of a second copy."""
    names = {f"#a{index}": name for index, name in enumerate(attrs)}
    values = {f":a{index}": {"S": value} for index, value in enumerate(attrs.values())}
    clause = ", ".join(f"{name} = {value}" for name, value in zip(names, values))
    return ok(
        endpoint,
        "UpdateItem",
        TableName=table,
        Key={"id": {"S": item_id}},
        UpdateExpression=f"SET {clause}",
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )


def stream_arn(endpoint) -> str:
    """The stream a destination names: created once, then described so the ARN is the emulator's own."""
    status, text = _request(
        endpoint, "kinesis", KINESIS, "CreateStream", StreamName=STREAM, ShardCount=1
    )
    assert status == 200 or "ResourceInUseException" in text, (
        f"CreateStream answered {status}: {text[:400]}"
    )
    status, text = _request(endpoint, "kinesis", KINESIS, "DescribeStream", StreamName=STREAM)
    assert status == 200, f"DescribeStream answered {status}: {text[:400]}"
    return json.loads(text)["StreamDescription"]["StreamARN"]


def test_create_table_is_read_back_by_list_and_describe(s3_endpoint):
    create(s3_endpoint, "ops-dynamodb-created")
    assert "ops-dynamodb-created" in ok(s3_endpoint, "ListTables")["TableNames"]
    described = ok(s3_endpoint, "DescribeTable", TableName="ops-dynamodb-created")["Table"]
    assert described["TableName"] == "ops-dynamodb-created"


def test_put_item_is_read_back_by_scan(s3_endpoint):
    create(s3_endpoint, "ops-dynamodb-items")
    ok(
        s3_endpoint,
        "PutItem",
        TableName="ops-dynamodb-items",
        Item={"id": {"S": "one"}, "value": {"S": "kept"}},
    )
    items = ok(s3_endpoint, "Scan", TableName="ops-dynamodb-items")["Items"]
    assert {"id": {"S": "one"}, "value": {"S": "kept"}} in items


def test_delete_table_removes_the_table_it_created(s3_endpoint):
    create(s3_endpoint, "ops-dynamodb-deleted")
    ok(s3_endpoint, "DeleteTable", TableName="ops-dynamodb-deleted")
    status, text = call(s3_endpoint, "DescribeTable", TableName="ops-dynamodb-deleted")
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_describe_table_reports_the_key_schema_and_status(s3_endpoint):
    create(s3_endpoint, "ops-dynamodb-described")
    table = ok(s3_endpoint, "DescribeTable", TableName="ops-dynamodb-described")["Table"]
    assert table["TableStatus"] == "ACTIVE"
    assert table["KeySchema"] == [{"AttributeName": "id", "KeyType": "HASH"}]
    assert table["AttributeDefinitions"] == [{"AttributeName": "id", "AttributeType": "S"}]
    assert table["BillingModeSummary"]["BillingMode"] == "PAY_PER_REQUEST"
    assert table["TableArn"].endswith("/ops-dynamodb-described")


def test_update_table_enables_a_stream_on_the_table_it_created(s3_endpoint):
    create(s3_endpoint, "ops-dynamodb-updated")
    spec = {"StreamEnabled": True, "StreamViewType": "NEW_AND_OLD_IMAGES"}
    updated = ok(
        s3_endpoint,
        "UpdateTable",
        TableName="ops-dynamodb-updated",
        StreamSpecification=spec,
    )["TableDescription"]
    assert updated["StreamSpecification"] == spec
    described = ok(s3_endpoint, "DescribeTable", TableName="ops-dynamodb-updated")["Table"]
    assert described["StreamSpecification"] == spec
    assert described["LatestStreamArn"].startswith(described["TableArn"] + "/stream/")


def test_get_item_returns_the_item_and_nothing_for_a_missing_key(s3_endpoint):
    create(s3_endpoint, "ops-dynamodb-get")
    write(s3_endpoint, "ops-dynamodb-get", "one", value="kept")
    found = ok(s3_endpoint, "GetItem", TableName="ops-dynamodb-get", Key={"id": {"S": "one"}})
    assert found["Item"] == {"id": {"S": "one"}, "value": {"S": "kept"}}
    absent = ok(
        s3_endpoint, "GetItem", TableName="ops-dynamodb-get", Key={"id": {"S": "absent"}}
    )
    assert "Item" not in absent


def test_delete_item_returns_the_item_it_removed(s3_endpoint):
    create(s3_endpoint, "ops-dynamodb-deleted-item")
    write(s3_endpoint, "ops-dynamodb-deleted-item", "one", value="doomed")
    deleted = ok(
        s3_endpoint,
        "DeleteItem",
        TableName="ops-dynamodb-deleted-item",
        Key={"id": {"S": "one"}},
        ReturnValues="ALL_OLD",
    )
    assert deleted["Attributes"] == {"id": {"S": "one"}, "value": {"S": "doomed"}}
    gone = ok(
        s3_endpoint,
        "GetItem",
        TableName="ops-dynamodb-deleted-item",
        Key={"id": {"S": "one"}},
    )
    assert "Item" not in gone


def test_update_item_sets_an_attribute_read_back_by_get(s3_endpoint):
    create(s3_endpoint, "ops-dynamodb-updated-item")
    set_new = write(s3_endpoint, "ops-dynamodb-updated-item", "one", value="first")
    assert set_new["Attributes"]["value"] == {"S": "first"}
    changed = ok(
        s3_endpoint,
        "UpdateItem",
        TableName="ops-dynamodb-updated-item",
        Key={"id": {"S": "one"}},
        UpdateExpression="SET #v = :v",
        ExpressionAttributeNames={"#v": "value"},
        ExpressionAttributeValues={":v": {"S": "second"}},
        ReturnValues="UPDATED_NEW",
    )
    assert changed["Attributes"] == {"value": {"S": "second"}}
    read = ok(
        s3_endpoint,
        "GetItem",
        TableName="ops-dynamodb-updated-item",
        Key={"id": {"S": "one"}},
    )["Item"]
    assert read["value"] == {"S": "second"}


def test_query_returns_only_the_partition_it_asked_for(s3_endpoint):
    create(s3_endpoint, "ops-dynamodb-query")
    write(s3_endpoint, "ops-dynamodb-query", "one", payload="first")
    write(s3_endpoint, "ops-dynamodb-query", "two", payload="second")
    result = ok(
        s3_endpoint,
        "Query",
        TableName="ops-dynamodb-query",
        KeyConditionExpression="id = :id",
        ExpressionAttributeValues={":id": {"S": "one"}},
    )
    assert result["Count"] == 1
    assert result["Items"] == [{"id": {"S": "one"}, "payload": {"S": "first"}}]
    empty = ok(
        s3_endpoint,
        "Query",
        TableName="ops-dynamodb-query",
        KeyConditionExpression="id = :id",
        ExpressionAttributeValues={":id": {"S": "absent"}},
    )
    assert empty["Count"] == 0 and empty["Items"] == []


def test_batch_write_item_puts_and_deletes_in_one_call(s3_endpoint):
    table = "ops-dynamodb-batch-write"
    create(s3_endpoint, table)
    write(s3_endpoint, table, "stale", payload="superseded")
    result = ok(
        s3_endpoint,
        "BatchWriteItem",
        RequestItems={
            table: [
                {"PutRequest": {"Item": {"id": {"S": "fresh"}, "payload": {"S": "kept"}}}},
                {"DeleteRequest": {"Key": {"id": {"S": "stale"}}}},
            ]
        },
    )
    assert result["UnprocessedItems"] == {}
    assert ok(s3_endpoint, "GetItem", TableName=table, Key={"id": {"S": "fresh"}})["Item"] == {
        "id": {"S": "fresh"},
        "payload": {"S": "kept"},
    }
    assert "Item" not in ok(s3_endpoint, "GetItem", TableName=table, Key={"id": {"S": "stale"}})


def test_batch_get_item_returns_every_key_that_exists(s3_endpoint):
    table = "ops-dynamodb-batch-get"
    create(s3_endpoint, table)
    write(s3_endpoint, table, "one", payload="first")
    write(s3_endpoint, table, "two", payload="second")
    responses = ok(
        s3_endpoint,
        "BatchGetItem",
        RequestItems={
            table: {
                "Keys": [
                    {"id": {"S": "one"}},
                    {"id": {"S": "two"}},
                    {"id": {"S": "absent"}},
                ]
            }
        },
    )["Responses"]
    assert sorted(item["id"]["S"] for item in responses[table]) == ["one", "two"]


def test_transact_write_items_writes_every_item_in_the_transaction(s3_endpoint):
    table = "ops-dynamodb-transact-write"
    create(s3_endpoint, table)
    ok(
        s3_endpoint,
        "TransactWriteItems",
        TransactItems=[
            {
                "Update": {
                    "TableName": table,
                    "Key": {"id": {"S": item_id}},
                    "UpdateExpression": "SET #p = :p",
                    "ExpressionAttributeNames": {"#p": "payload"},
                    "ExpressionAttributeValues": {":p": {"S": payload}},
                }
            }
            for item_id, payload in (("one", "first"), ("two", "second"))
        ],
    )
    for item_id, payload in (("one", "first"), ("two", "second")):
        item = ok(s3_endpoint, "GetItem", TableName=table, Key={"id": {"S": item_id}})["Item"]
        assert item["payload"] == {"S": payload}


def test_transact_get_items_answers_in_request_order(s3_endpoint):
    table = "ops-dynamodb-transact-get"
    create(s3_endpoint, table)
    write(s3_endpoint, table, "one", payload="first")
    responses = ok(
        s3_endpoint,
        "TransactGetItems",
        TransactItems=[
            {"Get": {"TableName": table, "Key": {"id": {"S": "one"}}}},
            {"Get": {"TableName": table, "Key": {"id": {"S": "absent"}}}},
        ],
    )["Responses"]
    assert responses[0]["Item"]["payload"] == {"S": "first"}
    assert responses[1] == {}


def test_describe_time_to_live_reports_disabled_before_it_is_set(s3_endpoint):
    create(s3_endpoint, "ops-dynamodb-ttl-unset")
    described = ok(
        s3_endpoint, "DescribeTimeToLive", TableName="ops-dynamodb-ttl-unset"
    )["TimeToLiveDescription"]
    assert described["TimeToLiveStatus"] == "DISABLED"
    assert "AttributeName" not in described


def test_update_time_to_live_is_read_back_by_describe(s3_endpoint):
    table = "ops-dynamodb-ttl-set"
    create(s3_endpoint, table)
    spec = {"Enabled": True, "AttributeName": "expires_at"}
    updated = ok(s3_endpoint, "UpdateTimeToLive", TableName=table, TimeToLiveSpecification=spec)
    assert updated["TimeToLiveSpecification"] == spec
    described = ok(s3_endpoint, "DescribeTimeToLive", TableName=table)["TimeToLiveDescription"]
    assert described["TimeToLiveStatus"] == "ENABLED"
    assert described["AttributeName"] == "expires_at"


def test_describe_continuous_backups_reports_recovery_disabled(s3_endpoint):
    create(s3_endpoint, "ops-dynamodb-pitr-unset")
    described = ok(
        s3_endpoint, "DescribeContinuousBackups", TableName="ops-dynamodb-pitr-unset"
    )["ContinuousBackupsDescription"]
    assert described["ContinuousBackupsStatus"] == "ENABLED"
    recovery = described["PointInTimeRecoveryDescription"]
    assert recovery["PointInTimeRecoveryStatus"] == "DISABLED"


def test_update_continuous_backups_is_read_back_by_describe(s3_endpoint):
    table = "ops-dynamodb-pitr-set"
    create(s3_endpoint, table)
    updated = ok(
        s3_endpoint,
        "UpdateContinuousBackups",
        TableName=table,
        PointInTimeRecoverySpecification={"PointInTimeRecoveryEnabled": True},
    )["ContinuousBackupsDescription"]
    assert updated["PointInTimeRecoveryDescription"]["PointInTimeRecoveryStatus"] == "ENABLED"
    described = ok(s3_endpoint, "DescribeContinuousBackups", TableName=table)[
        "ContinuousBackupsDescription"
    ]
    recovery = described["PointInTimeRecoveryDescription"]
    assert recovery["PointInTimeRecoveryStatus"] == "ENABLED"
    assert recovery["RecoveryPeriodInDays"] == 35


def test_describe_endpoints_answers_an_address_and_a_cache_period(s3_endpoint):
    endpoints = ok(s3_endpoint, "DescribeEndpoints")["Endpoints"]
    assert endpoints, "DescribeEndpoints answered no endpoint"
    assert isinstance(endpoints[0]["Address"], str) and endpoints[0]["Address"]
    assert isinstance(endpoints[0]["CachePeriodInMinutes"], int)
    assert endpoints[0]["CachePeriodInMinutes"] > 0


def test_tag_resource_is_read_back_by_list_tags_of_resource(s3_endpoint):
    table = "ops-dynamodb-tagged"
    create(s3_endpoint, table)
    arn = ok(s3_endpoint, "DescribeTable", TableName=table)["Table"]["TableArn"]
    ok(
        s3_endpoint,
        "TagResource",
        ResourceArn=arn,
        Tags=[{"Key": "team", "Value": "ops"}, {"Key": "stage", "Value": "test"}],
    )
    tags = ok(s3_endpoint, "ListTagsOfResource", ResourceArn=arn)["Tags"]
    assert {tag["Key"]: tag["Value"] for tag in tags} == {"team": "ops", "stage": "test"}


def test_untag_resource_removes_only_the_key_it_names(s3_endpoint):
    table = "ops-dynamodb-untagged"
    create(s3_endpoint, table)
    arn = ok(s3_endpoint, "DescribeTable", TableName=table)["Table"]["TableArn"]
    ok(
        s3_endpoint,
        "TagResource",
        ResourceArn=arn,
        Tags=[{"Key": "team", "Value": "ops"}, {"Key": "stage", "Value": "test"}],
    )
    ok(s3_endpoint, "UntagResource", ResourceArn=arn, TagKeys=["stage"])
    tags = ok(s3_endpoint, "ListTagsOfResource", ResourceArn=arn)["Tags"]
    assert [tag["Key"] for tag in tags] == ["team"]


def test_list_tags_of_resource_answers_none_for_an_untagged_table(s3_endpoint):
    create(s3_endpoint, "ops-dynamodb-tagless")
    arn = ok(s3_endpoint, "DescribeTable", TableName="ops-dynamodb-tagless")["Table"]["TableArn"]
    assert ok(s3_endpoint, "ListTagsOfResource", ResourceArn=arn)["Tags"] == []


def test_enable_kinesis_streaming_destination_is_read_back_by_describe(s3_endpoint):
    table = "ops-dynamodb-stream-enable"
    create(s3_endpoint, table)
    arn = stream_arn(s3_endpoint)
    # A second sweep finds the destination ACTIVE already; `ok` tolerates that.
    ok(s3_endpoint, "EnableKinesisStreamingDestination", TableName=table, StreamArn=arn)
    destinations = ok(s3_endpoint, "DescribeKinesisStreamingDestination", TableName=table)[
        "KinesisDataStreamDestinations"
    ]
    assert [(d["StreamArn"], d["DestinationStatus"]) for d in destinations] == [(arn, "ACTIVE")]


def test_describe_kinesis_streaming_destination_lists_none_on_a_new_table(s3_endpoint):
    table = "ops-dynamodb-stream-describe"
    create(s3_endpoint, table)
    described = ok(s3_endpoint, "DescribeKinesisStreamingDestination", TableName=table)
    assert described["TableName"] == table
    assert described["KinesisDataStreamDestinations"] == []


def test_disable_kinesis_streaming_destination_flips_it_to_disabled(s3_endpoint):
    table = "ops-dynamodb-stream-disable"
    create(s3_endpoint, table)
    arn = stream_arn(s3_endpoint)
    ok(s3_endpoint, "EnableKinesisStreamingDestination", TableName=table, StreamArn=arn)
    disabled = ok(
        s3_endpoint, "DisableKinesisStreamingDestination", TableName=table, StreamArn=arn
    )
    assert disabled["DestinationStatus"] == "DISABLING"
    destinations = ok(s3_endpoint, "DescribeKinesisStreamingDestination", TableName=table)[
        "KinesisDataStreamDestinations"
    ]
    assert [d["DestinationStatus"] for d in destinations] == ["DISABLED"]


def test_update_kinesis_streaming_destination_sets_the_precision(s3_endpoint):
    table = "ops-dynamodb-stream-update"
    create(s3_endpoint, table)
    arn = stream_arn(s3_endpoint)
    ok(s3_endpoint, "EnableKinesisStreamingDestination", TableName=table, StreamArn=arn)
    updated = ok(
        s3_endpoint,
        "UpdateKinesisStreamingDestination",
        TableName=table,
        StreamArn=arn,
        UpdateKinesisStreamingConfiguration={"ApproximateCreationDateTimePrecision": "MICROSECOND"},
    )
    assert updated["DestinationStatus"] == "UPDATING"
    assert (
        updated["UpdateKinesisStreamingConfiguration"]["ApproximateCreationDateTimePrecision"]
        == "MICROSECOND"
    )
    destinations = ok(s3_endpoint, "DescribeKinesisStreamingDestination", TableName=table)[
        "KinesisDataStreamDestinations"
    ]
    assert [d["ApproximateCreationDateTimePrecision"] for d in destinations] == ["MICROSECOND"]
