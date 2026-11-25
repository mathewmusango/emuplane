"""WAF v2 on the wire: all 29 advertised operations behind ``AWSWAF_20190729``.

A call is a ``POST /`` with ``X-Amz-Target: AWSWAF_20190729.<Action>`` and an
``application/x-amz-json-1.1`` body, signed with the ``wafv2`` credential scope.

The emulator does not make a name unique: every create mints a new id and a new
``LockToken``, so a second sweep of the same lab must find the resource by listing
its scope and matching ``Name`` (+ ``Scope``), then read it back with ``Get*``
rather than create a duplicate. ``UpdateWebACL``, ``DeleteWebACL``,
``UpdateRegexPatternSet``, ``DeleteRegexPatternSet`` and ``UpdateRuleGroup`` all
compare the ``LockToken`` they are handed with the stored one and answer
``WAFOptimisticLockException`` on a mismatch, so every update reads the current
token first and asserts the one it got back. ``UpdateIPSet``, ``DeleteIPSet`` and
``DeleteRuleGroup`` do not check it in this version of the emulator; they are
still handed the current token, as a client would send it.

An update action mutates a resource of its own (``ops-wafv2-webacl-updated``
beside ``ops-wafv2-webacl``) so no create assertion reads a field another test
writes; a delete action finds-or-creates a ``*-doomed`` resource and removes only
that. Nothing else is deleted.

``AssociateWebACL`` resolves the WebACL ARN locally but stores the ``ResourceArn``
as given — no listener or stage has to exist behind it — so the association
fixtures are an ELBv2 listener ARN and an API Gateway stage ARN. The first lists
under the default ``APPLICATION_LOAD_BALANCER`` resource type and the second under
``API_GATEWAY``, which is what ``ListResourcesForWebACL`` filters on.
``CheckCapacity`` answers a fixed capacity and ``DescribeManagedRuleGroup`` names
its label namespace from the vendor and name it is given, so neither needs a
managed rule group to exist.

No operation needs a dependant that cannot be created here, so nothing is skipped.
"""

from __future__ import annotations

import json

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
TARGET = "AWSWAF_20190729."
HEADERS = {"Content-Type": "application/x-amz-json-1.1"}
SCOPE = "REGIONAL"
# A well-formed id nothing was created under, and a token nothing ever issued.
MISSING_ID = "0f0f0f0f-0f0f-4f0f-8f0f-0f0f0f0f0f0f"
STALE_TOKEN = "00000000-0000-4000-8000-000000000000"

WEB_ACL = "ops-wafv2-webacl"
WEB_ACL_UPDATED = "ops-wafv2-webacl-updated"
WEB_ACL_DOOMED = "ops-wafv2-webacl-doomed"
METRIC_WEB_ACL = "opsWafv2WebAcl"
METRIC_WEB_ACL_UPDATED = "opsWafv2WebAclUpdated"

IP_SET = "ops-wafv2-ipset"
IP_SET_UPDATED = "ops-wafv2-ipset-updated"
IP_SET_DOOMED = "ops-wafv2-ipset-doomed"
ADDRESS = "198.51.100.0/24"
ADDRESS_UPDATED = "203.0.113.0/24"

REGEX_SET = "ops-wafv2-regex"
REGEX_SET_UPDATED = "ops-wafv2-regex-updated"
REGEX_SET_DOOMED = "ops-wafv2-regex-doomed"
REGEX = "^ops-[a-z]+$"
REGEX_UPDATED = "^ops-[a-z0-9]+$"

RULE_GROUP = "ops-wafv2-rulegroup"
RULE_GROUP_UPDATED = "ops-wafv2-rulegroup-updated"
RULE_GROUP_DOOMED = "ops-wafv2-rulegroup-doomed"
METRIC_RULE_GROUP = "opsWafv2RuleGroup"
METRIC_RULE = "opsWafv2ManagedRule"
RULE_NAME = "ops-wafv2-managed-rule"
MANAGED_GROUP = "AWSManagedRulesCommonRuleSet"
MANAGED_VENDOR = "AWS"

