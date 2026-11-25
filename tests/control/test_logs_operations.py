"""CloudWatch Logs on the wire: every console action, driven through the JSON protocol.

A group created here is left in place; each delete action creates a resource of its own.
"""

from __future__ import annotations

import http.client
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
TARGET = "Logs_20140328."
HEADERS = {"Content-Type": "application/x-amz-json-1.0"}

# Stable names and values, so a lab sweep that re-runs overwrites instead of conflicting.
SOURCE_RESOURCE = f"arn:aws:bedrock:{REGION}:{ACCOUNT}:model/ops-logs-delivery"
BUCKET = "arn:aws:s3:::ops-logs-delivery-bucket"
SUBSCRIPTION_TARGET = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:ops-logs-subscriber"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/ops-logs-destination"
METRIC_TRANSFORMATIONS = [
    {"metricName": "OpsLogsMatches", "metricNamespace": "Emuplane/Tests", "metricValue": "1"}
]
DELIVERY_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "delivery.logs.amazonaws.com"},
                "Action": "logs:CreateDelivery",
                "Resource": "*",
            }
        ],
    }
)
RESOURCE_POLICY = json.dumps(
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock.amazonaws.com"},
                "Action": "logs:PutLogEvents",
                "Resource": "*",
            }
        ],
    }
)


def call(endpoint, action: str, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "logs", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, action: str, *, tolerate: str = "ResourceAlreadyExists", **params) -> dict:
    status, text = call(endpoint, action, **params)
    # A lab sweep re-runs against the resources an earlier sweep deliberately left behind.
    if status == 200:
        return json.loads(text or "{}")
    assert tolerate in text, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def names(endpoint) -> list[str]:
    return [group["logGroupName"] for group in ok(endpoint, "DescribeLogGroups")["logGroups"]]


def group(endpoint, name: str, **params) -> None:
    ok(endpoint, "CreateLogGroup", logGroupName=name, **params)


def described_group(endpoint, name: str) -> dict:
    groups = ok(endpoint, "DescribeLogGroups", logGroupNamePrefix=name)["logGroups"]
    return next(entry for entry in groups if entry["logGroupName"] == name)


def group_arn(endpoint, name: str) -> str:
    """The tag APIs take a group ARN without the trailing `:*`."""
    return described_group(endpoint, name)["arn"].removesuffix(":*")


def log_stream(endpoint, group_name: str, stream_name: str) -> None:
    ok(endpoint, "CreateLogStream", logGroupName=group_name, logStreamName=stream_name)


def put_events(endpoint, group_name: str, stream_name: str, *messages: str) -> dict:
    """One event per message, a millisecond apart so the order is fixed."""
    start = int(time.time() * 1000)
    log_events = [
        {"timestamp": start + index, "message": message}
        for index, message in enumerate(messages)
    ]
    return ok(
        endpoint,
        "PutLogEvents",
        logGroupName=group_name,
        logStreamName=stream_name,
        logEvents=log_events,
    )


def delivery_source(endpoint, name: str) -> dict:
    answer = ok(
        endpoint,
        "PutDeliverySource",
        name=name,
        resourceArn=SOURCE_RESOURCE,
        logType="APPLICATION_LOGS",
    )
    return answer["deliverySource"]


def delivery_destination(endpoint, name: str) -> dict:
    answer = ok(
        endpoint,
        "PutDeliveryDestination",
        name=name,
        deliveryDestinationConfiguration={"destinationResourceArn": BUCKET},
        outputFormat="json",
    )
    return answer["deliveryDestination"]


def delivery(endpoint, source_name: str, destination_name: str) -> dict:
    """The delivery binding that pair: created on a first sweep, found on a later one."""
    source = delivery_source(endpoint, source_name)
    destination = delivery_destination(endpoint, destination_name)
    for existing in ok(endpoint, "DescribeDeliveries")["deliveries"]:
        if (
            existing["deliverySourceName"] == source["name"]
            and existing["deliveryDestinationArn"] == destination["arn"]
        ):
            return existing
    answer = ok(
        endpoint,
        "CreateDelivery",
        deliverySourceName=source["name"],
        deliveryDestinationArn=destination["arn"],
    )
    return answer["delivery"]


def test_create_log_group_is_read_back_by_describe(s3_endpoint):
    ok(s3_endpoint, "CreateLogGroup", logGroupName="ops-logs-created")
    assert "ops-logs-created" in names(s3_endpoint)


