"""AWS Organizations on the wire: all 28 advertised operations, JSON protocol.

Signed with the `organizations` scope and addressed by
``X-Amz-Target: AWSOrganizationsV20161128.<Action>``. The organization is
initialised lazily on the first call, with a root that has `SERVICE_CONTROL_POLICY`
enabled and `p-FullAWSAccess` attached.

Everything is find-or-create by name or email, because the emulator happily mints
a second account or unit with the same name: a second sweep must meet the first
sweep's graph, not grow a duplicate of it. The one exception is an operation that
returns a one-shot identifier (a create-account request), which gets a run-unique
email so the id can be read back immediately. The graph is left in place.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
TARGET = "AWSOrganizationsV20161128."
HEADERS = {"Content-Type": "application/x-amz-json-1.1"}

OU = "ops-org-ou"
OU_CHILD = "ops-org-ou-child"
POLICY = "ops-org-policy"
ACCOUNT_EMAIL = "ops-org-account@example.com"
MOVED_EMAIL = "ops-org-moved@example.com"
CLOSED_EMAIL = "ops-org-closed@example.com"

POLICY_CONTENT = json.dumps(
    {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "s3:*", "Resource": "*"}]}
)
POLICY_CONTENT_UPDATED = json.dumps(
    {"Version": "2012-10-17", "Statement": [{"Effect": "Deny", "Action": "s3:*", "Resource": "*"}]}
)


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def call(endpoint, action: str, **payload):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "organizations", ACCOUNT, REGION, "POST", "/", json.dumps(payload), headers
    )


def ok(endpoint, action: str, **payload) -> dict:
    status, text = call(endpoint, action, **payload)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def rejected(endpoint, action: str, expected: int = 400, **payload) -> str:
    status, text = call(endpoint, action, **payload)
    assert status == expected, f"{action} answered {status}: {text[:400]}"
    return text


# ---------------------------------------------------------------------------
# Find-or-create
# ---------------------------------------------------------------------------


def root_id(endpoint) -> str:
    return ok(endpoint, "ListRoots")["Roots"][0]["Id"]


def ensure_ou(endpoint, name: str, parent: str | None = None) -> str:
    parent = parent or root_id(endpoint)
    units = ok(endpoint, "ListOrganizationalUnitsForParent", ParentId=parent)[
        "OrganizationalUnits"
    ]
    for unit in units:
        if unit["Name"] == name:
            return unit["Id"]
    return ok(endpoint, "CreateOrganizationalUnit", ParentId=parent, Name=name)[
        "OrganizationalUnit"
    ]["Id"]


def ensure_account(endpoint, email: str, name: str) -> str:
    for account in ok(endpoint, "ListAccounts")["Accounts"]:
        if account["Email"] == email:
            return account["Id"]
    return ok(endpoint, "CreateAccount", Email=email, AccountName=name)[
        "CreateAccountStatus"
    ]["AccountId"]


def ensure_policy(endpoint, name: str) -> str:
    for policy in ok(endpoint, "ListPolicies", Filter="SERVICE_CONTROL_POLICY")["Policies"]:
        if policy["Name"] == name:
            return policy["Id"]
    return ok(
        endpoint,
        "CreatePolicy",
        Content=POLICY_CONTENT,
        Description="Emuplane Organizations sweep",
        Name=name,
        Type="SERVICE_CONTROL_POLICY",
    )["Policy"]["PolicySummary"]["Id"]


def ensure_attached(endpoint) -> tuple[str, str]:
    policy = ensure_policy(endpoint, POLICY)
    target = ensure_ou(endpoint, OU)
    status, text = call(endpoint, "AttachPolicy", PolicyId=policy, TargetId=target)
    assert status in (200, 400), f"AttachPolicy answered {status}: {text[:400]}"
    if status == 400:
        assert "already attached" in text
    return policy, target


def policy_names_for(endpoint, target: str) -> list[str]:
    return [
        policy["Name"]
        for policy in ok(
            endpoint, "ListPoliciesForTarget", TargetId=target, Filter="SERVICE_CONTROL_POLICY"
        )["Policies"]
    ]


# ---------------------------------------------------------------------------
# The organization and its root
# ---------------------------------------------------------------------------


def test_describe_organization_reports_the_all_features_master(endpoint):
    organization = ok(endpoint, "DescribeOrganization")["Organization"]
    assert organization["FeatureSet"] == "ALL"
    assert organization["MasterAccountId"] == ACCOUNT
    assert organization["Id"].startswith("o-")


def test_list_roots_reports_the_scp_enabled_root(endpoint):
    roots = ok(endpoint, "ListRoots")["Roots"]
    assert len(roots) == 1
    assert roots[0]["Id"].startswith("r-")
    types = {entry["Type"]: entry["Status"] for entry in roots[0]["PolicyTypes"]}
    assert types["SERVICE_CONTROL_POLICY"] == "ENABLED"


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def test_list_accounts_includes_the_master_account(endpoint):
    accounts = ok(endpoint, "ListAccounts")["Accounts"]
    assert ACCOUNT in [account["Id"] for account in accounts]


def test_list_accounts_for_parent_finds_the_master_under_the_root(endpoint):
    accounts = ok(endpoint, "ListAccountsForParent", ParentId=root_id(endpoint))["Accounts"]
    assert ACCOUNT in [account["Id"] for account in accounts]


def test_describe_account_reads_the_master_account(endpoint):
    account = ok(endpoint, "DescribeAccount", AccountId=ACCOUNT)["Account"]
    assert account["Id"] == ACCOUNT
    assert account["Name"] == "Master Account"
    assert account["Status"] == "ACTIVE"


def test_create_account_is_read_back_by_describe_account(endpoint):
    email = f"ops-org-created-{time.time_ns()}@example.com"
    created = ok(endpoint, "CreateAccount", Email=email, AccountName="ops-org-created")[
        "CreateAccountStatus"
    ]
    assert created["State"] == "SUCCEEDED"
    account = ok(endpoint, "DescribeAccount", AccountId=created["AccountId"])["Account"]
    assert account["Email"] == email
    assert account["JoinedMethod"] == "CREATED"


def test_describe_create_account_status_reads_the_request(endpoint):
    email = f"ops-org-status-{time.time_ns()}@example.com"
    created = ok(endpoint, "CreateAccount", Email=email, AccountName="ops-org-status")[
        "CreateAccountStatus"
    ]
    status = ok(
        endpoint, "DescribeCreateAccountStatus", CreateAccountRequestId=created["Id"]
    )["CreateAccountStatus"]
    assert status["State"] == "SUCCEEDED"
    assert status["AccountId"] == created["AccountId"]


def test_move_account_changes_its_parent(endpoint):
    account = ensure_account(endpoint, MOVED_EMAIL, "ops-org-moved")
    unit = ensure_ou(endpoint, OU)
    root = root_id(endpoint)
    current = ok(endpoint, "ListParents", ChildId=account)["Parents"][0]["Id"]
    destination = unit if current != unit else root
    ok(
        endpoint,
        "MoveAccount",
        AccountId=account,
        SourceParentId=current,
        DestinationParentId=destination,
    )
    parent = ok(endpoint, "ListParents", ChildId=account)["Parents"][0]
    assert parent["Id"] == destination


def test_close_account_suspends_it(endpoint):
    account = ensure_account(endpoint, CLOSED_EMAIL, "ops-org-closed")
    status = ok(endpoint, "DescribeAccount", AccountId=account)["Account"]["Status"]
    if status == "SUSPENDED":
        text = rejected(endpoint, "CloseAccount", AccountId=account)
        assert "already closed" in text
    else:
        ok(endpoint, "CloseAccount", AccountId=account)
    assert ok(endpoint, "DescribeAccount", AccountId=account)["Account"]["Status"] == "SUSPENDED"


# ---------------------------------------------------------------------------
# Organizational units
# ---------------------------------------------------------------------------


def test_create_organizational_unit_is_read_back_with_its_path(endpoint):
    parent = ensure_ou(endpoint, OU)
    unit = ensure_ou(endpoint, OU_CHILD, parent=parent)
    described = ok(endpoint, "DescribeOrganizationalUnit", OrganizationalUnitId=unit)[
        "OrganizationalUnit"
    ]
    assert described["Name"] == OU_CHILD
    assert described["Path"] == f"/{OU}/{OU_CHILD}/"


def test_describe_organizational_unit_reports_the_parent_path(endpoint):
    unit = ensure_ou(endpoint, OU)
    described = ok(endpoint, "DescribeOrganizationalUnit", OrganizationalUnitId=unit)[
        "OrganizationalUnit"
    ]
    assert described["Id"] == unit
    assert described["Path"] == f"/{OU}/"


def test_delete_organizational_unit_removes_the_unit_it_created(endpoint):
    name = f"ops-org-deleted-{time.time_ns()}"
    unit = ensure_ou(endpoint, name)
    ok(endpoint, "DeleteOrganizationalUnit", OrganizationalUnitId=unit)
    text = rejected(endpoint, "DescribeOrganizationalUnit", OrganizationalUnitId=unit)
    assert "not found" in text


def test_list_organizational_units_includes_the_unit(endpoint):
    ensure_ou(endpoint, OU)
    units = ok(endpoint, "ListOrganizationalUnitsForParent", ParentId=root_id(endpoint))[
        "OrganizationalUnits"
    ]
    assert OU in [unit["Name"] for unit in units]


def test_list_parents_names_the_root_and_the_unit(endpoint):
    unit = ensure_ou(endpoint, OU)
    child = ensure_ou(endpoint, OU_CHILD, parent=unit)
    assert ok(endpoint, "ListParents", ChildId=unit)["Parents"] == [
        {"Id": root_id(endpoint), "Type": "ROOT"}
    ]
    assert ok(endpoint, "ListParents", ChildId=child)["Parents"] == [
        {"Id": unit, "Type": "ORGANIZATIONAL_UNIT"}
    ]


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------


def test_create_policy_is_read_back_by_describe(endpoint):
    policy = ensure_policy(endpoint, POLICY)
    described = ok(endpoint, "DescribePolicy", PolicyId=policy)["Policy"]
    assert described["PolicySummary"]["Id"] == policy
    assert described["PolicySummary"]["Type"] == "SERVICE_CONTROL_POLICY"


def test_describe_policy_returns_the_document(endpoint):
    policy = ensure_policy(endpoint, POLICY)
    described = ok(endpoint, "DescribePolicy", PolicyId=policy)["Policy"]
    assert json.loads(described["Content"])["Version"] == "2012-10-17"


def test_update_policy_changes_its_description(endpoint):
    policy = ensure_policy(endpoint, POLICY)
    updated = ok(
        endpoint,
        "UpdatePolicy",
        PolicyId=policy,
        Description="Updated by the Emuplane sweep",
        Content=POLICY_CONTENT_UPDATED,
    )["Policy"]
    assert updated["PolicySummary"]["Description"] == "Updated by the Emuplane sweep"
    assert json.loads(updated["Content"])["Statement"][0]["Effect"] == "Deny"


def test_delete_policy_removes_the_policy_it_created(endpoint):
    name = f"ops-org-policy-deleted-{time.time_ns()}"
    policy = ok(
        endpoint,
        "CreatePolicy",
        Content=POLICY_CONTENT,
        Description="Delete me",
        Name=name,
        Type="SERVICE_CONTROL_POLICY",
    )["Policy"]["PolicySummary"]["Id"]
    ok(endpoint, "DeletePolicy", PolicyId=policy)
    text = rejected(endpoint, "DescribePolicy", PolicyId=policy)
    assert "can't find a policy" in text


def test_list_policies_includes_the_created_policy(endpoint):
    ensure_policy(endpoint, POLICY)
    names = [
        policy["Name"]
        for policy in ok(endpoint, "ListPolicies", Filter="SERVICE_CONTROL_POLICY")["Policies"]
    ]
    assert POLICY in names


def test_attach_policy_is_read_back_by_list_policies_for_target(endpoint):
    policy, target = ensure_attached(endpoint)
    assert POLICY in policy_names_for(endpoint, target)
    assert policy in [
        entry["Id"]
        for entry in ok(
            endpoint, "ListPoliciesForTarget", TargetId=target, Filter="SERVICE_CONTROL_POLICY"
        )["Policies"]
    ]


def test_detach_policy_removes_the_attachment(endpoint):
    _policy, target = ensure_attached(endpoint)
    ok(
        endpoint,
        "DetachPolicy",
        PolicyId=ensure_policy(endpoint, POLICY),
        TargetId=target,
    )
    assert POLICY not in policy_names_for(endpoint, target)


def test_list_policies_for_target_finds_the_attached_policy(endpoint):
    _policy, target = ensure_attached(endpoint)
    assert POLICY in policy_names_for(endpoint, target)


def test_list_targets_for_policy_names_the_unit(endpoint):
    policy, target = ensure_attached(endpoint)
    targets = ok(endpoint, "ListTargetsForPolicy", PolicyId=policy)["Targets"]
    unit = next(entry for entry in targets if entry["TargetId"] == target)
    assert unit["Type"] == "ORGANIZATIONAL_UNIT"
    assert unit["Name"] == OU


# ---------------------------------------------------------------------------
# Policy types
# ---------------------------------------------------------------------------


def test_enable_policy_type_enables_it_on_the_root(endpoint):
    root = root_id(endpoint)
    status, text = call(endpoint, "EnablePolicyType", RootId=root, PolicyType="TAG_POLICY")
    assert status in (200, 400), f"EnablePolicyType answered {status}: {text[:400]}"
    if status == 400:
        assert "already enabled" in text
    root_record = ok(endpoint, "ListRoots")["Roots"][0]
    types = {entry["Type"]: entry["Status"] for entry in root_record["PolicyTypes"]}
    assert types["TAG_POLICY"] == "ENABLED"


def test_disable_policy_type_removes_it_from_the_root(endpoint):
    root = root_id(endpoint)
    status, text = call(endpoint, "EnablePolicyType", RootId=root, PolicyType="TAG_POLICY")
    assert status in (200, 400), f"EnablePolicyType answered {status}: {text[:400]}"
    ok(endpoint, "DisablePolicyType", RootId=root, PolicyType="TAG_POLICY")
    root_record = ok(endpoint, "ListRoots")["Roots"][0]
    assert "TAG_POLICY" not in {entry["Type"] for entry in root_record["PolicyTypes"]}


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_adds_a_tag_the_list_reads_back(endpoint):
    unit = ensure_ou(endpoint, OU)
    ok(endpoint, "TagResource", ResourceId=unit, Tags=[{"Key": "env", "Value": "ops"}])
    tags = ok(endpoint, "ListTagsForResource", ResourceId=unit)["Tags"]
    assert {"Key": "env", "Value": "ops"} in tags


def test_untag_resource_removes_the_key_it_names(endpoint):
    unit = ensure_ou(endpoint, OU)
    ok(endpoint, "TagResource", ResourceId=unit, Tags=[{"Key": "doomed", "Value": "yes"}])
    ok(endpoint, "UntagResource", ResourceId=unit, TagKeys=["doomed"])
    tags = ok(endpoint, "ListTagsForResource", ResourceId=unit)["Tags"]
    assert "doomed" not in {tag["Key"] for tag in tags}


def test_list_tags_for_resource_shows_the_unit_tags(endpoint):
    unit = ensure_ou(endpoint, OU)
    ok(endpoint, "TagResource", ResourceId=unit, Tags=[{"Key": "team", "Value": "platform"}])
    tags = ok(endpoint, "ListTagsForResource", ResourceId=unit)["Tags"]
    assert {"Key": "team", "Value": "platform"} in tags