# The association fixtures: an ALB listener and an API Gateway stage. Neither
# resource has to exist, because only the WebACL side of the pair is resolved.
ALB_ARN = (
    f"arn:aws:elasticloadbalancing:{REGION}:{ACCOUNT}"
    ":listener/app/ops-wafv2-alb/0123456789abcdef/0123456789abcdef"
)
DOOMED_ALB_ARN = (
    f"arn:aws:elasticloadbalancing:{REGION}:{ACCOUNT}"
    ":listener/app/ops-wafv2-doomed/0123456789abcdef/0123456789abcdef"
)
API_GATEWAY_ARN = f"arn:aws:apigateway:{REGION}::/restapis/opswafv2/stages/ops"

MISSING_ACL_ARN = (
    f"arn:aws:wafv2:{REGION}:{ACCOUNT}:regional/webacl/ops-wafv2-missing/{MISSING_ID}"
)
OTHER_ACCOUNT_ARN = (
    f"arn:aws:wafv2:{REGION}:999999999999:regional/webacl/{WEB_ACL}/{MISSING_ID}"
)

TAG_CREATED = "ops-created"
TAG_KEPT = "ops-kept"
TAG_DOOMED = "ops-doomed"


# ---------------------------------------------------------------------------
# The wire
# ---------------------------------------------------------------------------


def call(endpoint, action: str, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "wafv2", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, action: str, **params) -> dict:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def refused(endpoint, action: str, code: str, **params) -> str:
    """One call that must be answered with ``code``; returns the message."""
    status, text = call(endpoint, action, **params)
    assert status == 400, f"{action} answered {status}: {text[:400]}"
    assert code in text, f"{action} answered {status}: {text[:400]}"
    return text


def visibility(metric: str) -> dict:
    return {
        "SampledRequestsEnabled": True,
        "CloudWatchMetricsEnabled": True,
        "MetricName": metric,
    }


def managed_rule() -> dict:
    """A rule with no dependant: a managed group is named, never deployed."""
    return {
        "Name": RULE_NAME,
        "Priority": 1,
        "Action": {"Block": {}},
        "Statement": {
            "ManagedRuleGroupStatement": {
                "VendorName": MANAGED_VENDOR,
                "Name": MANAGED_GROUP,
            }
        },
        "VisibilityConfig": visibility(METRIC_RULE),
    }


def listing(endpoint, action: str, key: str, scope: str = SCOPE) -> list[dict]:
    """Every page of one scoped listing: a lab may hold more than ``Limit`` items."""
    found: list[dict] = []
    marker = None
    while True:
        params = {"Scope": scope, "Limit": 100}
        if marker:
            params["NextMarker"] = marker
        page = ok(endpoint, action, **params)
        found.extend(page.get(key, []))
        marker = page.get("NextMarker")
        if not marker:
            return found


def named(rows: list[dict], name: str) -> dict | None:
    return next((row for row in rows if row.get("Name") == name), None)


def arn_for(kind: str, name: str, uid: str) -> str:
    return f"arn:aws:wafv2:{REGION}:{ACCOUNT}:regional/{kind}/{name}/{uid}"


# ---------------------------------------------------------------------------
# Fixtures — find-or-create by name, then read the current LockToken
# ---------------------------------------------------------------------------


def ensure_web_acl(endpoint, name: str = WEB_ACL, metric: str = METRIC_WEB_ACL) -> dict:
    """``{"WebACL": ..., "LockToken": ...}`` for the named ACL, creating it once."""
    found = named(listing(endpoint, "ListWebACLs", "WebACLs"), name)
    if found is None:
        found = ok(
            endpoint,
            "CreateWebACL",
            Name=name,
            Scope=SCOPE,
            DefaultAction={"Allow": {}},
            VisibilityConfig=visibility(metric),
            Rules=[],
            Description="ops fixture",
        )["Summary"]
    return ok(endpoint, "GetWebACL", Id=found["Id"], Scope=SCOPE)


def ensure_ip_set(endpoint, name: str = IP_SET) -> dict:
    found = named(listing(endpoint, "ListIPSets", "IPSets"), name)
    if found is None:
        found = ok(
            endpoint,
            "CreateIPSet",
            Name=name,
            Scope=SCOPE,
            IPAddressVersion="IPV4",
            Addresses=[ADDRESS],
            Description="ops fixture",
        )["Summary"]
    return ok(endpoint, "GetIPSet", Id=found["Id"], Scope=SCOPE)


