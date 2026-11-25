"""AWS Config on the wire: all 14 advertised operations, JSON 1.1.

The target prefix is `StarlingDoveService`. Rules, the configuration recorder and
the delivery channel are all upserts keyed by name, so a sweep re-puts what it
needs; a delete action creates its own rule. No evaluation engine runs, so
compliance is the documented `INSUFFICIENT_DATA` shape.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PREFIX = "StarlingDoveService"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}
RECORDER = "default"
CHANNEL = "default"


def call(endpoint, action: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    headers = {"X-Amz-Target": f"{PREFIX}.{action}", **JSON_TYPE}
    return signed.request(endpoint, "config", ACCOUNT, REGION, "POST", "/", body, headers)


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


def ensure_rule(endpoint, name: str = "ops-config-rule") -> str:
    ok(
        endpoint,
        "PutConfigRule",
        {"ConfigRule": {
            "ConfigRuleName": name,
            "Source": {"Owner": "AWS", "SourceIdentifier": "S3_BUCKET_VERSIONING_ENABLED"},
        }},
    )
    rules = ok(endpoint, "DescribeConfigRules", {"ConfigRuleNames": [name]})["ConfigRules"]
    assert rules[0]["ConfigRuleName"] == name
    return name


def ensure_recorder(endpoint) -> str:
    ok(
        endpoint,
        "PutConfigurationRecorder",
        {"ConfigurationRecorder": {
            "name": RECORDER,
            "roleARN": f"arn:aws:iam::{ACCOUNT}:role/ops-config-role",
        }},
    )
    names = [r["name"] for r in ok(endpoint, "DescribeConfigurationRecorders")["ConfigurationRecorders"]]
    assert RECORDER in names
    return RECORDER


def ensure_channel(endpoint) -> str:
    ok(
        endpoint,
        "PutDeliveryChannel",
        {"DeliveryChannel": {"name": CHANNEL, "s3BucketName": "ops-config-bucket"}},
    )
    names = [c["name"] for c in ok(endpoint, "DescribeDeliveryChannels")["DeliveryChannels"]]
    assert CHANNEL in names
    return CHANNEL


def recorder_status(endpoint) -> dict:
    statuses = ok(endpoint, "DescribeConfigurationRecorderStatus")["ConfigurationRecordersStatus"]
    return {item["name"]: item for item in statuses}[RECORDER]


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def test_put_config_rule_is_read_back(endpoint):
    ensure_rule(endpoint)
    rules = ok(endpoint, "DescribeConfigRules", {"ConfigRuleNames": ["ops-config-rule"]})["ConfigRules"]
    assert rules[0]["ConfigRuleName"] == "ops-config-rule"
    assert rules[0]["ConfigRuleArn"].startswith("arn:aws:config:us-east-1:")
    assert ":config-rule/" in rules[0]["ConfigRuleArn"]


def test_describe_config_rules_lists_the_rule(endpoint):
    name = ensure_rule(endpoint)
    assert name in {rule["ConfigRuleName"] for rule in ok(endpoint, "DescribeConfigRules")["ConfigRules"]}


def test_delete_config_rule_removes_the_rule_it_created(endpoint):
    name = f"ops-config-deleted-{time.time_ns()}"
    ensure_rule(endpoint, name)
    ok(endpoint, "DeleteConfigRule", {"ConfigRuleName": name})
    refused(endpoint, "DescribeConfigRules", {"ConfigRuleNames": [name]}, "NoSuchConfigRuleException")


# ---------------------------------------------------------------------------
# Configuration recorder
# ---------------------------------------------------------------------------


def test_put_configuration_recorder_is_read_back(endpoint):
    ensure_recorder(endpoint)
    recorders = ok(endpoint, "DescribeConfigurationRecorders")["ConfigurationRecorders"]
    assert {r["name"]: r for r in recorders}[RECORDER]["roleARN"].endswith("ops-config-role")


def test_describe_configuration_recorders_lists_the_recorder(endpoint):
    ensure_recorder(endpoint)
    names = [r["name"] for r in ok(endpoint, "DescribeConfigurationRecorders")["ConfigurationRecorders"]]
    assert RECORDER in names


def test_describe_configuration_recorder_status_shows_the_name(endpoint):
    ensure_recorder(endpoint)
    assert recorder_status(endpoint)["name"] == RECORDER


def test_start_configuration_recorder_sets_recording_true(endpoint):
    ensure_recorder(endpoint)
    ok(endpoint, "StartConfigurationRecorder", {"ConfigurationRecorderName": RECORDER})
    status = recorder_status(endpoint)
    assert status["recording"] is True
    assert status["lastStatus"] == "Success"


def test_stop_configuration_recorder_sets_recording_false(endpoint):
    ensure_recorder(endpoint)
    ok(endpoint, "StopConfigurationRecorder", {"ConfigurationRecorderName": RECORDER})
    assert recorder_status(endpoint)["recording"] is False


# ---------------------------------------------------------------------------
# Delivery channel
# ---------------------------------------------------------------------------


def test_put_delivery_channel_is_read_back(endpoint):
    ensure_channel(endpoint)
    channels = ok(endpoint, "DescribeDeliveryChannels")["DeliveryChannels"]
    assert {c["name"]: c for c in channels}[CHANNEL]["s3BucketName"] == "ops-config-bucket"


def test_describe_delivery_channels_lists_the_channel(endpoint):
    ensure_channel(endpoint)
    names = [c["name"] for c in ok(endpoint, "DescribeDeliveryChannels")["DeliveryChannels"]]
    assert CHANNEL in names


def test_describe_delivery_channel_status_shows_the_name(endpoint):
    ensure_channel(endpoint)
    statuses = ok(endpoint, "DescribeDeliveryChannelStatus")["DeliveryChannelsStatus"]
    assert CHANNEL in {item["name"] for item in statuses}


# ---------------------------------------------------------------------------
# Compliance and evaluation
# ---------------------------------------------------------------------------


def test_describe_compliance_by_config_rule_is_insufficient_data(endpoint):
    name = ensure_rule(endpoint)
    rules = ok(
        endpoint, "DescribeComplianceByConfigRule", {"ConfigRuleNames": [name]}
    )["ComplianceByConfigRules"]
    assert rules[0]["ConfigRuleName"] == name
    assert rules[0]["Compliance"]["ComplianceType"] == "INSUFFICIENT_DATA"


def test_get_compliance_details_by_config_rule_is_empty(endpoint):
    name = ensure_rule(endpoint)
    details = ok(endpoint, "GetComplianceDetailsByConfigRule", {"ConfigRuleName": name})
    assert details["EvaluationResults"] == []


def test_describe_config_rule_evaluation_status_lists_the_rule(endpoint):
    name = ensure_rule(endpoint)
    statuses = ok(
        endpoint, "DescribeConfigRuleEvaluationStatus", {"ConfigRuleNames": [name]}
    )["ConfigRulesEvaluationStatus"]
    assert statuses[0]["ConfigRuleName"] == name