def test_describe_log_streams_reads_the_new_group(s3_endpoint):
    ok(s3_endpoint, "CreateLogGroup", logGroupName="ops-logs-streams")
    answer = ok(s3_endpoint, "DescribeLogStreams", logGroupName="ops-logs-streams")
    assert answer.get("logStreams", []) == []


def test_delete_log_group_removes_the_group_it_created(s3_endpoint):
    ok(s3_endpoint, "CreateLogGroup", logGroupName="ops-logs-deleted")
    ok(s3_endpoint, "DeleteLogGroup", logGroupName="ops-logs-deleted")
    assert "ops-logs-deleted" not in names(s3_endpoint)


def test_create_log_stream_is_read_back_by_describe_log_streams(s3_endpoint):
    group(s3_endpoint, "ops-logs-stream-created")
    log_stream(s3_endpoint, "ops-logs-stream-created", "ops-stream-created")
    streams = ok(
        s3_endpoint, "DescribeLogStreams", logGroupName="ops-logs-stream-created"
    )["logStreams"]
    assert "ops-stream-created" in [stream["logStreamName"] for stream in streams]


def test_delete_log_stream_removes_the_stream_it_created(s3_endpoint):
    group(s3_endpoint, "ops-logs-stream-deleted")
    log_stream(s3_endpoint, "ops-logs-stream-deleted", "ops-stream-deleted")
    ok(
        s3_endpoint,
        "DeleteLogStream",
        logGroupName="ops-logs-stream-deleted",
        logStreamName="ops-stream-deleted",
    )
    answer = ok(s3_endpoint, "DescribeLogStreams", logGroupName="ops-logs-stream-deleted")
    assert answer["logStreams"] == []


def test_put_log_events_returns_a_sequence_token(s3_endpoint):
    group(s3_endpoint, "ops-logs-events-put")
    log_stream(s3_endpoint, "ops-logs-events-put", "ops-events-put")
    answer = put_events(s3_endpoint, "ops-logs-events-put", "ops-events-put", "ops event put")
    assert answer["nextSequenceToken"].isdigit()
    events = ok(
        s3_endpoint,
        "GetLogEvents",
        logGroupName="ops-logs-events-put",
        logStreamName="ops-events-put",
        startFromHead=True,
    )["events"]
    assert "ops event put" in [event["message"] for event in events]


def test_get_log_events_reads_the_events_back(s3_endpoint):
    group(s3_endpoint, "ops-logs-events-read")
    log_stream(s3_endpoint, "ops-logs-events-read", "ops-events-read")
    put_events(s3_endpoint, "ops-logs-events-read", "ops-events-read", "ops event first", "ops event second")
    answer = ok(
        s3_endpoint,
        "GetLogEvents",
        logGroupName="ops-logs-events-read",
        logStreamName="ops-events-read",
        startFromHead=True,
    )
    messages = [event["message"] for event in answer["events"]]
    assert {"ops event first", "ops event second"} <= set(messages)
    # OutputLogEvent carries exactly these three members, as on AWS.
    assert all(
        set(event) == {"timestamp", "message", "ingestionTime"}
        for event in answer["events"]
    )
    assert answer["nextForwardToken"].startswith("f/")


def test_filter_log_events_returns_only_the_matching_events(s3_endpoint):
    group(s3_endpoint, "ops-logs-events-filtered")
    log_stream(s3_endpoint, "ops-logs-events-filtered", "ops-events-filtered")
    put_events(
        s3_endpoint,
        "ops-logs-events-filtered",
        "ops-events-filtered",
        "ops filter needle",
        "ops filter hay",
    )
    answer = ok(
        s3_endpoint,
        "FilterLogEvents",
        logGroupName="ops-logs-events-filtered",
        filterPattern="needle",
    )
    assert answer["events"]
    assert all("needle" in event["message"] for event in answer["events"])
    assert {event["logStreamName"] for event in answer["events"]} == {"ops-events-filtered"}


def test_get_log_record_reads_the_pointer_filter_log_events_returned(s3_endpoint):
    group(s3_endpoint, "ops-logs-record")
    log_stream(s3_endpoint, "ops-logs-record", "ops-record")
    put_events(s3_endpoint, "ops-logs-record", "ops-record", "ops record needle")
    found = ok(
        s3_endpoint, "FilterLogEvents", logGroupName="ops-logs-record", filterPattern="needle"
    )["events"]
    record = ok(
        s3_endpoint, "GetLogRecord", logRecordPointer=found[0]["eventId"]
    )["logRecord"]
    assert record["@message"] == "ops record needle"
    assert record["@log"] == "ops-logs-record"
    assert record["@logStream"] == "ops-record"


