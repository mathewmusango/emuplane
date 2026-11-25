"""EventBridge on the wire: all 57 advertised operations, JSON + `X-Amz-Target`.

Signed with the `events` credential scope. A custom bus carries the rule, target,
tag, archive and replay rows; the default bus takes `PutEvents` so no rule
delivers it. A global endpoint needs a real Route53 health check, created here
under the `route53` scope. Without Docker the bus, rules and targets are records;
nothing is delivered.
"""

from __future__ import annotations

import json
import re
import secrets
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
SECONDARY = "us-west-2"
RUN = secrets.token_hex(3)

BUS = "ops-eb-bus"
RULE = "ops-eb-rule"
ARCHIVE = "ops-eb-archive"
CONNECTION = "ops-eb-connection"
DESTINATION = "ops-eb-destination"
ENDPOINT = "ops-eb-endpoint"
PARTNER = "ops-eb-partner"
PARTNER_ACCOUNT = "123456789012"
TARGET_ID = "ops-target"
TARGET_ARN = f"arn:aws:sqs:{REGION}:{ACCOUNT}:ops-eb-target"


def call(endpoint, action: str, **payload):
    body = json.dumps(payload)
    headers = {"X-Amz-Target": f"AWSEvents.{action}", "Content-Type": "application/x-amz-json-1.1"}
    return signed.request(endpoint, "events", ACCOUNT, REGION, "POST", "/", body, headers)


def ok(endpoint, action: str, **payload) -> dict:
    status, text = call(endpoint, action, **payload)
    assert status == 200, f"{action} answered {status}: {text[:500]}"
    return json.loads(text or "{}")


def created(endpoint, action: str, **payload) -> dict:
    status, text = call(endpoint, action, **payload)
    assert status == 200 or "AlreadyExist" in text, f"{action} answered {status}: {text[:500]}"
    return json.loads(text or "{}")


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:400]}"
    return match.group(1)


def ensure_bus(endpoint) -> dict:
    created(endpoint, "CreateEventBus", Name=BUS, Description="ops bus")
    bus = ok(endpoint, "DescribeEventBus", Name=BUS)
    if bus.get("Description") != "ops bus":
        # A previous sweep's update test left its description behind.
        ok(endpoint, "UpdateEventBus", Name=BUS, Description="ops bus")
        bus = ok(endpoint, "DescribeEventBus", Name=BUS)
    return bus


def bus_arn(endpoint) -> str:
    return ensure_bus(endpoint)["Arn"]


def ensure_rule(endpoint, name: str = RULE) -> str:
    answer = ok(
        endpoint,
        "PutRule",
        Name=name,
        EventBusName=BUS,
        EventPattern=json.dumps({"source": ["ops.test"]}),
    )
    return answer["RuleArn"]


def ensure_archive(endpoint) -> dict:
    arn = bus_arn(endpoint)
    created(
        endpoint,
        "CreateArchive",
        ArchiveName=ARCHIVE,
        EventSourceArn=arn,
        Description="ops archive",
    )
    return ok(endpoint, "DescribeArchive", ArchiveName=ARCHIVE)


def ensure_connection(endpoint) -> dict:
    created(
        endpoint,
        "CreateConnection",
        Name=CONNECTION,
        AuthorizationType="BASIC",
        AuthParameters={"BasicAuthParameters": {"Username": "ops", "Password": "ops"}},
    )
    return ok(endpoint, "DescribeConnection", Name=CONNECTION)


def ensure_destination(endpoint) -> dict:
    connection = ensure_connection(endpoint)
    created(
        endpoint,
        "CreateApiDestination",
        Name=DESTINATION,
        InvocationEndpoint="https://example.com",
        HttpMethod="POST",
        ConnectionArn=connection["ConnectionArn"],
    )
    return ok(endpoint, "DescribeApiDestination", Name=DESTINATION)


# --- Route 53 health checks a global endpoint needs -------------------------


