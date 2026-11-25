"""WAF Classic / Regional on the wire: the twenty operations the v1 stub names, plus one call per generic family.

The emulator does not implement WAF v1 — `waf_v1` answers shapes, not resources — so these tests
pin the stub's contract instead of behaviour a real service would have. Every List* must answer
the documented member empty, GetChangeToken must mint a fresh uuid4, GetChangeTokenStatus must be
the terminal INSYNC, GetPermissionPolicy must be an empty Policy, and every other Get* must be
refused as WAFNonexistentItemException. That is deliberate and tight: the day v1 is implemented
for real, this module fails and is rewritten, rather than passing on a `200` that means nothing.
Nothing is stored, so nothing is created here and nothing is deleted.
"""

from __future__ import annotations

import json
import uuid

import pytest
import signed
from conftest import ACCOUNT

REGION = "us-east-1"
# `waf_v1.handle_request` splits the target on the first dot, so only the suffix is read.
TARGET = "AWSWAF_20150824."
# The regional prefix reaches the same module (`services["waf-regional"]`), despite its own name.
REGIONAL_TARGET = "AWSWAF_Regional_20161128."
HEADERS = {"Content-Type": "application/x-amz-json-1.1"}

# A v1 identifier that names nothing. The stub reads no argument; a real implementation would
# have to refuse it, which is exactly the failure this module is written to produce.
MISSING_ID = "ops-waf-00000000-0000-4000-8000-000000000000"
MISSING_ARN = f"arn:aws:waf::{ACCOUNT}:ipset/{MISSING_ID}"

# Each List* and the response member a client reads. The module's _LIST_RESULT_KEYS is the
# source of truth; the arguments are the ones the v1 shapes require, so a real implementation
# would answer rather than reject the request itself.
EMPTY_LISTS = {
    "ListActivatedRulesInRuleGroup": ("ActivatedRules", {"RuleGroupId": MISSING_ID}),
    "ListByteMatchSets": ("ByteMatchSets", {}),
    "ListGeoMatchSets": ("GeoMatchSets", {}),
    "ListIPSets": ("IPSets", {}),
    "ListLoggingConfigurations": ("LoggingConfigurations", {}),
    "ListRateBasedRules": ("Rules", {}),
    "ListRegexMatchSets": ("RegexMatchSets", {}),
    "ListRegexPatternSets": ("RegexPatternSets", {}),
    "ListResourcesForWebACL": ("ResourceArns", {"WebACLId": MISSING_ID}),
    "ListRuleGroups": ("RuleGroups", {}),
    "ListRules": ("Rules", {}),
    "ListSizeConstraintSets": ("SizeConstraintSets", {}),
    "ListSqlInjectionMatchSets": ("SqlInjectionMatchSets", {}),
    "ListSubscribedRuleGroups": ("RuleGroups", {}),
    "ListWebACLs": ("WebACLs", {}),
    "ListXssMatchSets": ("XssMatchSets", {}),
}


