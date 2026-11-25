"""Aurora DSQL on the wire: all 16 advertised operations, REST-JSON.

Signed with the `dsql` credential scope and routed on method + path. Without
`DSQL_STRICT` and Docker a cluster is metadata-only `ACTIVE`, so the tests need
no backend. A stream's CDC target is a real Kinesis stream, created here under
the `kinesis` scope, so the stream lands `ACTIVE` rather than `FAILED`.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
JSON_TYPE = {"Content-Type": "application/json"}
KINESIS_TARGET = "Kinesis_20131202."
KINESIS_STREAM = "ops-dsql-kinesis"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ops-dsql-stream-role"
POLICY = json.dumps({"Version": "2012-10-17", "Statement": []})

_STATE: dict = {}


def call(endpoint, method: str, path: str, payload: dict | None = None):
    body = json.dumps(payload or {})
    return signed.request(endpoint, "dsql", ACCOUNT, REGION, method, path, body, JSON_TYPE)


def ok(endpoint, method: str, path: str, payload: dict | None = None) -> dict:
    status, text = call(endpoint, method, path, payload)
    assert status == 200, f"{method} {path} answered {status}: {text[:500]}"
    return json.loads(text or "{}")


def ensure_cluster(endpoint) -> dict:
    if "cluster" not in _STATE:
        _STATE["cluster"] = ok(endpoint, "POST", "/cluster")
    return _STATE["cluster"]


def new_cluster(endpoint, **extra) -> dict:
    return ok(endpoint, "POST", "/cluster", extra)


def ensure_role(endpoint) -> None:
    trust = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "dsql.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
    )
    body = urlencode(
        {
            "Action": "CreateRole",
            "Version": "2010-05-08",
            "RoleName": ROLE_ARN.rsplit("/", 1)[-1],
            "AssumeRolePolicyDocument": trust,
        }
    )
    status, text = signed.request(
        endpoint,
        "iam",
        ACCOUNT,
        REGION,
        "POST",
        "/",
        body,
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert status == 200 or "EntityAlreadyExists" in text, f"CreateRole answered {status}: {text[:300]}"


def kinesis_target(endpoint) -> dict:
    ensure_role(endpoint)
    headers = {"X-Amz-Target": f"{KINESIS_TARGET}CreateStream", **JSON_TYPE}
    status, text = signed.request(
        endpoint,
        "kinesis",
        ACCOUNT,
        REGION,
        "POST",
        "/",
        json.dumps({"StreamName": KINESIS_STREAM, "ShardCount": 1}),
        headers,
    )
    assert status == 200 or "ResourceInUse" in text, f"CreateStream answered {status}: {text[:300]}"
    headers = {"X-Amz-Target": f"{KINESIS_TARGET}DescribeStream", **JSON_TYPE}
    status, text = signed.request(
        endpoint,
        "kinesis",
        ACCOUNT,
        REGION,
        "POST",
        "/",
        json.dumps({"StreamName": KINESIS_STREAM}),
        headers,
    )
    assert status == 200, f"DescribeStream answered {status}: {text[:300]}"
    arn = json.loads(text)["StreamDescription"]["StreamARN"]
    return {"kinesis": {"streamArn": arn, "roleArn": ROLE_ARN}}


def create_stream(endpoint, cluster_id: str) -> dict:
    return ok(
        endpoint,
        "POST",
        f"/stream/{cluster_id}",
        {
            "targetDefinition": kinesis_target(endpoint),
            "ordering": "UNORDERED",
            "format": "JSON",
        },
    )


def ensure_stream(endpoint) -> dict:
    cluster = ensure_cluster(endpoint)
    if "stream" not in _STATE:
        _STATE["stream"] = create_stream(endpoint, cluster["identifier"])
    return _STATE["stream"]


# --- Clusters ---------------------------------------------------------------


def test_create_cluster_answers_the_cluster(endpoint):
    cluster = ensure_cluster(endpoint)
    assert cluster["identifier"]
    assert cluster["arn"].endswith(f"cluster/{cluster['identifier']}")
    assert cluster["status"] in ("ACTIVE", "CREATING")


def test_get_cluster_reads_it(endpoint):
    cluster = ensure_cluster(endpoint)
    answer = ok(endpoint, "GET", f"/cluster/{cluster['identifier']}")
    assert answer["identifier"] == cluster["identifier"]
    assert answer["deletionProtectionEnabled"] is True


def test_update_cluster_sets_deletion_protection(endpoint):
    cluster = ensure_cluster(endpoint)
    answer = ok(
        endpoint,
        "POST",
        f"/cluster/{cluster['identifier']}",
        {"deletionProtectionEnabled": True},
    )
    assert answer["identifier"] == cluster["identifier"]
    assert answer["status"] in ("ACTIVE", "CREATING")


def test_list_clusters_lists_it(endpoint):
    cluster = ensure_cluster(endpoint)
    answer = ok(endpoint, "GET", "/cluster")
    assert cluster["identifier"] in {item["identifier"] for item in answer["clusters"]}


def test_delete_cluster_removes_it(endpoint):
    cluster = new_cluster(endpoint, deletionProtectionEnabled=False)
    ok(endpoint, "DELETE", f"/cluster/{cluster['identifier']}")
    status, _text = call(endpoint, "GET", f"/cluster/{cluster['identifier']}")
    assert status == 404


# --- Cluster policy ---------------------------------------------------------


def test_put_cluster_policy_answers_the_version(endpoint):
    cluster = ensure_cluster(endpoint)
    answer = ok(endpoint, "POST", f"/cluster/{cluster['identifier']}/policy", {"policy": POLICY})
    assert int(answer["policyVersion"]) >= 1


def test_get_cluster_policy_reads_it(endpoint):
    cluster = ensure_cluster(endpoint)
    status, _text = call(endpoint, "GET", f"/cluster/{cluster['identifier']}/policy")
    if status != 200:
        ok(endpoint, "POST", f"/cluster/{cluster['identifier']}/policy", {"policy": POLICY})
    answer = ok(endpoint, "GET", f"/cluster/{cluster['identifier']}/policy")
    assert answer["policy"] == POLICY


def test_delete_cluster_policy_removes_it(endpoint):
    cluster = ensure_cluster(endpoint)
    status, _text = call(endpoint, "GET", f"/cluster/{cluster['identifier']}/policy")
    if status != 200:
        ok(endpoint, "POST", f"/cluster/{cluster['identifier']}/policy", {"policy": POLICY})
    ok(endpoint, "DELETE", f"/cluster/{cluster['identifier']}/policy")
    status, _text = call(endpoint, "GET", f"/cluster/{cluster['identifier']}/policy")
    assert status == 404


# --- Streams ----------------------------------------------------------------


def test_create_stream_answers_the_stream(endpoint):
    stream = ensure_stream(endpoint)
    assert stream["streamIdentifier"]
    assert stream["status"] == "ACTIVE"
    assert stream["ordering"] == "UNORDERED"


def test_get_stream_reads_it(endpoint):
    stream = ensure_stream(endpoint)
    answer = ok(
        endpoint,
        "GET",
        f"/stream/{stream['clusterIdentifier']}/{stream['streamIdentifier']}",
    )
    assert answer["streamIdentifier"] == stream["streamIdentifier"]


def test_list_streams_lists_it(endpoint):
    stream = ensure_stream(endpoint)
    answer = ok(endpoint, "GET", f"/stream/{stream['clusterIdentifier']}")
    assert stream["streamIdentifier"] in {
        item["streamIdentifier"] for item in answer["streams"]
    }


def test_delete_stream_removes_it(endpoint):
    cluster = ensure_cluster(endpoint)
    stream = create_stream(endpoint, cluster["identifier"])
    ok(
        endpoint,
        "DELETE",
        f"/stream/{cluster['identifier']}/{stream['streamIdentifier']}",
    )
    status, _text = call(
        endpoint, "GET", f"/stream/{cluster['identifier']}/{stream['streamIdentifier']}"
    )
    assert status == 404


# --- VPC endpoint and tags --------------------------------------------------


def test_get_vpc_endpoint_service_name_answers_it(endpoint):
    cluster = ensure_cluster(endpoint)
    answer = ok(
        endpoint, "GET", f"/clusters/{cluster['identifier']}/vpc-endpoint-service-name"
    )
    assert answer["serviceName"].startswith(f"com.amazonaws.{REGION}.dsql-")


def test_tag_resource_adds_tags(endpoint):
    cluster = ensure_cluster(endpoint)
    ok(endpoint, "POST", f"/tags/{cluster['arn']}", {"tags": {"ops": "dsql"}})
    answer = ok(endpoint, "GET", f"/tags/{cluster['arn']}")
    assert answer["tags"]["ops"] == "dsql"


def test_list_tags_for_resource_reads_them(endpoint):
    cluster = ensure_cluster(endpoint)
    ok(endpoint, "POST", f"/tags/{cluster['arn']}", {"tags": {"ops": "dsql"}})
    answer = ok(endpoint, "GET", f"/tags/{cluster['arn']}")
    assert "ops" in answer["tags"]


def test_untag_resource_removes_tags(endpoint):
    cluster = ensure_cluster(endpoint)
    ok(endpoint, "POST", f"/tags/{cluster['arn']}", {"tags": {"ops-remove": "dsql"}})
    ok(endpoint, "DELETE", f"/tags/{cluster['arn']}?tagKeys=ops-remove")
    answer = ok(endpoint, "GET", f"/tags/{cluster['arn']}")
    assert "ops-remove" not in answer["tags"]