def ensure_regex_pattern_set(endpoint, name: str = REGEX_SET) -> dict:
    found = named(listing(endpoint, "ListRegexPatternSets", "RegexPatternSets"), name)
    if found is None:
        found = ok(
            endpoint,
            "CreateRegexPatternSet",
            Name=name,
            Scope=SCOPE,
            RegularExpressionList=[{"RegexString": REGEX}],
            Description="ops fixture",
        )["Summary"]
    return ok(endpoint, "GetRegexPatternSet", Id=found["Id"], Scope=SCOPE)


def ensure_rule_group(
    endpoint,
    name: str = RULE_GROUP,
    metric: str = METRIC_RULE_GROUP,
    rules: list[dict] | None = None,
) -> dict:
    found = named(listing(endpoint, "ListRuleGroups", "RuleGroups"), name)
    if found is None:
        found = ok(
            endpoint,
            "CreateRuleGroup",
            Name=name,
            Scope=SCOPE,
            Capacity=100,
            Rules=rules or [],
            VisibilityConfig=visibility(metric),
            Description="ops fixture",
        )["Summary"]
    return ok(endpoint, "GetRuleGroup", Id=found["Id"], Scope=SCOPE)


def associate(endpoint, web_acl_arn: str, resource_arn: str) -> None:
    """AssociateWebACL upserts, so a re-run leaves the same pairing in place."""
    ok(endpoint, "AssociateWebACL", WebACLArn=web_acl_arn, ResourceArn=resource_arn)


# ---------------------------------------------------------------------------
# WebACL — CreateWebACL, GetWebACL, ListWebACLs, UpdateWebACL, DeleteWebACL
# ---------------------------------------------------------------------------


def test_create_web_acl_is_read_back_by_get_web_acl(endpoint):
    status, text = call(
        endpoint,
        "CreateWebACL",
        Name=WEB_ACL,
        Scope=SCOPE,
        DefaultAction={"Allow": {}},
        VisibilityConfig=visibility(METRIC_WEB_ACL),
        Rules=[],
        Description="ops fixture",
    )
    if status == 200:
        summary = json.loads(text)["Summary"]
        assert summary["Name"] == WEB_ACL
        assert summary["ARN"].startswith(
            f"arn:aws:wafv2:{REGION}:{ACCOUNT}:regional/webacl/{WEB_ACL}/"
        )
        assert summary["Id"] and summary["LockToken"]
    else:
        # A second sweep re-runs against the ACL the first one deliberately left.
        assert status == 400 and "WAFDuplicateItemException" in text, (
            f"CreateWebACL answered {status}: {text[:400]}"
        )

    read = ensure_web_acl(endpoint)
    acl = read["WebACL"]
    assert acl["Name"] == WEB_ACL
    assert acl["ARN"] == arn_for("webacl", WEB_ACL, acl["Id"])
    assert acl["DefaultAction"] == {"Allow": {}}
    assert acl["VisibilityConfig"]["MetricName"] == METRIC_WEB_ACL
    assert acl["Rules"] == []
    assert read["LockToken"]

    refused(endpoint, "GetWebACL", "WAFNonexistentItemException", Id=MISSING_ID, Scope=SCOPE)
    # AWS validates the id shape before it looks the ACL up.
    message = refused(endpoint, "GetWebACL", "ValidationException", Id="ops-not-a-uuid", Scope=SCOPE)
    assert "regular expression pattern" in message


def test_list_web_acls_includes_the_shared_acl(endpoint):
    read = ensure_web_acl(endpoint)
    row = named(listing(endpoint, "ListWebACLs", "WebACLs"), WEB_ACL)
    assert row["Id"] == read["WebACL"]["Id"]
    assert row["ARN"] == read["WebACL"]["ARN"]
    assert row["LockToken"] == read["LockToken"]