def health_check(endpoint) -> str:
    body = (
        "<CreateHealthCheckRequest>"
        f"<CallerReference>ops-eb-health-{RUN}</CallerReference>"
        "<HealthCheckConfig><Type>HTTP</Type>"
        "<FullyQualifiedDomainName>ops.example.com</FullyQualifiedDomainName>"
        "<Port>80</Port><ResourcePath>/</ResourcePath>"
        "<RequestInterval>30</RequestInterval><FailureThreshold>3</FailureThreshold>"
        "</HealthCheckConfig></CreateHealthCheckRequest>"
    )
    status, text = signed.request(
        endpoint, "route53", ACCOUNT, REGION, "POST", "/2013-04-01/healthcheck", body,
        {"Content-Type": "application/xml"},
    )
    assert status in (200, 201), f"CreateHealthCheck answered {status}: {text[:300]}"
    return f"arn:aws:route53:::healthcheck/{field(text, 'Id')}"


def endpoint_body(endpoint, name: str) -> dict:
    arn = bus_arn(endpoint)
    return {
        "Name": name,
        "Description": "ops endpoint",
        "RoutingConfig": {
            "FailoverConfig": {
                "Primary": {"HealthCheck": health_check(endpoint)},
                "Secondary": {"Route": SECONDARY},
            }
        },
        "ReplicationConfig": {"State": "DISABLED"},
        "EventBuses": [
            {"EventBusArn": arn},
            {"EventBusArn": f"arn:aws:events:{SECONDARY}:{ACCOUNT}:event-bus/{BUS}"},
        ],
    }


def ensure_endpoint(endpoint) -> dict:
    status, _text = call(endpoint, "DescribeEndpoint", Name=ENDPOINT)
    if status == 200:
        return ok(endpoint, "DescribeEndpoint", Name=ENDPOINT)
    return ok(endpoint, "CreateEndpoint", **endpoint_body(endpoint, ENDPOINT))


def ensure_partner(endpoint) -> dict:
    created(
        endpoint,
        "CreatePartnerEventSource",
        Name=PARTNER,
        Account=PARTNER_ACCOUNT,
    )
    return ok(endpoint, "DescribePartnerEventSource", Name=PARTNER)


# --- Event buses ------------------------------------------------------------


def test_create_event_bus_answers_the_bus(endpoint):
    bus = ensure_bus(endpoint)
    assert bus["Name"] == BUS
    assert bus["Arn"].endswith(f"event-bus/{BUS}")


def test_describe_event_bus_reads_it(endpoint):
    ensure_bus(endpoint)
    answer = ok(endpoint, "DescribeEventBus", Name=BUS)
    assert answer["Name"] == BUS
    assert answer["Description"] == "ops bus"


def test_update_event_bus_sets_the_description(endpoint):
    ensure_bus(endpoint)
    ok(endpoint, "UpdateEventBus", Name=BUS, Description="updated bus")
    answer = ok(endpoint, "DescribeEventBus", Name=BUS)
    assert answer["Description"] == "updated bus"


def test_list_event_buses_lists_it(endpoint):
    ensure_bus(endpoint)
    answer = ok(endpoint, "ListEventBuses", NamePrefix=BUS)
    assert BUS in {bus["Name"] for bus in answer["EventBuses"]}


def test_delete_event_bus_removes_it(endpoint):
    name = f"ops-eb-delete-bus-{RUN}"
    ok(endpoint, "CreateEventBus", Name=name)
    ok(endpoint, "DeleteEventBus", Name=name)
    status, _text = call(endpoint, "DescribeEventBus", Name=name)
    assert status == 400


# --- Rules ------------------------------------------------------------------


def test_put_rule_answers_the_rule(endpoint):
    arn = ensure_rule(endpoint)
    assert arn.endswith(f"rule/{BUS}/{RULE}")


def test_describe_rule_reads_it(endpoint):
    ensure_rule(endpoint)
    answer = ok(endpoint, "DescribeRule", Name=RULE, EventBusName=BUS)
    assert answer["Name"] == RULE
    assert answer["State"] == "ENABLED"


def test_list_rules_lists_it(endpoint):
    ensure_rule(endpoint)
    answer = ok(endpoint, "ListRules", EventBusName=BUS, NamePrefix=RULE)
    assert RULE in {rule["Name"] for rule in answer["Rules"]}