def call(endpoint, action: str, target: str = TARGET, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": target + action})
    return signed.request(
        endpoint, "waf", ACCOUNT, REGION, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, action: str, **params) -> dict:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def change_token(endpoint) -> str:
    return ok(endpoint, "GetChangeToken")["ChangeToken"]


def token_from(endpoint, action: str, **params) -> str:
    """A write's answer: exactly one ChangeToken, a fresh uuid4 rather than the one sent."""
    answer = ok(endpoint, action, **params)
    assert set(answer) == {"ChangeToken"}, f"{action} answered {sorted(answer)}"
    token = answer["ChangeToken"]
    assert str(uuid.UUID(token)) == token, f"{action} answered a non-uuid token {token!r}"
    sent = params.get("ChangeToken")
    if sent is not None:
        assert token != sent, f"{action} echoed the token it was given"
    return token


@pytest.mark.parametrize("action", sorted(EMPTY_LISTS))
def test_list_operation_answers_the_documented_empty_member(s3_endpoint, action):
    """Every List* answers its own member and nothing else: the stub holds no resources to name."""
    member, params = EMPTY_LISTS[action]
    assert ok(s3_endpoint, action, **params) == {member: []}


def test_list_tags_for_resource_answers_the_empty_tag_struct(s3_endpoint):
    """ListTagsForResource alone answers a struct rather than a list: no ARN and no tags."""
    answer = ok(s3_endpoint, "ListTagsForResource", ResourceArn=MISSING_ARN)
    assert answer == {"TagInfoForResource": {"ResourceARN": "", "TagList": []}}


def test_get_change_token_answers_a_fresh_uuid(s3_endpoint):
    """No token is stored, so every call mints a new uuid4 and the previous one means nothing."""
    first = ok(s3_endpoint, "GetChangeToken")
    second = ok(s3_endpoint, "GetChangeToken")
    assert set(first) == {"ChangeToken"}
    token = first["ChangeToken"]
    assert str(uuid.UUID(token)) == token
    assert second["ChangeToken"] != token


def test_get_change_token_status_is_insync(s3_endpoint):
    """The status a client polls is terminal: this stub never reports a PENDING change."""
    token = change_token(s3_endpoint)
    assert ok(s3_endpoint, "GetChangeTokenStatus", ChangeToken=token) == {
        "ChangeTokenStatus": "INSYNC"
    }


def test_get_permission_policy_is_empty(s3_endpoint):
    """No IAM policy is ever attached, so the answer is the empty string, not a document."""
    assert ok(s3_endpoint, "GetPermissionPolicy", ResourceArn=MISSING_ARN) == {"Policy": ""}


def test_get_is_not_found_because_nothing_is_stored(s3_endpoint):
    """GetIPSet stands for the whole Get* family: only the three named operations answer, the rest refuse."""
    status, text = call(s3_endpoint, "GetIPSet", IPSetId=MISSING_ID)
    assert status == 400, text[:400]
    assert "WAFNonexistentItemException" in text
    assert "does not exist" in text


def test_create_is_a_stub_change_token(s3_endpoint):
    """CreateIPSet stores nothing: the answer is a ChangeToken and no IPSet is returned or kept."""
    token_from(
        s3_endpoint,
        "CreateIPSet",
        Name="ops-waf-ipset",
        ChangeToken=change_token(s3_endpoint),
    )


def test_update_is_a_stub_change_token(s3_endpoint):
    """UpdateIPSet never reaches a resource: the identifier is unread and only a ChangeToken answers."""
    token_from(
        s3_endpoint,
        "UpdateIPSet",
        IPSetId=MISSING_ID,
        ChangeToken=change_token(s3_endpoint),
        Updates=[
            {
                "Action": "INSERT",
                "IPSetDescriptor": {"Type": "IPV4", "Value": "198.51.100.1/32"},
            }
        ],
    )


def test_delete_is_a_stub_change_token(s3_endpoint):
    """DeleteIPSet removes nothing, because nothing was ever stored: a ChangeToken is the whole answer."""
    token_from(
        s3_endpoint,
        "DeleteIPSet",
        IPSetId=MISSING_ID,
        ChangeToken=change_token(s3_endpoint),
    )


def test_associate_is_a_stub_change_token(s3_endpoint):
    """AssociateWebACL records no association: the ARNs are unread and a ChangeToken comes back."""
    token_from(
        s3_endpoint,
        "AssociateWebACL",
        WebACLId=MISSING_ID,
        ResourceArn=MISSING_ARN,
    )


def test_disassociate_is_a_stub_change_token(s3_endpoint):
    """DisassociateWebACL has no association to drop, so it too answers only a ChangeToken."""
    token_from(s3_endpoint, "DisassociateWebACL", ResourceArn=MISSING_ARN)


def test_put_is_a_stub_change_token(s3_endpoint):
    """PutLoggingConfiguration keeps no configuration: the assumed object is unread, a ChangeToken answers."""
    token_from(
        s3_endpoint,
        "PutLoggingConfiguration",
        LoggingConfiguration={
            "ResourceArn": MISSING_ARN,
            "LogDestinationConfigs": [
                f"arn:aws:firehose:{REGION}:{ACCOUNT}:deliverystream/ops-waf"
            ],
        },
    )


def test_tag_resource_is_a_stub_change_token(s3_endpoint):
    """TagResource attaches no tag: ListTagsForResource goes on answering an empty TagList."""
    token_from(
        s3_endpoint,
        "TagResource",
        ResourceARN=MISSING_ARN,
        Tags=[{"Key": "owner", "Value": "emuplane"}],
    )


def test_untag_resource_is_a_stub_change_token(s3_endpoint):
    """UntagResource removes no tag, for the same reason TagResource attaches none."""
    token_from(s3_endpoint, "UntagResource", ResourceARN=MISSING_ARN, TagKeys=["owner"])


def test_an_operation_outside_the_families_is_refused(s3_endpoint):
    """CheckCapacity is neither a List, a named Get nor a write prefix: the stub refuses it by name."""
    status, text = call(s3_endpoint, "CheckCapacity", RuleGroupId=MISSING_ID)
    assert status == 400, text[:400]
    assert "WAFInvalidOperationException" in text
    assert "CheckCapacity" in text


def test_the_regional_target_prefix_reaches_the_same_stub(s3_endpoint):
    """`waf-regional` signs as its own service and names AWSWAF_Regional_20161128; one stub answers both."""
    headers = dict(HEADERS, **{"X-Amz-Target": REGIONAL_TARGET + "ListIPSets"})
    status, text = signed.request(
        s3_endpoint, "waf-regional", ACCOUNT, REGION, "POST", "/", json.dumps({}), headers
    )
    assert status == 200, text[:400]
    assert json.loads(text) == {"IPSets": []}