def test_update_web_acl_rolls_the_lock_token(endpoint):
    read = ensure_web_acl(endpoint, WEB_ACL_UPDATED, METRIC_WEB_ACL_UPDATED)
    acl_id = read["WebACL"]["Id"]

    refused(
        endpoint,
        "UpdateWebACL",
        "WAFOptimisticLockException",
        Id=acl_id,
        Scope=SCOPE,
        LockToken=STALE_TOKEN,
        DefaultAction={"Block": {}},
        VisibilityConfig=visibility(METRIC_WEB_ACL_UPDATED),
        Rules=[managed_rule()],
    )

    answer = ok(
        endpoint,
        "UpdateWebACL",
        Id=acl_id,
        Scope=SCOPE,
        LockToken=read["LockToken"],
        DefaultAction={"Block": {}},
        VisibilityConfig=visibility(METRIC_WEB_ACL_UPDATED),
        Rules=[managed_rule()],
        Description="ops updated",
    )
    assert answer["NextLockToken"] != read["LockToken"]

    updated = ok(endpoint, "GetWebACL", Id=acl_id, Scope=SCOPE)
    assert updated["LockToken"] == answer["NextLockToken"]
    assert updated["WebACL"]["DefaultAction"] == {"Block": {}}
    assert updated["WebACL"]["Description"] == "ops updated"
    assert [rule["Name"] for rule in updated["WebACL"]["Rules"]] == [RULE_NAME]

    refused(
        endpoint,
        "UpdateWebACL",
        "WAFNonexistentItemException",
        Id=MISSING_ID,
        Scope=SCOPE,
        LockToken=STALE_TOKEN,
        DefaultAction={"Allow": {}},
        VisibilityConfig=visibility(METRIC_WEB_ACL_UPDATED),
        Rules=[],
    )


def test_delete_web_acl_removes_only_the_acl_it_created(endpoint):
    read = ensure_web_acl(endpoint, WEB_ACL_DOOMED, METRIC_WEB_ACL_UPDATED)
    acl_id = read["WebACL"]["Id"]

    refused(
        endpoint,
        "DeleteWebACL",
        "WAFOptimisticLockException",
        Id=acl_id,
        Scope=SCOPE,
        LockToken=STALE_TOKEN,
    )
    # The refusal changed nothing.
    assert ok(endpoint, "GetWebACL", Id=acl_id, Scope=SCOPE)["LockToken"] == read["LockToken"]

    ok(endpoint, "DeleteWebACL", Id=acl_id, Scope=SCOPE, LockToken=read["LockToken"])
    refused(endpoint, "GetWebACL", "WAFNonexistentItemException", Id=acl_id, Scope=SCOPE)
    refused(
        endpoint,
        "DeleteWebACL",
        "WAFNonexistentItemException",
        Id=acl_id,
        Scope=SCOPE,
        LockToken=read["LockToken"],
    )
    assert WEB_ACL_DOOMED not in {row["Name"] for row in listing(endpoint, "ListWebACLs", "WebACLs")}
    # The shared ACL is untouched.
    assert WEB_ACL in {row["Name"] for row in listing(endpoint, "ListWebACLs", "WebACLs")}


# ---------------------------------------------------------------------------
# Association — AssociateWebACL, GetWebACLForResource, ListResourcesForWebACL,
# DisassociateWebACL
# ---------------------------------------------------------------------------


def test_associate_web_acl_is_read_back_by_get_web_acl_for_resource(endpoint):
    acl = ensure_web_acl(endpoint)["WebACL"]

    associate(endpoint, acl["ARN"], ALB_ARN)
    read_back = ok(endpoint, "GetWebACLForResource", ResourceArn=ALB_ARN)["WebACL"]
    assert read_back["ARN"] == acl["ARN"]
    assert read_back["Id"] == acl["Id"]

    # The API Gateway association is the second half of the resource-type filter.
    associate(endpoint, acl["ARN"], API_GATEWAY_ARN)
    assert (
        ok(endpoint, "GetWebACLForResource", ResourceArn=API_GATEWAY_ARN)["WebACL"]["ARN"]
        == acl["ARN"]
    )

    refused(
        endpoint,
        "GetWebACLForResource",
        "WAFNonexistentItemException",
        ResourceArn=f"arn:aws:apigateway:{REGION}::/restapis/ops-unassociated/stages/ops",
    )
    refused(
        endpoint,
        "AssociateWebACL",
        "WAFNonexistentItemException",
        WebACLArn=MISSING_ACL_ARN,
        ResourceArn=ALB_ARN,
    )
    refused(
        endpoint,
        "AssociateWebACL",
        "WAFInvalidParameterException",
        WebACLArn="not-an-arn",
        ResourceArn=ALB_ARN,
    )