def test_enable_rule_enables_it(endpoint):
    name = f"ops-eb-enable-{RUN}"
    ensure_rule(endpoint, name)
    ok(endpoint, "DisableRule", Name=name, EventBusName=BUS)
    ok(endpoint, "EnableRule", Name=name, EventBusName=BUS)
    answer = ok(endpoint, "DescribeRule", Name=name, EventBusName=BUS)
    assert answer["State"] == "ENABLED"


def test_disable_rule_disables_it(endpoint):
    name = f"ops-eb-disable-{RUN}"
    ensure_rule(endpoint, name)
    ok(endpoint, "DisableRule", Name=name, EventBusName=BUS)
    answer = ok(endpoint, "DescribeRule", Name=name, EventBusName=BUS)
    assert answer["State"] == "DISABLED"


def test_delete_rule_removes_it(endpoint):
    name = f"ops-eb-delete-rule-{RUN}"
    ensure_rule(endpoint, name)
    ok(endpoint, "DeleteRule", Name=name, EventBusName=BUS)
    status, _text = call(endpoint, "DescribeRule", Name=name, EventBusName=BUS)
    assert status == 400


# --- Targets ----------------------------------------------------------------


def target() -> dict:
    return {"Id": TARGET_ID, "Arn": TARGET_ARN}


def test_put_targets_answers_no_failures(endpoint):
    ensure_rule(endpoint)
    answer = ok(
        endpoint, "PutTargets", Rule=RULE, EventBusName=BUS, Targets=[target()]
    )
    assert answer["FailedEntryCount"] == 0


def test_list_targets_by_rule_lists_it(endpoint):
    ensure_rule(endpoint)
    ok(endpoint, "PutTargets", Rule=RULE, EventBusName=BUS, Targets=[target()])
    answer = ok(endpoint, "ListTargetsByRule", Rule=RULE, EventBusName=BUS)
    assert TARGET_ID in {t["Id"] for t in answer["Targets"]}


def test_list_rule_names_by_target_lists_it(endpoint):
    ensure_rule(endpoint)
    ok(endpoint, "PutTargets", Rule=RULE, EventBusName=BUS, Targets=[target()])
    answer = ok(endpoint, "ListRuleNamesByTarget", TargetArn=TARGET_ARN, EventBusName=BUS)
    assert RULE in answer["RuleNames"]


def test_remove_targets_removes_it(endpoint):
    ensure_rule(endpoint)
    ok(endpoint, "PutTargets", Rule=RULE, EventBusName=BUS, Targets=[target()])
    answer = ok(
        endpoint, "RemoveTargets", Rule=RULE, EventBusName=BUS, Ids=[TARGET_ID]
    )
    assert answer["FailedEntryCount"] == 0
    listed = ok(endpoint, "ListTargetsByRule", Rule=RULE, EventBusName=BUS)
    assert TARGET_ID not in {t["Id"] for t in listed["Targets"]}


# --- Events -----------------------------------------------------------------


def test_put_events_answers_an_event_id(endpoint):
    answer = ok(
        endpoint,
        "PutEvents",
        Entries=[
            {
                "Source": "ops.test",
                "DetailType": "ops.event",
                "Detail": json.dumps({"key": "value"}),
            }
        ],
    )
    assert answer["FailedEntryCount"] == 0
    assert answer["Entries"][0]["EventId"]


def test_test_event_pattern_matches(endpoint):
    event = json.dumps({"source": "ops.test", "detail": {"key": "value"}})
    pattern = json.dumps({"source": ["ops.test"]})
    answer = ok(endpoint, "TestEventPattern", Event=event, EventPattern=pattern)
    assert answer["Result"] is True


# --- Tags -------------------------------------------------------------------


def test_tag_resource_adds_tags(endpoint):
    arn = bus_arn(endpoint)
    ok(
        endpoint,
        "TagResource",
        ResourceARN=arn,
        Tags=[{"Key": "ops", "Value": "eventbridge"}],
    )
    answer = ok(endpoint, "ListTagsForResource", ResourceARN=arn)
    assert {"Key": "ops", "Value": "eventbridge"} in answer["Tags"]


