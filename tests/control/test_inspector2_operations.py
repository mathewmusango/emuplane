"""Amazon Inspector2 on the wire: all 14 advertised operations, REST-JSON.

Paths are fixed: `/enable`, `/disable`, `/findings/*`, `/coverage/*`,
`/vulnerabilities/search`, `/filters/*`, and tags by resource ARN under
`/tags/{arn}`. Findings and coverage exist only while a resource type is
enabled, so the read tests enable the account first.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/json"}
FILTER = "ops-inspector-filter"


def call(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(endpoint, "inspector2", ACCOUNT, REGION, method, path, body, JSON_TYPE)


def ok(endpoint, method: str, path: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, method, path, payload)
    assert status == 200, f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def enable(endpoint) -> None:
    ok(endpoint, "POST", "/enable", {"accountIds": [ACCOUNT], "resourceTypes": ["ECR", "EC2"]})


def ensure_filter(endpoint, name: str = FILTER) -> str:
    status, text = call(endpoint, "POST", "/filters/create", {"name": name, "action": "NONE", "filterCriteria": {}})
    assert status == 200 or "ConflictException" in text, text[:300]
    filters = ok(endpoint, "POST", "/filters/list")["filters"]
    return {item["name"]: item["arn"] for item in filters}[name]


# ---------------------------------------------------------------------------
# Account state
# ---------------------------------------------------------------------------


def test_enable_turns_the_account_on(endpoint):
    answer = ok(endpoint, "POST", "/enable", {"accountIds": [ACCOUNT], "resourceTypes": ["ECR"]})
    assert answer["accounts"][0]["status"] == "ENABLED"
    assert answer["failedAccounts"] == []


def test_disable_turns_the_account_off(endpoint):
    answer = ok(endpoint, "POST", "/disable", {"accountIds": [ACCOUNT], "resourceTypes": ["ECR"]})
    assert answer["accounts"][0]["status"] == "DISABLED"
    # Leave the account enabled for the read tests.
    enable(endpoint)


# ---------------------------------------------------------------------------
# Findings and coverage
# ---------------------------------------------------------------------------


def test_list_findings_answers_the_findings(endpoint):
    enable(endpoint)
    assert isinstance(ok(endpoint, "POST", "/findings/list")["findings"], list)


def test_batch_get_finding_details_reports_a_missing_finding(endpoint):
    missing = f"arn:aws:inspector2:{REGION}:{ACCOUNT}:finding/ops-missing"
    answer = ok(endpoint, "POST", "/findings/details/batch/get", {"findingArns": [missing]})
    assert answer["findingDetails"] == []
    assert answer["errors"][0]["errorCode"] == "RESOURCE_NOT_FOUND"


def test_list_coverage_answers_the_covered_resources(endpoint):
    enable(endpoint)
    assert isinstance(ok(endpoint, "POST", "/coverage/list")["coveredResources"], list)


def test_list_coverage_statistics_answers_the_counts(endpoint):
    enable(endpoint)
    answer = ok(endpoint, "POST", "/coverage/statistics/list", {"groupBy": "RESOURCE_TYPE"})
    assert isinstance(answer["countsByGroup"], list)
    assert isinstance(answer["totalCounts"], int)


def test_list_finding_aggregations_answers_the_groups(endpoint):
    enable(endpoint)
    answer = ok(endpoint, "POST", "/findings/aggregation/list", {"aggregationType": "FINDING_TYPE"})
    assert answer["aggregationType"] == "FINDING_TYPE"
    assert isinstance(answer["responses"], list)


def test_search_vulnerabilities_answers_the_matches(endpoint):
    answer = ok(endpoint, "POST", "/vulnerabilities/search", {"filterCriteria": {}})
    assert isinstance(answer["vulnerabilities"], list)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def test_create_filter_is_read_back(endpoint):
    name = f"ops-filter-{time.time_ns()}"
    created = ok(endpoint, "POST", "/filters/create", {"name": name, "action": "NONE", "filterCriteria": {}})
    assert created["arn"].endswith(f"filter/{name}")
    names = [item["name"] for item in ok(endpoint, "POST", "/filters/list")["filters"]]
    assert name in names


def test_list_filters_lists_the_filter(endpoint):
    ensure_filter(endpoint)
    names = [item["name"] for item in ok(endpoint, "POST", "/filters/list")["filters"]]
    assert FILTER in names


def test_delete_filter_removes_the_filter_it_created(endpoint):
    name = f"ops-filter-deleted-{time.time_ns()}"
    created = ok(endpoint, "POST", "/filters/create", {"name": name, "action": "NONE", "filterCriteria": {}})
    ok(endpoint, "POST", "/filters/delete", {"arn": created["arn"]})
    names = [item["name"] for item in ok(endpoint, "POST", "/filters/list")["filters"]]
    assert name not in names


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_is_read_back_by_list_tags(endpoint):
    arn = ensure_filter(endpoint)
    ok(endpoint, "POST", f"/tags/{arn}", {"tags": {"env": "ops"}})
    assert ok(endpoint, "GET", f"/tags/{arn}")["tags"].get("env") == "ops"


def test_untag_resource_removes_the_key_it_names(endpoint):
    arn = ensure_filter(endpoint)
    ok(endpoint, "POST", f"/tags/{arn}", {"tags": {"doomed": "yes"}})
    ok(endpoint, "DELETE", f"/tags/{arn}?tagKeys=doomed")
    assert "doomed" not in ok(endpoint, "GET", f"/tags/{arn}")["tags"]


def test_list_tags_for_resource_lists_the_tags(endpoint):
    arn = ensure_filter(endpoint)
    ok(endpoint, "POST", f"/tags/{arn}", {"tags": {"team": "platform"}})
    assert ok(endpoint, "GET", f"/tags/{arn}")["tags"].get("team") == "platform"