def test_list_resources_for_web_acl_filters_by_resource_type(endpoint):
    acl = ensure_web_acl(endpoint)["WebACL"]
    associate(endpoint, acl["ARN"], ALB_ARN)
    associate(endpoint, acl["ARN"], API_GATEWAY_ARN)

    # No ResourceType means APPLICATION_LOAD_BALANCER.
    load_balancers = ok(endpoint, "ListResourcesForWebACL", WebACLArn=acl["ARN"])["ResourceArns"]
    assert ALB_ARN in load_balancers
    assert API_GATEWAY_ARN not in load_balancers

    gateways = ok(
        endpoint,
        "ListResourcesForWebACL",
        WebACLArn=acl["ARN"],
        ResourceType="API_GATEWAY",
    )["ResourceArns"]
    assert API_GATEWAY_ARN in gateways
    assert ALB_ARN not in gateways

    refused(
        endpoint,
        "ListResourcesForWebACL",
        "WAFNonexistentItemException",
        WebACLArn=MISSING_ACL_ARN,
    )


def test_disassociate_web_acl_removes_only_the_association_it_created(endpoint):
    acl = ensure_web_acl(endpoint)["WebACL"]
    associate(endpoint, acl["ARN"], ALB_ARN)
    associate(endpoint, acl["ARN"], DOOMED_ALB_ARN)
    assert (
        ok(endpoint, "GetWebACLForResource", ResourceArn=DOOMED_ALB_ARN)["WebACL"]["ARN"]
        == acl["ARN"]
    )

    ok(endpoint, "DisassociateWebACL", ResourceArn=DOOMED_ALB_ARN)
    refused(
        endpoint,
        "GetWebACLForResource",
        "WAFNonexistentItemException",
        ResourceArn=DOOMED_ALB_ARN,
    )
    remaining = ok(endpoint, "ListResourcesForWebACL", WebACLArn=acl["ARN"])["ResourceArns"]
    assert DOOMED_ALB_ARN not in remaining
    assert ALB_ARN in remaining

    # Disassociating a pair that is already gone is not an error.
    ok(endpoint, "DisassociateWebACL", ResourceArn=DOOMED_ALB_ARN)


# ---------------------------------------------------------------------------
# IPSet — CreateIPSet, GetIPSet, UpdateIPSet, DeleteIPSet, ListIPSets
# ---------------------------------------------------------------------------


def test_create_ip_set_is_read_back_by_get_ip_set(endpoint):
    read = ensure_ip_set(endpoint)
    ip_set = read["IPSet"]
    assert ip_set["Name"] == IP_SET
    assert ip_set["ARN"] == arn_for("ipset", IP_SET, ip_set["Id"])
    assert ip_set["IPAddressVersion"] == "IPV4"
    assert ip_set["Addresses"] == [ADDRESS]
    assert read["LockToken"]

    refused(endpoint, "GetIPSet", "WAFNonexistentItemException", Id=MISSING_ID, Scope=SCOPE)


def test_list_ip_sets_includes_the_shared_set(endpoint):
    read = ensure_ip_set(endpoint)
    row = named(listing(endpoint, "ListIPSets", "IPSets"), IP_SET)
    assert row["Id"] == read["IPSet"]["Id"]
    assert row["ARN"] == read["IPSet"]["ARN"]
    assert row["LockToken"] == read["LockToken"]