def test_list_tags_for_resource_reads_them(endpoint):
    arn = bus_arn(endpoint)
    ok(
        endpoint,
        "TagResource",
        ResourceARN=arn,
        Tags=[{"Key": "ops", "Value": "eventbridge"}],
    )
    answer = ok(endpoint, "ListTagsForResource", ResourceARN=arn)
    assert any(tag["Key"] == "ops" for tag in answer["Tags"])


def test_untag_resource_removes_tags(endpoint):
    arn = bus_arn(endpoint)
    ok(
        endpoint,
        "TagResource",
        ResourceARN=arn,
        Tags=[{"Key": "ops-remove", "Value": "eventbridge"}],
    )
    ok(endpoint, "UntagResource", ResourceARN=arn, TagKeys=["ops-remove"])
    answer = ok(endpoint, "ListTagsForResource", ResourceARN=arn)
    assert all(tag["Key"] != "ops-remove" for tag in answer["Tags"])


# --- Archives ---------------------------------------------------------------


def test_create_archive_answers_the_archive(endpoint):
    archive = ensure_archive(endpoint)
    assert archive["ArchiveName"] == ARCHIVE
    assert archive["ArchiveArn"].endswith(f"archive/{ARCHIVE}")


def test_describe_archive_reads_it(endpoint):
    ensure_archive(endpoint)
    answer = ok(endpoint, "DescribeArchive", ArchiveName=ARCHIVE)
    assert answer["ArchiveName"] == ARCHIVE


def test_update_archive_sets_the_description(endpoint):
    ensure_archive(endpoint)
    ok(endpoint, "UpdateArchive", ArchiveName=ARCHIVE, Description="updated archive")
    answer = ok(endpoint, "DescribeArchive", ArchiveName=ARCHIVE)
    assert answer["Description"] == "updated archive"


def test_list_archives_lists_it(endpoint):
    ensure_archive(endpoint)
    answer = ok(endpoint, "ListArchives", NamePrefix=ARCHIVE)
    assert ARCHIVE in {archive["ArchiveName"] for archive in answer["Archives"]}


def test_delete_archive_removes_it(endpoint):
    name = f"ops-eb-delete-archive-{RUN}"
    arn = bus_arn(endpoint)
    ok(endpoint, "CreateArchive", ArchiveName=name, EventSourceArn=arn)
    ok(endpoint, "DeleteArchive", ArchiveName=name)
    status, _text = call(endpoint, "DescribeArchive", ArchiveName=name)
    assert status == 400


# --- Permissions ------------------------------------------------------------


def test_put_permission_stores_a_statement(endpoint):
    ensure_bus(endpoint)
    answer = ok(
        endpoint,
        "PutPermission",
        EventBusName=BUS,
        StatementId="ops-statement",
        Action="events:PutEvents",
        Principal="*",
    )
    assert answer == {}


def test_remove_permission_removes_it(endpoint):
    ensure_bus(endpoint)
    ok(
        endpoint,
        "PutPermission",
        EventBusName=BUS,
        StatementId="ops-remove-statement",
        Action="events:PutEvents",
        Principal="*",
    )
    answer = ok(
        endpoint, "RemovePermission", EventBusName=BUS, StatementId="ops-remove-statement"
    )
    assert answer == {}


# --- Connections ------------------------------------------------------------


def test_create_connection_answers_the_connection(endpoint):
    connection = ensure_connection(endpoint)
    assert connection["Name"] == CONNECTION
    assert connection["ConnectionState"] in ("AUTHORIZED", "DEAUTHORIZED")


def test_describe_connection_reads_it(endpoint):
    ensure_connection(endpoint)
    answer = ok(endpoint, "DescribeConnection", Name=CONNECTION)
    assert answer["Name"] == CONNECTION
    assert answer["AuthorizationType"] == "BASIC"


def test_update_connection_sets_the_description(endpoint):
    ensure_connection(endpoint)
    ok(endpoint, "UpdateConnection", Name=CONNECTION, Description="updated connection")
    answer = ok(endpoint, "DescribeConnection", Name=CONNECTION)
    assert answer.get("Description") == "updated connection"


