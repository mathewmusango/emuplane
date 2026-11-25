"""OpenSearch Serverless on the wire: all 19 advertised operations, JSON 1.0.

The control plane targets `OpenSearchServerless.<Op>` under the `aoss` signing
name. A collection needs a matching encryption security policy before it can be
created; provisioning is asynchronous, so the helpers wait for `ACTIVE`.
Collections and policies are keyed by name.
"""

from __future__ import annotations

import json
import time

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
PREFIX = "OpenSearchServerless"
JSON_TYPE = {"Content-Type": "application/x-amz-json-1.0"}
COLLECTION = "ops-aoss"
ENC_POLICY = "ops-aoss-enc"


def call(endpoint, action: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    headers = {"X-Amz-Target": f"{PREFIX}.{action}", **JSON_TYPE}
    return signed.request(endpoint, "aoss", ACCOUNT, REGION, "POST", "/", body, headers)


def ok(endpoint, action: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, action, payload)
    assert status == 200, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def refused(endpoint, action: str, payload: dict | None = None) -> str:
    status, text = call(endpoint, action, payload)
    assert status >= 400, f"{action} unexpectedly answered {status}: {text[:400]}"
    return text


def encryption_policy(name: str, policy_name: str) -> dict:
    doc = {"Rules": [{"ResourceType": "collection", "Resource": [f"collection/{name}"]}], "AWSOwnedKey": True}
    return {"name": policy_name, "type": "encryption", "policy": json.dumps(doc)}


def ensure_encryption_policy(endpoint, name: str, policy_name: str) -> None:
    status, text = call(endpoint, "CreateSecurityPolicy", encryption_policy(name, policy_name))
    assert status == 200 or "ConflictException" in text, text[:300]


def detail_by_name(endpoint, name: str) -> dict:
    answer = ok(endpoint, "BatchGetCollection", {"names": [name]})
    return {item["name"]: item for item in answer["collectionDetails"]}[name]


def wait_active(endpoint, name: str) -> dict:
    detail = detail_by_name(endpoint, name)
    for _ in range(50):
        if detail["status"] == "ACTIVE":
            return detail
        time.sleep(0.1)
        detail = detail_by_name(endpoint, name)
    return detail


def ensure_collection(endpoint, name: str = COLLECTION, policy_name: str = ENC_POLICY) -> dict:
    ensure_encryption_policy(endpoint, name, policy_name)
    status, text = call(endpoint, "CreateCollection", {"name": name, "type": "TIMESERIES", "standbyReplicas": "DISABLED"})
    assert status == 200 or "ConflictException" in text, text[:300]
    return wait_active(endpoint, name)


def new_collection(endpoint, prefix: str) -> dict:
    name = f"{prefix}-{time.time_ns() % 10000000}"
    ensure_encryption_policy(endpoint, name, f"{prefix}-enc-{time.time_ns() % 10000000}")
    return ok(endpoint, "CreateCollection", {"name": name, "type": "TIMESERIES", "standbyReplicas": "DISABLED"})[
        "createCollectionDetail"
    ]


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


def test_create_collection_is_read_back(endpoint):
    created = new_collection(endpoint, "ops-aoss-create")
    detail = wait_active(endpoint, created["name"])
    assert detail["name"] == created["name"]


def test_batch_get_collection_reads_the_collection(endpoint):
    ensure_collection(endpoint)
    assert detail_by_name(endpoint, COLLECTION)["name"] == COLLECTION


def test_list_collections_lists_the_collection(endpoint):
    ensure_collection(endpoint)
    names = [item["name"] for item in ok(endpoint, "ListCollections")["collectionSummaries"]]
    assert COLLECTION in names


def test_update_collection_changes_the_description(endpoint):
    detail = ensure_collection(endpoint)
    updated = ok(endpoint, "UpdateCollection", {"id": detail["id"], "description": "updated"})["updateCollectionDetail"]
    assert updated["description"] == "updated"


def test_delete_collection_removes_the_collection_it_created(endpoint):
    created = new_collection(endpoint, "ops-aoss-del")
    detail = wait_active(endpoint, created["name"])
    ok(endpoint, "DeleteCollection", {"id": detail["id"]})
    answer = ok(endpoint, "BatchGetCollection", {"names": [detail["name"]]})
    assert answer["collectionDetails"] == []


# ---------------------------------------------------------------------------
# Security policies
# ---------------------------------------------------------------------------


def test_create_security_policy_is_read_back(endpoint):
    name = f"ops-sec-{time.time_ns() % 10000000}"
    ok(endpoint, "CreateSecurityPolicy", encryption_policy(f"sec-{name}", name))
    got = ok(endpoint, "GetSecurityPolicy", {"type": "encryption", "name": name})
    assert got["securityPolicyDetail"]["name"] == name


def test_get_security_policy_reads_the_policy(endpoint):
    name = f"ops-sec-{time.time_ns() % 10000000}"
    ok(endpoint, "CreateSecurityPolicy", encryption_policy(f"sec-{name}", name))
    assert ok(endpoint, "GetSecurityPolicy", {"type": "encryption", "name": name})["securityPolicyDetail"]["type"] == "encryption"


def test_update_security_policy_changes_the_description(endpoint):
    name = f"ops-sec-{time.time_ns() % 10000000}"
    ok(endpoint, "CreateSecurityPolicy", encryption_policy(f"sec-{name}", name))
    current = ok(endpoint, "GetSecurityPolicy", {"type": "encryption", "name": name})["securityPolicyDetail"]
    body = {
        "name": name,
        "type": "encryption",
        "policyVersion": current["policyVersion"],
        "description": "updated",
    }
    ok(endpoint, "UpdateSecurityPolicy", body)
    got = ok(endpoint, "GetSecurityPolicy", {"type": "encryption", "name": name})["securityPolicyDetail"]
    assert got["description"] == "updated"


def test_delete_security_policy_removes_the_policy_it_created(endpoint):
    name = f"ops-sec-del-{time.time_ns() % 10000000}"
    ok(endpoint, "CreateSecurityPolicy", encryption_policy(f"sec-{name}", name))
    ok(endpoint, "DeleteSecurityPolicy", {"type": "encryption", "name": name})
    refused(endpoint, "GetSecurityPolicy", {"type": "encryption", "name": name})


def test_list_security_policies_lists_the_policy(endpoint):
    name = f"ops-sec-{time.time_ns() % 10000000}"
    ok(endpoint, "CreateSecurityPolicy", encryption_policy(f"sec-{name}", name))
    names = [item["name"] for item in ok(endpoint, "ListSecurityPolicies", {"type": "encryption"})["securityPolicySummaries"]]
    assert name in names


# ---------------------------------------------------------------------------
# Access policies
# ---------------------------------------------------------------------------


def access_policy(name: str) -> dict:
    doc = [
        {
            "Rules": [
                {
                    "ResourceType": "collection",
                    "Resource": [f"collection/{name}"],
                    "Permission": ["aoss:DescribeCollectionItems"],
                }
            ],
            "Principal": [f"arn:aws:iam::{ACCOUNT}:root"],
        }
    ]
    return {"name": name, "type": "data", "policy": json.dumps(doc)}


def test_create_access_policy_is_read_back(endpoint):
    name = f"ops-data-{time.time_ns() % 10000000}"
    ok(endpoint, "CreateAccessPolicy", access_policy(name))
    assert ok(endpoint, "GetAccessPolicy", {"type": "data", "name": name})["accessPolicyDetail"]["name"] == name


def test_get_access_policy_reads_the_policy(endpoint):
    name = f"ops-data-{time.time_ns() % 10000000}"
    ok(endpoint, "CreateAccessPolicy", access_policy(name))
    assert ok(endpoint, "GetAccessPolicy", {"type": "data", "name": name})["accessPolicyDetail"]["type"] == "data"


def test_update_access_policy_changes_the_description(endpoint):
    name = f"ops-data-{time.time_ns() % 10000000}"
    ok(endpoint, "CreateAccessPolicy", access_policy(name))
    current = ok(endpoint, "GetAccessPolicy", {"type": "data", "name": name})["accessPolicyDetail"]
    ok(endpoint, "UpdateAccessPolicy", {"name": name, "type": "data", "policyVersion": current["policyVersion"], "description": "updated"})
    assert ok(endpoint, "GetAccessPolicy", {"type": "data", "name": name})["accessPolicyDetail"]["description"] == "updated"


def test_delete_access_policy_removes_the_policy_it_created(endpoint):
    name = f"ops-data-del-{time.time_ns() % 10000000}"
    ok(endpoint, "CreateAccessPolicy", access_policy(name))
    ok(endpoint, "DeleteAccessPolicy", {"type": "data", "name": name})
    refused(endpoint, "GetAccessPolicy", {"type": "data", "name": name})


def test_list_access_policies_lists_the_policy(endpoint):
    name = f"ops-data-{time.time_ns() % 10000000}"
    ok(endpoint, "CreateAccessPolicy", access_policy(name))
    names = [item["name"] for item in ok(endpoint, "ListAccessPolicies", {"type": "data"})["accessPolicySummaries"]]
    assert name in names


def test_get_policies_stats_answers_the_counts(endpoint):
    stats = ok(endpoint, "GetPoliciesStats")
    assert "TotalPolicyCount" in stats


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def test_tag_resource_is_read_back_by_list_tags(endpoint):
    arn = ensure_collection(endpoint)["arn"]
    ok(endpoint, "TagResource", {"resourceArn": arn, "tags": [{"key": "env", "value": "ops"}]})
    assert {"key": "env", "value": "ops"} in ok(endpoint, "ListTagsForResource", {"resourceArn": arn})["tags"]


def test_untag_resource_removes_the_key_it_names(endpoint):
    arn = ensure_collection(endpoint)["arn"]
    ok(endpoint, "TagResource", {"resourceArn": arn, "tags": [{"key": "doomed", "value": "yes"}]})
    ok(endpoint, "UntagResource", {"resourceArn": arn, "tagKeys": ["doomed"]})
    assert "doomed" not in {tag["key"] for tag in ok(endpoint, "ListTagsForResource", {"resourceArn": arn})["tags"]}


def test_list_tags_for_resource_lists_the_tags(endpoint):
    arn = ensure_collection(endpoint)["arn"]
    ok(endpoint, "TagResource", {"resourceArn": arn, "tags": [{"key": "team", "value": "platform"}]})
    assert {"key": "team", "value": "platform"} in ok(endpoint, "ListTagsForResource", {"resourceArn": arn})["tags"]