def test_update_ip_set_changes_its_addresses(endpoint):
    read = ensure_ip_set(endpoint, IP_SET_UPDATED)
    ip_set_id = read["IPSet"]["Id"]

    answer = ok(
        endpoint,
        "UpdateIPSet",
        Id=ip_set_id,
        Scope=SCOPE,
        LockToken=read["LockToken"],
        Addresses=[ADDRESS_UPDATED],
        Description="ops updated",
    )
    assert answer["NextLockToken"] != read["LockToken"]

    updated = ok(endpoint, "GetIPSet", Id=ip_set_id, Scope=SCOPE)
    assert updated["LockToken"] == answer["NextLockToken"]
    assert updated["IPSet"]["Addresses"] == [ADDRESS_UPDATED]
    assert updated["IPSet"]["Description"] == "ops updated"

    refused(
        endpoint,
        "UpdateIPSet",
        "WAFNonexistentItemException",
        Id=MISSING_ID,
        Scope=SCOPE,
        Addresses=[ADDRESS],
    )


def test_delete_ip_set_removes_only_the_set_it_created(endpoint):
    read = ensure_ip_set(endpoint, IP_SET_DOOMED)
    ip_set_id = read["IPSet"]["Id"]

    ok(endpoint, "DeleteIPSet", Id=ip_set_id, Scope=SCOPE, LockToken=read["LockToken"])
    refused(endpoint, "GetIPSet", "WAFNonexistentItemException", Id=ip_set_id, Scope=SCOPE)
    refused(
        endpoint,
        "DeleteIPSet",
        "WAFNonexistentItemException",
        Id=ip_set_id,
        Scope=SCOPE,
        LockToken=read["LockToken"],
    )
    assert IP_SET_DOOMED not in {row["Name"] for row in listing(endpoint, "ListIPSets", "IPSets")}
    assert IP_SET in {row["Name"] for row in listing(endpoint, "ListIPSets", "IPSets")}


# ---------------------------------------------------------------------------
# RegexPatternSet — CreateRegexPatternSet, GetRegexPatternSet,
# UpdateRegexPatternSet, DeleteRegexPatternSet, ListRegexPatternSets
# ---------------------------------------------------------------------------


def test_create_regex_pattern_set_is_read_back_by_get_regex_pattern_set(endpoint):
    read = ensure_regex_pattern_set(endpoint)
    regex_set = read["RegexPatternSet"]
    assert regex_set["Name"] == REGEX_SET
    assert regex_set["ARN"] == arn_for("regexpatternset", REGEX_SET, regex_set["Id"])
    assert regex_set["RegularExpressionList"] == [{"RegexString": REGEX}]
    assert read["LockToken"]

    refused(endpoint, "CreateRegexPatternSet", "WAFInvalidParameterException", Scope=SCOPE)
    refused(
        endpoint,
        "GetRegexPatternSet",
        "WAFNonexistentItemException",
        Id=MISSING_ID,
        Scope=SCOPE,
    )


def test_list_regex_pattern_sets_includes_the_shared_set(endpoint):
    read = ensure_regex_pattern_set(endpoint)
    row = named(listing(endpoint, "ListRegexPatternSets", "RegexPatternSets"), REGEX_SET)
    assert row["Id"] == read["RegexPatternSet"]["Id"]
    assert row["ARN"] == read["RegexPatternSet"]["ARN"]
    assert row["LockToken"] == read["LockToken"]


def test_update_regex_pattern_set_rejects_a_stale_lock_token(endpoint):
    read = ensure_regex_pattern_set(endpoint, REGEX_SET_UPDATED)
    regex_set_id = read["RegexPatternSet"]["Id"]

    refused(
        endpoint,
        "UpdateRegexPatternSet",
        "WAFOptimisticLockException",
        Id=regex_set_id,
        Scope=SCOPE,
        LockToken=STALE_TOKEN,
        RegularExpressionList=[{"RegexString": REGEX_UPDATED}],
    )

    answer = ok(
        endpoint,
        "UpdateRegexPatternSet",
        Id=regex_set_id,
        Scope=SCOPE,
        LockToken=read["LockToken"],
        RegularExpressionList=[{"RegexString": REGEX_UPDATED}],
        Description="ops updated",
    )
    assert answer["NextLockToken"] != read["LockToken"]

    updated = ok(endpoint, "GetRegexPatternSet", Id=regex_set_id, Scope=SCOPE)
    assert updated["LockToken"] == answer["NextLockToken"]
    assert updated["RegexPatternSet"]["RegularExpressionList"] == [
        {"RegexString": REGEX_UPDATED}
    ]
    assert updated["RegexPatternSet"]["Description"] == "ops updated"