def test_deauthorize_connection_deauthorizes_it(endpoint):
    ensure_connection(endpoint)
    answer = ok(endpoint, "DeauthorizeConnection", Name=CONNECTION)
    assert answer["ConnectionState"] == "DEAUTHORIZED"


def test_list_connections_lists_it(endpoint):
    ensure_connection(endpoint)
    answer = ok(endpoint, "ListConnections", NamePrefix=CONNECTION)
    assert CONNECTION in {connection["Name"] for connection in answer["Connections"]}


def test_delete_connection_removes_it(endpoint):
    name = f"ops-eb-delete-connection-{RUN}"
    ok(
        endpoint,
        "CreateConnection",
        Name=name,
        AuthorizationType="BASIC",
        AuthParameters={"BasicAuthParameters": {"Username": "ops", "Password": "ops"}},
    )
    ok(endpoint, "DeleteConnection", Name=name)
    status, _text = call(endpoint, "DescribeConnection", Name=name)
    assert status == 400


# --- API destinations -------------------------------------------------------


def test_create_api_destination_answers_the_destination(endpoint):
    destination = ensure_destination(endpoint)
    assert destination["Name"] == DESTINATION
    assert destination["ApiDestinationState"] == "ACTIVE"


def test_describe_api_destination_reads_it(endpoint):
    ensure_destination(endpoint)
    answer = ok(endpoint, "DescribeApiDestination", Name=DESTINATION)
    assert answer["HttpMethod"] == "POST"


def test_update_api_destination_sets_the_description(endpoint):
    ensure_destination(endpoint)
    ok(endpoint, "UpdateApiDestination", Name=DESTINATION, Description="updated destination")
    answer = ok(endpoint, "DescribeApiDestination", Name=DESTINATION)
    assert answer.get("Description") == "updated destination"


def test_list_api_destinations_lists_it(endpoint):
    ensure_destination(endpoint)
    answer = ok(endpoint, "ListApiDestinations", NamePrefix=DESTINATION)
    assert DESTINATION in {
        destination["Name"] for destination in answer["ApiDestinations"]
    }


def test_delete_api_destination_removes_it(endpoint):
    name = f"ops-eb-delete-destination-{RUN}"
    connection = ensure_connection(endpoint)
    ok(
        endpoint,
        "CreateApiDestination",
        Name=name,
        InvocationEndpoint="https://example.com",
        HttpMethod="POST",
        ConnectionArn=connection["ConnectionArn"],
    )
    ok(endpoint, "DeleteApiDestination", Name=name)
    status, _text = call(endpoint, "DescribeApiDestination", Name=name)
    assert status == 400


# --- Replays ----------------------------------------------------------------


def start_replay(endpoint, name: str) -> str:
    archive = ensure_archive(endpoint)
    answer = ok(
        endpoint,
        "StartReplay",
        ReplayName=name,
        EventSourceArn=archive["ArchiveArn"],
        Destination={"Arn": archive["EventSourceArn"]},
        EventStartTime=0,
        EventEndTime=int(time.time()) + 3600,
    )
    return answer["ReplayArn"]


def test_start_replay_answers_the_replay(endpoint):
    name = f"ops-eb-replay-{RUN}"
    assert start_replay(endpoint, name).endswith(f"replay/{name}")


def test_describe_replay_reads_it(endpoint):
    name = f"ops-eb-describe-replay-{RUN}"
    start_replay(endpoint, name)
    answer = ok(endpoint, "DescribeReplay", ReplayName=name)
    assert answer["ReplayName"] == name


def test_list_replays_lists_it(endpoint):
    name = f"ops-eb-list-replay-{RUN}"
    start_replay(endpoint, name)
    answer = ok(endpoint, "ListReplays", NamePrefix=name)
    assert name in {replay["ReplayName"] for replay in answer["Replays"]}


def test_cancel_replay_refuses_a_completed_replay(endpoint):
    """An archive with no matching events completes its replay at once, so the reachable answer is the refusal."""
    name = f"ops-eb-cancel-replay-{RUN}"
    start_replay(endpoint, name)
    for _ in range(100):
        if ok(endpoint, "DescribeReplay", ReplayName=name)["State"] == "COMPLETED":
            break
        time.sleep(0.01)
    status, text = call(endpoint, "CancelReplay", ReplayName=name)
    assert status == 400 and "already completed" in text


