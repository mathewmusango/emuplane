"""Cost & Usage Reports on the wire: all 7 advertised operations, JSON 1.1.

The target prefix is `AWSOrigamiServiceGateway`. A report definition has no
lifecycle to unwind: it is put and read back, a delete action creates its own
report, and every tag write is read through `ListTagsForResource`.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PREFIX = "AWSOrigamiServiceGateway"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.1"}


def call(endpoint, action: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    headers = {"X-Amz-Target": f"{PREFIX}.{action}", **JSON_TYPE}
    return signed.request(endpoint, "cur", ACCOUNT, REGION, "POST", "/", body, headers)


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


def definition(name: str) -> dict:
    return {
        "ReportName": name,
        "TimeUnit": "DAILY",
        "Format": "textORcsv",
        "Compression": "GZIP",
        "S3Bucket": "ops-cur-bucket",
        "S3Prefix": "reports",
        "S3Region": REGION,
        "AdditionalSchemaElements": ["RESOURCES"],
    }


def reports(endpoint) -> dict:
    return {
        item["ReportName"]: item
        for item in ok(endpoint, "DescribeReportDefinitions")["ReportDefinitions"]
    }


def ensure_report(endpoint, name: str = "ops-cur-report") -> str:
    status, text = call(endpoint, "PutReportDefinition", {"ReportDefinition": definition(name)})
    assert status == 200 or "DuplicateReportNameException" in text, text[:300]
    assert name in reports(endpoint)
    return name


# ---------------------------------------------------------------------------
# Report definitions
# ---------------------------------------------------------------------------


def test_put_report_definition_is_read_back(endpoint):
    name = f"ops-cur-created-{time.time_ns()}"
    ok(endpoint, "PutReportDefinition", {"ReportDefinition": definition(name)})
    found = reports(endpoint)[name]
    assert found["S3Region"] == REGION
    assert found["TimeUnit"] == "DAILY"


def test_describe_report_definitions_lists_the_report(endpoint):
    name = ensure_report(endpoint)
    assert name in reports(endpoint)


def test_modify_report_definition_changes_the_prefix(endpoint):
    name = ensure_report(endpoint)
    changed = definition(name)
    changed["S3Prefix"] = "modified"
    ok(endpoint, "ModifyReportDefinition", {"ReportName": name, "ReportDefinition": changed})
    assert reports(endpoint)[name]["S3Prefix"] == "modified"


def test_delete_report_definition_removes_the_report_it_created(endpoint):
    name = f"ops-cur-deleted-{time.time_ns()}"
    ok(endpoint, "PutReportDefinition", {"ReportDefinition": definition(name)})
    assert name in reports(endpoint)
    ok(endpoint, "DeleteReportDefinition", {"ReportName": name})
    assert name not in reports(endpoint)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_is_read_back_by_list_tags(endpoint):
    name = ensure_report(endpoint)
    ok(endpoint, "TagResource", {"ReportName": name, "Tags": [{"Key": "env", "Value": "ops"}]})
    tags = ok(endpoint, "ListTagsForResource", {"ReportName": name})["Tags"]
    assert {"Key": "env", "Value": "ops"} in tags


def test_untag_resource_removes_the_key_it_names(endpoint):
    name = ensure_report(endpoint)
    ok(endpoint, "TagResource", {"ReportName": name, "Tags": [{"Key": "doomed", "Value": "yes"}]})
    ok(endpoint, "UntagResource", {"ReportName": name, "TagKeys": ["doomed"]})
    keys = {tag["Key"] for tag in ok(endpoint, "ListTagsForResource", {"ReportName": name})["Tags"]}
    assert "doomed" not in keys


def test_list_tags_for_resource_lists_the_tags(endpoint):
    name = ensure_report(endpoint)
    ok(endpoint, "TagResource", {"ReportName": name, "Tags": [{"Key": "team", "Value": "platform"}]})
    tags = ok(endpoint, "ListTagsForResource", {"ReportName": name})["Tags"]
    assert {"Key": "team", "Value": "platform"} in tags