def test_delete_regex_pattern_set_removes_only_the_set_it_created(endpoint):
    read = ensure_regex_pattern_set(endpoint, REGEX_SET_DOOMED)
    regex_set_id = read["RegexPatternSet"]["Id"]

    refused(
        endpoint,
        "DeleteRegexPatternSet",
        "WAFOptimisticLockException",
        Id=regex_set_id,
        Scope=SCOPE,
        LockToken=STALE_TOKEN,
    )
    assert ok(endpoint, "GetRegexPatternSet", Id=regex_set_id, Scope=SCOPE)["LockToken"] == read["LockToken"]

    ok(
        endpoint,
        "DeleteRegexPatternSet",
        Id=regex_set_id,
        Scope=SCOPE,
        LockToken=read["LockToken"],
    )
    refused(
        endpoint,
        "GetRegexPatternSet",
        "WAFNonexistentItemException",
        Id=regex_set_id,
        Scope=SCOPE,
    )
    assert REGEX_SET_DOOMED not in {
        row["Name"] for row in listing(endpoint, "ListRegexPatternSets", "RegexPatternSets")
    }
    assert REGEX_SET in {
        row["Name"] for row in listing(endpoint, "ListRegexPatternSets", "RegexPatternSets")
    }


# ---------------------------------------------------------------------------
# RuleGroup — CreateRuleGroup, GetRuleGroup, UpdateRuleGroup, DeleteRuleGroup,
# ListRuleGroups
# ---------------------------------------------------------------------------


def test_create_rule_group_is_read_back_by_get_rule_group(endpoint):
    read = ensure_rule_group(endpoint)
    group = read["RuleGroup"]
    assert group["Name"] == RULE_GROUP
    assert group["ARN"] == arn_for("rulegroup", RULE_GROUP, group["Id"])
    assert group["Capacity"] == 100
    assert group["Rules"] == []
    assert group["VisibilityConfig"]["MetricName"] == METRIC_RULE_GROUP
    assert read["LockToken"]

    refused(endpoint, "GetRuleGroup", "WAFNonexistentItemException", Id=MISSING_ID, Scope=SCOPE)


def test_list_rule_groups_includes_the_shared_group(endpoint):
    read = ensure_rule_group(endpoint)
    row = named(listing(endpoint, "ListRuleGroups", "RuleGroups"), RULE_GROUP)
    assert row["Id"] == read["RuleGroup"]["Id"]
    assert row["ARN"] == read["RuleGroup"]["ARN"]
    assert row["LockToken"] == read["LockToken"]


def test_update_rule_group_rejects_a_stale_lock_token(endpoint):
    read = ensure_rule_group(endpoint, RULE_GROUP_UPDATED)
    group_id = read["RuleGroup"]["Id"]

    refused(
        endpoint,
        "UpdateRuleGroup",
        "WAFOptimisticLockException",
        Id=group_id,
        Scope=SCOPE,
        LockToken=STALE_TOKEN,
        Rules=[managed_rule()],
        VisibilityConfig=visibility(METRIC_RULE_GROUP),
    )

    answer = ok(
        endpoint,
        "UpdateRuleGroup",
        Id=group_id,
        Scope=SCOPE,
        LockToken=read["LockToken"],
        Rules=[managed_rule()],
        VisibilityConfig=visibility(METRIC_RULE_GROUP),
        Description="ops updated",
    )
    assert answer["NextLockToken"] != read["LockToken"]

    updated = ok(endpoint, "GetRuleGroup", Id=group_id, Scope=SCOPE)
    assert updated["LockToken"] == answer["NextLockToken"]
    assert [rule["Name"] for rule in updated["RuleGroup"]["Rules"]] == [RULE_NAME]
    assert updated["RuleGroup"]["Description"] == "ops updated"