# --- Global endpoints -------------------------------------------------------


def test_create_endpoint_answers_the_endpoint(endpoint):
    record = ensure_endpoint(endpoint)
    assert record["Name"] == ENDPOINT
    assert record["State"] in ("CREATING", "ACTIVE")


def test_describe_endpoint_reads_it(endpoint):
    ensure_endpoint(endpoint)
    answer = ok(endpoint, "DescribeEndpoint", Name=ENDPOINT)
    assert answer["Name"] == ENDPOINT


def test_list_endpoints_lists_it(endpoint):
    ensure_endpoint(endpoint)
    answer = ok(endpoint, "ListEndpoints", NamePrefix=ENDPOINT)
    assert ENDPOINT in {record["Name"] for record in answer["Endpoints"]}


def test_update_endpoint_sets_the_description(endpoint):
    ensure_endpoint(endpoint)
    ok(endpoint, "UpdateEndpoint", Name=ENDPOINT, Description="updated endpoint")
    answer = ok(endpoint, "DescribeEndpoint", Name=ENDPOINT)
    assert answer["Description"] == "updated endpoint"


def test_delete_endpoint_removes_it(endpoint):
    name = f"ops-eb-delete-endpoint-{RUN}"
    ok(endpoint, "CreateEndpoint", **endpoint_body(endpoint, name))
    ok(endpoint, "DeleteEndpoint", Name=name)
    status, _text = call(endpoint, "DescribeEndpoint", Name=name)
    assert status == 400


# --- Event sources and partners ---------------------------------------------


def test_activate_event_source_is_accepted(endpoint):
    assert ok(endpoint, "ActivateEventSource", Name=f"{PARTNER}/1") == {}


def test_deactivate_event_source_is_accepted(endpoint):
    assert ok(endpoint, "DeactivateEventSource", Name=f"{PARTNER}/2") == {}


def test_describe_event_source_reads_it(endpoint):
    answer = ok(endpoint, "DescribeEventSource", Name=PARTNER)
    assert answer["Name"] == PARTNER
    assert answer["State"] == "ACTIVE"


def test_create_partner_event_source_answers_the_source(endpoint):
    source = ensure_partner(endpoint)
    assert source["Name"] == PARTNER
    assert source["Arn"].endswith(f"event-source/{PARTNER}")


def test_describe_partner_event_source_reads_it(endpoint):
    ensure_partner(endpoint)
    answer = ok(endpoint, "DescribePartnerEventSource", Name=PARTNER)
    assert answer["Name"] == PARTNER


def test_list_partner_event_sources_lists_it(endpoint):
    ensure_partner(endpoint)
    answer = ok(endpoint, "ListPartnerEventSources", NamePrefix=PARTNER)
    assert PARTNER in {source["Name"] for source in answer["PartnerEventSources"]}


def test_list_partner_event_source_accounts_answers_a_list(endpoint):
    answer = ok(endpoint, "ListPartnerEventSourceAccounts", EventSourceName=PARTNER)
    assert answer["PartnerEventSourceAccounts"] == []


def test_list_event_sources_answers_a_list(endpoint):
    answer = ok(endpoint, "ListEventSources")
    assert answer["EventSources"] == []


def test_put_partner_events_answers_an_event_id(endpoint):
    answer = ok(
        endpoint,
        "PutPartnerEvents",
        Entries=[
            {
                "Source": "aws.partner/ops",
                "DetailType": "ops.event",
                "Detail": json.dumps({"key": "value"}),
            }
        ],
    )
    assert answer["FailedEntryCount"] == 0
    assert answer["Entries"][0]["EventId"]


def test_delete_partner_event_source_removes_it(endpoint):
    name = f"ops-eb-partner-delete-{RUN}"
    ok(endpoint, "CreatePartnerEventSource", Name=name, Account=PARTNER_ACCOUNT)
    ok(endpoint, "DeletePartnerEventSource", Name=name, Account=PARTNER_ACCOUNT)
    status, _text = call(endpoint, "DescribePartnerEventSource", Name=name)
    assert status == 400