def test_get_log_group_fields_names_the_json_fields_it_saw(s3_endpoint):
    group(s3_endpoint, "ops-logs-fields")
    log_stream(s3_endpoint, "ops-logs-fields", "ops-fields")
    put_events(
        s3_endpoint,
        "ops-logs-fields",
        "ops-fields",
        json.dumps({"level": "INFO", "msg": "ops fields"}),
    )
    fields = {
        field["name"]
        for field in ok(s3_endpoint, "GetLogGroupFields", logGroupName="ops-logs-fields")[
            "logGroupFields"
        ]
    }
    assert {"level", "msg", "@message"} <= fields


def stream_messages(endpoint, action: str, count: int, **params) -> list[dict]:
    """The first `count` eventstream messages of a long-lived response, then hang up.

    `StartLiveTail` stays open until the client disconnects, so a body read to EOF
    would never return. Reading message by message is what a tailer does at
    shutdown, and it works against a lab too.
    """
    url = urlsplit(endpoint)
    stamp = datetime.now(timezone.utc)
    body = json.dumps(params).encode()
    headers = {
        "Host": f"{url.hostname}:{url.port or 80}",
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={ACCOUNT}/{stamp:%Y%m%d}/{REGION}/logs"
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


def test_start_live_tail_streams_the_session_start(s3_endpoint):
    group(s3_endpoint, "ops-logs-live-tail")
    log_stream(s3_endpoint, "ops-logs-live-tail", "ops-live")
    put_events(s3_endpoint, "ops-logs-live-tail", "ops-live", "ops live tail")
    identifier = group_arn(s3_endpoint, "ops-logs-live-tail")

    initial, started = stream_messages(
        s3_endpoint, "StartLiveTail", 2, logGroupIdentifiers=[identifier]
    )
    assert "initial-response" in initial
    session = started["sessionStart"]
    assert session["sessionId"]
    assert identifier in session["logGroupIdentifiers"]


def test_put_retention_policy_is_read_back_by_describe_log_groups(s3_endpoint):
    group(s3_endpoint, "ops-logs-retention")
    ok(s3_endpoint, "PutRetentionPolicy", logGroupName="ops-logs-retention", retentionInDays=7)
    assert described_group(s3_endpoint, "ops-logs-retention")["retentionInDays"] == 7


def test_delete_retention_policy_clears_the_group(s3_endpoint):
    group(s3_endpoint, "ops-logs-retention-deleted")
    ok(
        s3_endpoint,
        "PutRetentionPolicy",
        logGroupName="ops-logs-retention-deleted",
        retentionInDays=30,
    )
    ok(s3_endpoint, "DeleteRetentionPolicy", logGroupName="ops-logs-retention-deleted")
    assert "retentionInDays" not in described_group(s3_endpoint, "ops-logs-retention-deleted")


def test_put_subscription_filter_is_read_back_by_describe(s3_endpoint):
    group(s3_endpoint, "ops-logs-subscription")
    ok(
        s3_endpoint,
        "PutSubscriptionFilter",
        logGroupName="ops-logs-subscription",
        filterName="ops-logs-sub-filter",
        filterPattern="needle",
        destinationArn=SUBSCRIPTION_TARGET,
    )
    filters = {
        entry["filterName"]: entry
        for entry in ok(
            s3_endpoint, "DescribeSubscriptionFilters", logGroupName="ops-logs-subscription"
        )["subscriptionFilters"]
    }
    assert filters["ops-logs-sub-filter"]["filterPattern"] == "needle"
    assert filters["ops-logs-sub-filter"]["destinationArn"] == SUBSCRIPTION_TARGET


def test_delete_subscription_filter_removes_the_filter_it_created(s3_endpoint):
    group(s3_endpoint, "ops-logs-subscription-deleted")
    ok(
        s3_endpoint,
        "PutSubscriptionFilter",
        logGroupName="ops-logs-subscription-deleted",
        filterName="ops-logs-sub-filter-deleted",
        filterPattern="needle",
        destinationArn=SUBSCRIPTION_TARGET,
    )
    ok(
        s3_endpoint,
        "DeleteSubscriptionFilter",
        logGroupName="ops-logs-subscription-deleted",
        filterName="ops-logs-sub-filter-deleted",
    )
    answer = ok(
        s3_endpoint,
        "DescribeSubscriptionFilters",
        logGroupName="ops-logs-subscription-deleted",
    )
    assert answer["subscriptionFilters"] == []


def test_describe_subscription_filters_lists_the_filter(s3_endpoint):
    group(s3_endpoint, "ops-logs-subscription-described")
    ok(
        s3_endpoint,
        "PutSubscriptionFilter",
        logGroupName="ops-logs-subscription-described",
        filterName="ops-logs-sub-filter-described",
        filterPattern="phrase",
        destinationArn=SUBSCRIPTION_TARGET,
    )
    answer = ok(
        s3_endpoint,
        "DescribeSubscriptionFilters",
        logGroupName="ops-logs-subscription-described",
        filterNamePrefix="ops-logs-sub-filter-described",
    )
    assert [entry["filterName"] for entry in answer["subscriptionFilters"]] == [
        "ops-logs-sub-filter-described"
    ]


def test_put_metric_filter_is_read_back_by_describe(s3_endpoint):
    group(s3_endpoint, "ops-logs-metric")
    ok(
        s3_endpoint,
        "PutMetricFilter",
        logGroupName="ops-logs-metric",
        filterName="ops-metric-filter",
        filterPattern="needle",
        metricTransformations=METRIC_TRANSFORMATIONS,
    )
    filters = {
        entry["filterName"]: entry
        for entry in ok(s3_endpoint, "DescribeMetricFilters", logGroupName="ops-logs-metric")[
            "metricFilters"
        ]
    }
    assert filters["ops-metric-filter"]["logGroupName"] == "ops-logs-metric"
    assert filters["ops-metric-filter"]["metricTransformations"][0]["metricName"] == "OpsLogsMatches"


def test_delete_metric_filter_removes_the_filter_it_created(s3_endpoint):
    group(s3_endpoint, "ops-logs-metric-deleted")
    ok(
        s3_endpoint,
        "PutMetricFilter",
        logGroupName="ops-logs-metric-deleted",
        filterName="ops-metric-filter-deleted",
        filterPattern="needle",
        metricTransformations=METRIC_TRANSFORMATIONS,
    )
    ok(
        s3_endpoint,
        "DeleteMetricFilter",
        logGroupName="ops-logs-metric-deleted",
        filterName="ops-metric-filter-deleted",
    )
    answer = ok(s3_endpoint, "DescribeMetricFilters", logGroupName="ops-logs-metric-deleted")
    assert answer["metricFilters"] == []


def test_describe_metric_filters_lists_the_filter(s3_endpoint):
    group(s3_endpoint, "ops-logs-metric-described")
    ok(
        s3_endpoint,
        "PutMetricFilter",
        logGroupName="ops-logs-metric-described",
        filterName="ops-metric-filter-described",
        filterPattern="phrase",
        metricTransformations=METRIC_TRANSFORMATIONS,
    )
    answer = ok(
        s3_endpoint,
        "DescribeMetricFilters",
        logGroupName="ops-logs-metric-described",
        filterNamePrefix="ops-metric-filter-described",
    )
    assert [entry["filterName"] for entry in answer["metricFilters"]] == [
        "ops-metric-filter-described"
    ]


def test_tag_log_group_is_read_back_by_list(s3_endpoint):
    group(s3_endpoint, "ops-logs-tags-legacy")
    ok(
        s3_endpoint,
        "TagLogGroup",
        logGroupName="ops-logs-tags-legacy",
        tags={"team": "emulation", "stage": "test"},
    )
    tags = ok(s3_endpoint, "ListTagsLogGroup", logGroupName="ops-logs-tags-legacy")["tags"]
    assert tags["team"] == "emulation"
    assert tags["stage"] == "test"


def test_untag_log_group_removes_only_the_named_tag(s3_endpoint):
    group(s3_endpoint, "ops-logs-tags-untagged")
    ok(
        s3_endpoint,
        "TagLogGroup",
        logGroupName="ops-logs-tags-untagged",
        tags={"team": "emulation", "stage": "test"},
    )
    ok(
        s3_endpoint,
        "UntagLogGroup",
        logGroupName="ops-logs-tags-untagged",
        tags=["stage"],
    )
    tags = ok(s3_endpoint, "ListTagsLogGroup", logGroupName="ops-logs-tags-untagged")["tags"]
    assert tags == {"team": "emulation"}


def test_list_tags_log_group_returns_the_groups_tags(s3_endpoint):
    group(s3_endpoint, "ops-logs-tags-listed", tags={"team": "emulation"})
    tags = ok(s3_endpoint, "ListTagsLogGroup", logGroupName="ops-logs-tags-listed")["tags"]
    assert tags == {"team": "emulation"}


def test_tag_resource_is_read_back_by_list_tags_for_resource(s3_endpoint):
    group(s3_endpoint, "ops-logs-resource-tagged")
    arn = group_arn(s3_endpoint, "ops-logs-resource-tagged")
    ok(s3_endpoint, "TagResource", resourceArn=arn, tags={"team": "emulation"})
    tags = ok(s3_endpoint, "ListTagsForResource", resourceArn=arn)["tags"]
    assert tags["team"] == "emulation"


def test_untag_resource_removes_only_the_named_tag(s3_endpoint):
    group(s3_endpoint, "ops-logs-resource-untagged")
    arn = group_arn(s3_endpoint, "ops-logs-resource-untagged")
    ok(s3_endpoint, "TagResource", resourceArn=arn, tags={"team": "emulation", "stage": "test"})
    ok(s3_endpoint, "UntagResource", resourceArn=arn, tagKeys=["stage"])
    tags = ok(s3_endpoint, "ListTagsForResource", resourceArn=arn)["tags"]
    assert tags == {"team": "emulation"}


def test_list_tags_for_resource_returns_the_groups_tags(s3_endpoint):
    group(s3_endpoint, "ops-logs-resource-listed", tags={"team": "emulation"})
    arn = group_arn(s3_endpoint, "ops-logs-resource-listed")
    tags = ok(s3_endpoint, "ListTagsForResource", resourceArn=arn)["tags"]
    assert tags == {"team": "emulation"}


def test_start_query_runs_the_query_it_was_given(s3_endpoint):
    group(s3_endpoint, "ops-logs-query-started")
    log_stream(s3_endpoint, "ops-logs-query-started", "ops-query-started")
    put_events(
        s3_endpoint,
        "ops-logs-query-started",
        "ops-query-started",
        "ops query OPSWARN one",
        "ops query info",
    )
    now = int(time.time())
    started = ok(
        s3_endpoint,
        "StartQuery",
        logGroupName="ops-logs-query-started",
        startTime=now - 600,
        endTime=now + 60,
        queryString="fields @message | filter @message like /OPSWARN/",
    )
    assert started["queryId"]
    answer = ok(s3_endpoint, "GetQueryResults", queryId=started["queryId"])
    assert answer["status"] == "Complete"
    assert answer["statistics"]["recordsMatched"] >= 1
    # Each result row is a list of {field, value} cells.
    values = [
        cell["value"]
        for row in answer["results"]
        for cell in row
        if cell["field"] == "@message"
    ]
    assert values and all("OPSWARN" in value for value in values)


def test_get_query_results_pages_the_rows(s3_endpoint):
    group(s3_endpoint, "ops-logs-query-results")
    log_stream(s3_endpoint, "ops-logs-query-results", "ops-query-results")
    put_events(
        s3_endpoint,
        "ops-logs-query-results",
        "ops-query-results",
        "ops query OPSPAGE first",
        "ops query OPSPAGE second",
    )
    now = int(time.time())
    started = ok(
        s3_endpoint,
        "StartQuery",
        logGroupName="ops-logs-query-results",
        startTime=now - 600,
        endTime=now + 60,
        queryString="fields @message | filter @message like /OPSPAGE/",
    )
    first = ok(
        s3_endpoint, "GetQueryResults", queryId=started["queryId"], maxItems=1
    )
    assert first["status"] == "Complete"
    # A row is one matched record; `maxItems` pages records, not cells.
    assert len(first["results"]) == 1
    assert first["nextToken"]
    rest = ok(
        s3_endpoint,
        "GetQueryResults",
        queryId=started["queryId"],
        maxItems=1,
        nextToken=first["nextToken"],
    )
    assert rest["results"]


def test_stop_query_cancels_the_query(s3_endpoint):
    group(s3_endpoint, "ops-logs-query-stopped")
    log_stream(s3_endpoint, "ops-logs-query-stopped", "ops-query-stopped")
    put_events(s3_endpoint, "ops-logs-query-stopped", "ops-query-stopped", "ops query stopped")
    now = int(time.time())
    started = ok(
        s3_endpoint,
        "StartQuery",
        logGroupName="ops-logs-query-stopped",
        startTime=now - 600,
        endTime=now + 60,
        queryString="fields @message",
    )
    answer = ok(s3_endpoint, "StopQuery", queryId=started["queryId"])
    assert answer["success"] is True
    results = ok(s3_endpoint, "GetQueryResults", queryId=started["queryId"])
    assert results["status"] == "Cancelled"


def test_put_destination_is_read_back_by_describe(s3_endpoint):
    answer = ok(
        s3_endpoint,
        "PutDestination",
        destinationName="ops-logs-destination",
        targetArn=SUBSCRIPTION_TARGET,
        roleArn=ROLE,
        accessPolicy=DELIVERY_POLICY,
    )
    assert answer["destination"]["destinationName"] == "ops-logs-destination"
    found = {
        entry["destinationName"]: entry
        for entry in ok(
            s3_endpoint,
            "DescribeDestinations",
            DestinationNamePrefix="ops-logs-destination",
        )["destinations"]
    }
    assert found["ops-logs-destination"]["targetArn"] == SUBSCRIPTION_TARGET


def test_delete_destination_removes_the_destination_it_created(s3_endpoint):
    ok(
        s3_endpoint,
        "PutDestination",
        destinationName="ops-logs-destination-deleted",
        targetArn=SUBSCRIPTION_TARGET,
        roleArn=ROLE,
    )
    ok(s3_endpoint, "DeleteDestination", destinationName="ops-logs-destination-deleted")
    answer = ok(
        s3_endpoint,
        "DescribeDestinations",
        DestinationNamePrefix="ops-logs-destination-deleted",
    )
    assert answer["destinations"] == []


def test_describe_destinations_lists_the_destination(s3_endpoint):
    ok(
        s3_endpoint,
        "PutDestination",
        destinationName="ops-logs-destination-described",
        targetArn=SUBSCRIPTION_TARGET,
        roleArn=ROLE,
    )
    answer = ok(
        s3_endpoint,
        "DescribeDestinations",
        DestinationNamePrefix="ops-logs-destination-described",
    )
    assert [entry["destinationName"] for entry in answer["destinations"]] == [
        "ops-logs-destination-described"
    ]
    assert answer["destinations"][0]["arn"].endswith(
        ":destination:ops-logs-destination-described"
    )


def test_put_destination_policy_sets_the_access_policy(s3_endpoint):
    ok(
        s3_endpoint,
        "PutDestination",
        destinationName="ops-logs-destination-policy",
        targetArn=SUBSCRIPTION_TARGET,
        roleArn=ROLE,
    )
    ok(
        s3_endpoint,
        "PutDestinationPolicy",
        destinationName="ops-logs-destination-policy",
        accessPolicy=DELIVERY_POLICY,
    )
    found = {
        entry["destinationName"]: entry
        for entry in ok(
            s3_endpoint,
            "DescribeDestinations",
            DestinationNamePrefix="ops-logs-destination-policy",
        )["destinations"]
    }
    assert found["ops-logs-destination-policy"]["accessPolicy"] == DELIVERY_POLICY


def test_put_delivery_source_is_read_back_by_get(s3_endpoint):
    answer = ok(
        s3_endpoint,
        "PutDeliverySource",
        name="ops-logs-delivery-source",
        resourceArn=SOURCE_RESOURCE,
        logType="APPLICATION_LOGS",
    )["deliverySource"]
    assert answer["name"] == "ops-logs-delivery-source"
    assert answer["resourceArns"] == [SOURCE_RESOURCE]
    assert answer["service"] == "bedrock"
    assert answer["logType"] == "APPLICATION_LOGS"
    read = ok(s3_endpoint, "GetDeliverySource", name="ops-logs-delivery-source")[
        "deliverySource"
    ]
    assert read["arn"] == answer["arn"]


def test_get_delivery_source_reads_the_source_it_created(s3_endpoint):
    delivery_source(s3_endpoint, "ops-logs-delivery-source-read")
    source = ok(s3_endpoint, "GetDeliverySource", name="ops-logs-delivery-source-read")[
        "deliverySource"
    ]
    assert source["name"] == "ops-logs-delivery-source-read"
    assert source["arn"].endswith(":delivery-source:ops-logs-delivery-source-read")
    assert source["logType"] == "APPLICATION_LOGS"


def test_delete_delivery_source_removes_the_source_it_created(s3_endpoint):
    delivery_source(s3_endpoint, "ops-logs-delivery-source-deleted")
    ok(s3_endpoint, "DeleteDeliverySource", name="ops-logs-delivery-source-deleted")
    status, text = call(s3_endpoint, "GetDeliverySource", name="ops-logs-delivery-source-deleted")
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_describe_delivery_sources_lists_the_source(s3_endpoint):
    delivery_source(s3_endpoint, "ops-logs-delivery-source-described")
    answer = ok(s3_endpoint, "DescribeDeliverySources")
    assert "ops-logs-delivery-source-described" in [
        source["name"] for source in answer["deliverySources"]
    ]


def test_put_delivery_destination_is_read_back_by_get(s3_endpoint):
    answer = delivery_destination(s3_endpoint, "ops-logs-delivery-destination")
    assert answer["deliveryDestinationType"] == "S3"
    assert answer["outputFormat"] == "json"
    assert answer["deliveryDestinationConfiguration"]["destinationResourceArn"] == BUCKET
    read = ok(
        s3_endpoint, "GetDeliveryDestination", name="ops-logs-delivery-destination"
    )["deliveryDestination"]
    assert read["arn"] == answer["arn"]


def test_get_delivery_destination_reads_the_destination_it_created(s3_endpoint):
    delivery_destination(s3_endpoint, "ops-logs-delivery-destination-read")
    destination = ok(
        s3_endpoint, "GetDeliveryDestination", name="ops-logs-delivery-destination-read"
    )["deliveryDestination"]
    assert destination["name"] == "ops-logs-delivery-destination-read"
    assert destination["arn"].endswith(
        ":delivery-destination:ops-logs-delivery-destination-read"
    )
    assert destination["deliveryDestinationType"] == "S3"


def test_delete_delivery_destination_removes_the_destination_it_created(s3_endpoint):
    delivery_destination(s3_endpoint, "ops-logs-delivery-destination-deleted")
    ok(
        s3_endpoint,
        "DeleteDeliveryDestination",
        name="ops-logs-delivery-destination-deleted",
    )
    status, text = call(
        s3_endpoint, "GetDeliveryDestination", name="ops-logs-delivery-destination-deleted"
    )
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_describe_delivery_destinations_lists_the_destination(s3_endpoint):
    delivery_destination(s3_endpoint, "ops-logs-delivery-destination-described")
    answer = ok(s3_endpoint, "DescribeDeliveryDestinations")
    assert "ops-logs-delivery-destination-described" in [
        destination["name"] for destination in answer["deliveryDestinations"]
    ]


def test_put_delivery_destination_policy_is_read_back_by_get(s3_endpoint):
    delivery_destination(s3_endpoint, "ops-logs-delivery-destination-policy")
    answer = ok(
        s3_endpoint,
        "PutDeliveryDestinationPolicy",
        deliveryDestinationName="ops-logs-delivery-destination-policy",
        deliveryDestinationPolicy=DELIVERY_POLICY,
    )
    assert answer["policy"]["deliveryDestinationPolicy"] == DELIVERY_POLICY
    read = ok(
        s3_endpoint,
        "GetDeliveryDestinationPolicy",
        deliveryDestinationName="ops-logs-delivery-destination-policy",
    )
    assert read["policy"]["deliveryDestinationPolicy"] == DELIVERY_POLICY


def test_get_delivery_destination_policy_reads_the_policy_it_put(s3_endpoint):
    delivery_destination(s3_endpoint, "ops-logs-delivery-destination-policy-read")
    ok(
        s3_endpoint,
        "PutDeliveryDestinationPolicy",
        deliveryDestinationName="ops-logs-delivery-destination-policy-read",
        deliveryDestinationPolicy=DELIVERY_POLICY,
    )
    read = ok(
        s3_endpoint,
        "GetDeliveryDestinationPolicy",
        deliveryDestinationName="ops-logs-delivery-destination-policy-read",
    )
    assert read["policy"] == {"deliveryDestinationPolicy": DELIVERY_POLICY}


def test_delete_delivery_destination_policy_removes_the_policy_it_created(s3_endpoint):
    name = "ops-logs-delivery-destination-policy-deleted"
    delivery_destination(s3_endpoint, name)
    ok(
        s3_endpoint,
        "PutDeliveryDestinationPolicy",
        deliveryDestinationName=name,
        deliveryDestinationPolicy=DELIVERY_POLICY,
    )
    ok(
        s3_endpoint,
        "DeleteDeliveryDestinationPolicy",
        deliveryDestinationName=name,
    )
    status, text = call(s3_endpoint, "GetDeliveryDestinationPolicy", deliveryDestinationName=name)
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_create_delivery_binds_a_source_to_its_destination(s3_endpoint):
    source = delivery_source(s3_endpoint, "ops-logs-delivery-source-bound")
    destination = delivery_destination(s3_endpoint, "ops-logs-delivery-destination-bound")
    # A re-run finds the delivery the earlier sweep created: AWS answers that pair with
    # ConflictException, and the binding it already holds is read back below.
    answer = ok(
        s3_endpoint,
        "CreateDelivery",
        tolerate="ConflictException",
        deliverySourceName=source["name"],
        deliveryDestinationArn=destination["arn"],
        recordFields=["event_timestamp", "message"],
    )
    created = answer.get("delivery") or delivery(
        s3_endpoint, source["name"], destination["name"]
    )
    assert created["deliverySourceName"] == source["name"]
    assert created["deliveryDestinationArn"] == destination["arn"]
    assert created["deliveryDestinationType"] == "S3"
    assert created["recordFields"] == ["event_timestamp", "message"]


def test_get_delivery_reads_the_delivery_it_created(s3_endpoint):
    existing = delivery(
        s3_endpoint, "ops-logs-delivery-get-source", "ops-logs-delivery-get-destination"
    )
    read = ok(s3_endpoint, "GetDelivery", id=existing["id"])["delivery"]
    assert read["id"] == existing["id"]
    assert read["arn"] == existing["arn"]
    assert read["deliverySourceName"] == "ops-logs-delivery-get-source"


def test_delete_delivery_removes_the_delivery_it_created(s3_endpoint):
    existing = delivery(
        s3_endpoint, "ops-logs-delivery-deleted-source", "ops-logs-delivery-deleted-destination"
    )
    ok(s3_endpoint, "DeleteDelivery", id=existing["id"])
    status, text = call(s3_endpoint, "GetDelivery", id=existing["id"])
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_describe_deliveries_lists_the_delivery(s3_endpoint):
    existing = delivery(
        s3_endpoint, "ops-logs-delivery-listed-source", "ops-logs-delivery-listed-destination"
    )
    listed = ok(s3_endpoint, "DescribeDeliveries")["deliveries"]
    assert any(entry["id"] == existing["id"] for entry in listed)


def test_put_resource_policy_is_read_back_by_describe(s3_endpoint):
    answer = ok(
        s3_endpoint,
        "PutResourcePolicy",
        policyName="ops-logs-resource-policy",
        policyDocument=RESOURCE_POLICY,
    )
    assert answer["resourcePolicy"]["policyName"] == "ops-logs-resource-policy"
    assert answer["resourcePolicy"]["policyScope"] == "ACCOUNT"
    assert answer["resourcePolicy"]["policyDocument"] == RESOURCE_POLICY
    assert answer["revisionId"]
    found = {
        policy["policyName"]: policy
        for policy in ok(s3_endpoint, "DescribeResourcePolicies")["resourcePolicies"]
    }
    assert found["ops-logs-resource-policy"]["policyDocument"] == RESOURCE_POLICY


def test_describe_resource_policies_lists_the_policy(s3_endpoint):
    ok(
        s3_endpoint,
        "PutResourcePolicy",
        policyName="ops-logs-resource-policy-described",
        policyDocument=RESOURCE_POLICY,
    )
    answer = ok(s3_endpoint, "DescribeResourcePolicies", policyScope="ACCOUNT")
    found = [
        policy
        for policy in answer["resourcePolicies"]
        if policy["policyName"] == "ops-logs-resource-policy-described"
    ]
    assert found
    assert found[0]["policyScope"] == "ACCOUNT"
    assert found[0]["policyDocument"] == RESOURCE_POLICY


def test_delete_resource_policy_removes_the_policy_it_created(s3_endpoint):
    ok(
        s3_endpoint,
        "PutResourcePolicy",
        policyName="ops-logs-resource-policy-deleted",
        policyDocument=RESOURCE_POLICY,
    )
    ok(s3_endpoint, "DeleteResourcePolicy", policyName="ops-logs-resource-policy-deleted")
    answer = ok(s3_endpoint, "DescribeResourcePolicies")
    assert "ops-logs-resource-policy-deleted" not in [
        policy["policyName"] for policy in answer["resourcePolicies"]
    ]