def test_delete_rule_group_removes_only_the_group_it_created(endpoint):
    read = ensure_rule_group(endpoint, RULE_GROUP_DOOMED)
    group_id = read["RuleGroup"]["Id"]

    ok(endpoint, "DeleteRuleGroup", Id=group_id, Scope=SCOPE, LockToken=read["LockToken"])
    refused(endpoint, "GetRuleGroup", "WAFNonexistentItemException", Id=group_id, Scope=SCOPE)
    refused(
        endpoint,
        "DeleteRuleGroup",
        "WAFNonexistentItemException",
        Id=group_id,
        Scope=SCOPE,
        LockToken=read["LockToken"],
    )
    assert RULE_GROUP_DOOMED not in {
        row["Name"] for row in listing(endpoint, "ListRuleGroups", "RuleGroups")
    }
    assert RULE_GROUP in {row["Name"] for row in listing(endpoint, "ListRuleGroups", "RuleGroups")}


# ---------------------------------------------------------------------------
# Tags — TagResource, UntagResource, ListTagsForResource
# ---------------------------------------------------------------------------


def tags_on(endpoint, arn: str) -> dict[str, str]:
    answer = ok(endpoint, "ListTagsForResource", ResourceARN=arn)["TagInfoForResource"]
    assert answer["ResourceARN"] == arn
    return {tag["Key"]: tag["Value"] for tag in answer["TagList"]}


def test_tag_resource_is_read_back_by_list_tags_for_resource(endpoint):
    acl = ensure_web_acl(endpoint)["WebACL"]
    ok(
        endpoint,
        "TagResource",
        ResourceARN=acl["ARN"],
        Tags=[{"Key": TAG_CREATED, "Value": "yes"}, {"Key": TAG_KEPT, "Value": "yes"}],
    )
    tags = tags_on(endpoint, acl["ARN"])
    assert tags[TAG_CREATED] == "yes"
    assert tags[TAG_KEPT] == "yes"

    refused(
        endpoint,
        "TagResource",
        "WAFNonexistentItemException",
        ResourceARN=MISSING_ACL_ARN,
        Tags=[{"Key": TAG_CREATED, "Value": "yes"}],
    )
    refused(
        endpoint,
        "TagResource",
        "WAFInvalidParameterException",
        ResourceARN=OTHER_ACCOUNT_ARN,
        Tags=[{"Key": TAG_CREATED, "Value": "yes"}],
    )


def test_untag_resource_removes_only_the_named_tag(endpoint):
    acl = ensure_web_acl(endpoint)["WebACL"]
    ok(
        endpoint,
        "TagResource",
        ResourceARN=acl["ARN"],
        Tags=[{"Key": TAG_DOOMED, "Value": "yes"}, {"Key": TAG_KEPT, "Value": "yes"}],
    )
    assert TAG_DOOMED in tags_on(endpoint, acl["ARN"])

    ok(endpoint, "UntagResource", ResourceARN=acl["ARN"], TagKeys=[TAG_DOOMED])
    remaining = tags_on(endpoint, acl["ARN"])
    assert TAG_DOOMED not in remaining
    assert remaining[TAG_KEPT] == "yes"

    refused(
        endpoint,
        "UntagResource",
        "WAFNonexistentItemException",
        ResourceARN=MISSING_ACL_ARN,
        TagKeys=[TAG_KEPT],
    )


# ---------------------------------------------------------------------------
# Misc — CheckCapacity, DescribeManagedRuleGroup
# ---------------------------------------------------------------------------


def test_check_capacity_answers_a_capacity(endpoint):
    answer = ok(
        endpoint,
        "CheckCapacity",
        Scope=SCOPE,
        Rules=[managed_rule()],
    )
    assert answer["Capacity"] >= 1


def test_describe_managed_rule_group_names_its_label_namespace(endpoint):
    answer = ok(
        endpoint,
        "DescribeManagedRuleGroup",
        Scope=SCOPE,
        VendorName=MANAGED_VENDOR,
        Name=MANAGED_GROUP,
        VersionName="Version_1.0",
    )
    assert answer["VersionName"]
    assert answer["Capacity"] > 0
    assert answer["LabelNamespace"] == f"awswaf:managed:{MANAGED_VENDOR}:{MANAGED_GROUP}:"
