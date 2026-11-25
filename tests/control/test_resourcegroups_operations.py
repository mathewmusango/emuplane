"""AWS Resource Groups on the wire: all 19 advertised operations, REST/JSON.

Group lifecycle and queries are POST routes (`/groups`, `/get-group`, ...);
tags are addressed by group ARN under `/resources/{arn}/tags`. A group is keyed
by name, so a stable group carries the read/query/member/tag tests while a create
or delete test makes its own.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/json"}
GROUP = "ops-rg"
RESOURCE = "arn:aws:s3:::ops-rg-bucket"
QUERY = {
    "Type": "TAG_FILTERS_1_0",
    "Query": json.dumps({"ResourceTypeFilters": ["AWS::AllSupported"], "TagFilters": []}),
}


def call(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(endpoint, "resource-groups", ACCOUNT, REGION, method, path, body, JSON_TYPE)


def ok(endpoint, method: str, path: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, method, path, payload)
    assert status == 200, f"{method} {path} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def refused(endpoint, method: str, path: str, payload: dict | None = None, code: str = "") -> str:
    status, text = call(endpoint, method, path, payload)
    assert status >= 400, f"{method} {path} unexpectedly answered {status}: {text[:400]}"
    if code:
        assert code in text
    return text


def ensure_group(endpoint, name: str = GROUP) -> dict:
    status, text = call(endpoint, "POST", "/groups", {"Name": name, "ResourceQuery": QUERY})
    assert status == 200 or "already exists" in text, text[:300]
    return ok(endpoint, "POST", "/get-group", {"GroupName": name})["Group"]


def group_arn(endpoint, name: str = GROUP) -> str:
    return ensure_group(endpoint, name)["GroupArn"]


def group_a_resource(endpoint, name: str = GROUP) -> None:
    ok(endpoint, "POST", "/group-resources", {"Group": name, "ResourceArns": [RESOURCE]})


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


def test_create_group_is_read_back(endpoint):
    name = f"ops-rg-created-{time.time_ns()}"
    ok(endpoint, "POST", "/groups", {"Name": name, "ResourceQuery": QUERY})
    assert ok(endpoint, "POST", "/get-group", {"GroupName": name})["Group"]["Name"] == name


def test_get_group_reads_the_group(endpoint):
    assert ensure_group(endpoint)["Name"] == GROUP


def test_delete_group_removes_the_group_it_created(endpoint):
    name = f"ops-rg-deleted-{time.time_ns()}"
    ok(endpoint, "POST", "/groups", {"Name": name})
    ok(endpoint, "POST", "/delete-group", {"GroupName": name})
    refused(endpoint, "POST", "/get-group", {"GroupName": name})


def test_update_group_changes_the_description(endpoint):
    ensure_group(endpoint)
    updated = ok(endpoint, "POST", "/update-group", {"GroupName": GROUP, "Description": "updated"})["Group"]
    assert updated["Description"] == "updated"


def test_list_groups_lists_the_group(endpoint):
    ensure_group(endpoint)
    names = [item["Name"] for item in ok(endpoint, "POST", "/groups-list", {})["Groups"]]
    assert GROUP in names


# ---------------------------------------------------------------------------
# Group query and configuration
# ---------------------------------------------------------------------------


def test_get_group_query_reads_the_query(endpoint):
    ensure_group(endpoint)
    query = ok(endpoint, "POST", "/get-group-query", {"GroupName": GROUP})["GroupQuery"]
    assert query["ResourceQuery"]["Type"] == "TAG_FILTERS_1_0"


def test_update_group_query_changes_the_query(endpoint):
    ensure_group(endpoint)
    updated = dict(QUERY)
    updated["Query"] = json.dumps({"ResourceTypeFilters": ["AWS::S3::Bucket"], "TagFilters": []})
    ok(endpoint, "POST", "/update-group-query", {"GroupName": GROUP, "ResourceQuery": updated})
    query = ok(endpoint, "POST", "/get-group-query", {"GroupName": GROUP})["GroupQuery"]
    assert "S3::Bucket" in query["ResourceQuery"]["Query"]


def test_get_group_configuration_reads_it(endpoint):
    ensure_group(endpoint)
    answer = ok(endpoint, "POST", "/get-group-configuration", {"Group": GROUP})
    assert "Configuration" in answer["GroupConfiguration"]


def test_put_group_configuration_sets_it(endpoint):
    ensure_group(endpoint)
    config = [{"Type": "AWS::ResourceGroups::Generic", "Parameters": [{"Name": "allowed-resource-types", "Values": ["AWS::S3::Bucket"]}]}]
    ok(endpoint, "POST", "/put-group-configuration", {"Group": GROUP, "Configuration": config})
    answer = ok(endpoint, "POST", "/get-group-configuration", {"Group": GROUP})
    assert answer["GroupConfiguration"]["Configuration"] == config


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


def test_group_resources_adds_the_resource(endpoint):
    ensure_group(endpoint)
    result = ok(endpoint, "POST", "/group-resources", {"Group": GROUP, "ResourceArns": [RESOURCE]})
    assert result["Succeeded"] == [RESOURCE]
    listed = ok(endpoint, "POST", "/list-group-resources", {"GroupName": GROUP})["ResourceIdentifiers"]
    assert RESOURCE in {item["ResourceArn"] for item in listed}


def test_ungroup_resources_removes_the_resource(endpoint):
    ensure_group(endpoint)
    group_a_resource(endpoint)
    ok(endpoint, "POST", "/ungroup-resources", {"Group": GROUP, "ResourceArns": [RESOURCE]})
    listed = ok(endpoint, "POST", "/list-group-resources", {"GroupName": GROUP})["ResourceIdentifiers"]
    assert RESOURCE not in {item["ResourceArn"] for item in listed}


def test_list_group_resources_lists_the_resource(endpoint):
    ensure_group(endpoint)
    group_a_resource(endpoint)
    listed = ok(endpoint, "POST", "/list-group-resources", {"GroupName": GROUP})["ResourceIdentifiers"]
    assert RESOURCE in {item["ResourceArn"] for item in listed}


def test_list_grouping_statuses_lists_the_member(endpoint):
    ensure_group(endpoint)
    group_a_resource(endpoint)
    statuses = ok(endpoint, "POST", "/list-grouping-statuses", {"Group": GROUP})["GroupingStatuses"]
    assert RESOURCE in {item["ResourceArn"] for item in statuses}


def test_search_resources_answers_the_query(endpoint):
    answer = ok(endpoint, "POST", "/resources/search", {"ResourceQuery": QUERY})
    assert answer["ResourceIdentifiers"] == []


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_is_read_back_by_get_tags(endpoint):
    arn = group_arn(endpoint)
    ok(endpoint, "PUT", f"/resources/{arn}/tags", {"Tags": {"env": "ops"}})
    assert ok(endpoint, "GET", f"/resources/{arn}/tags")["Tags"]["env"] == "ops"


def test_untag_removes_the_key_it_names(endpoint):
    arn = group_arn(endpoint)
    ok(endpoint, "PUT", f"/resources/{arn}/tags", {"Tags": {"doomed": "yes"}})
    ok(endpoint, "PATCH", f"/resources/{arn}/tags", {"Keys": ["doomed"]})
    assert "doomed" not in ok(endpoint, "GET", f"/resources/{arn}/tags")["Tags"]


def test_get_tags_lists_the_tags(endpoint):
    arn = group_arn(endpoint)
    ok(endpoint, "PUT", f"/resources/{arn}/tags", {"Tags": {"team": "platform"}})
    assert ok(endpoint, "GET", f"/resources/{arn}/tags")["Tags"]["team"] == "platform"


# ---------------------------------------------------------------------------
# Account settings
# ---------------------------------------------------------------------------


def test_get_account_settings_reads_them(endpoint):
    assert "GroupLifecycleEventsDesiredStatus" in ok(endpoint, "POST", "/get-account-settings", {})["AccountSettings"]


def test_update_account_settings_sets_the_status(endpoint):
    answer = ok(endpoint, "POST", "/update-account-settings", {"GroupLifecycleEventsDesiredStatus": "ACTIVE"})
    assert answer["AccountSettings"]["GroupLifecycleEventsDesiredStatus"] == "ACTIVE"
    # Restore the default for the next sweep.
    ok(endpoint, "POST", "/update-account-settings", {"GroupLifecycleEventsDesiredStatus": "INACTIVE"})
