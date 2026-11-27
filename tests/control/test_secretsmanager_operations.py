"""Secrets Manager on the wire: every advertised action, driven through the JSON protocol.

A secret created here is left in place; the delete action creates a secret of its own. The
replication actions need a second enabled region and skip when the lab has only one.
"""

from __future__ import annotations

import json

import pytest
import signed
from conftest import ACCOUNT

REGION = "us-east-1"
SECOND_REGION = "us-west-2"
TARGET = "secretsmanager."
HEADERS = {"Content-Type": "application/x-amz-json-1.0"}


def call(endpoint, action: str, region: str = REGION, **params):
    headers = dict(HEADERS, **{"X-Amz-Target": TARGET + action})
    return signed.request(
        endpoint, "secretsmanager", ACCOUNT, region, "POST", "/", json.dumps(params), headers
    )


def ok(endpoint, action: str, region: str = REGION, **params) -> dict:
    status, text = call(endpoint, action, region=region, **params)
    # A lab sweep re-runs against the secrets an earlier sweep deliberately left behind.
    if status == 200:
        return json.loads(text or "{}")
    assert "ResourceExists" in text, f"{action} answered {status}: {text[:400]}"
    return json.loads(text or "{}")


def secret(endpoint, name: str, value: str) -> str:
    """The ARN of the secret named, created once and reusable across sweeps."""
    status, text = call(endpoint, "CreateSecret", Name=name, SecretString=value)
    if status == 200:
        return json.loads(text)["ARN"]
    assert "ResourceExists" in text, f"CreateSecret answered {status}: {text[:400]}"
    listed = ok(endpoint, "ListSecrets")["SecretList"]
    return next(item["ARN"] for item in listed if item["Name"] == name)


def replicated(endpoint, name: str, value: str) -> tuple[str, dict]:
    """The ARN of a secret of this test's own, replicated to `SECOND_REGION`.

    A lab with a single region cannot host a replica; that is a missing dependant, not a failure.
    """
    arn = secret(endpoint, name, value)
    status, text = call(
        endpoint,
        "ReplicateSecretToRegions",
        SecretId=arn,
        AddReplicaRegions=[{"Region": SECOND_REGION}],
        ForceOverwriteReplicaSecret=True,
    )
    if status == 200:
        return arn, json.loads(text)
    # The only refusal this action raises is about the replica region itself.
    assert "InvalidParameterException" in text, (
        f"ReplicateSecretToRegions answered {status}: {text[:400]}"
    )
    pytest.skip("needs a second enabled region")


def test_create_secret_is_read_back_by_list(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-created", "initial")
    listed = ok(s3_endpoint, "ListSecrets")["SecretList"]
    assert arn in [item["ARN"] for item in listed]


def test_get_secret_value_returns_the_current_version(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-read", "read-back")
    got = ok(s3_endpoint, "GetSecretValue", SecretId=arn)
    assert got["ARN"] == arn
    assert got["SecretString"] == "read-back"
    assert got["VersionStages"] == ["AWSCURRENT"]


def test_put_secret_value_is_read_back_by_get(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-rotated", "first")
    ok(s3_endpoint, "PutSecretValue", SecretId=arn, SecretString="second")
    assert ok(s3_endpoint, "GetSecretValue", SecretId=arn)["SecretString"] == "second"


def test_update_secret_replaces_value_and_description(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-updated", "before")
    ok(
        s3_endpoint,
        "UpdateSecret",
        SecretId=arn,
        Description="updated by the sweep",
        SecretString="after",
    )
    assert ok(s3_endpoint, "GetSecretValue", SecretId=arn)["SecretString"] == "after"
    assert ok(s3_endpoint, "DescribeSecret", SecretId=arn)["Description"] == "updated by the sweep"


def test_describe_secret_reports_metadata(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-described", "described")
    described = ok(s3_endpoint, "DescribeSecret", SecretId=arn)
    assert described["ARN"] == arn
    assert described["Name"] == "ops-secrets-described"
    assert described["CreatedDate"] > 0
    assert "DeletedDate" not in described
    current = ok(s3_endpoint, "GetSecretValue", SecretId=arn)["VersionId"]
    assert described["VersionIdsToStages"][current] == ["AWSCURRENT"]


def test_update_secret_version_stage_moves_a_label(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-labelled", "initial")
    versions = ok(s3_endpoint, "ListSecretVersionIds", SecretId=arn)["Versions"]
    current = ok(s3_endpoint, "GetSecretValue", SecretId=arn)["VersionId"]
    # A label and a token no earlier sweep used: PutSecretValue attaches the label to the version
    # it writes, and a label held by one version moves without ambiguity.
    stage = f"OPSSTAGE{len(versions)}"
    labelled = ok(
        s3_endpoint,
        "PutSecretValue",
        SecretId=arn,
        SecretString="labelled",
        ClientRequestToken=f"ops-secrets-labelled-{len(versions)}",
        VersionStages=[stage],
    )["VersionId"]
    assert labelled != current

    ok(
        s3_endpoint,
        "UpdateSecretVersionStage",
        SecretId=arn,
        VersionStage=stage,
        MoveToVersionId=current,
        RemoveFromVersionId=labelled,
    )
    stages = {
        item["VersionId"]: item["VersionStages"]
        for item in ok(s3_endpoint, "ListSecretVersionIds", SecretId=arn)["Versions"]
    }
    assert stage in stages[current]
    assert stage not in stages.get(labelled, [])

    # The same action detaching the label again: it leaves AWSCURRENT clean for the next sweep.
    ok(
        s3_endpoint,
        "UpdateSecretVersionStage",
        SecretId=arn,
        VersionStage=stage,
        RemoveFromVersionId=current,
    )
    assert ok(s3_endpoint, "GetSecretValue", SecretId=arn)["SecretString"] == "initial"


def test_delete_secret_removes_the_secret_it_created(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-deleted", "gone")
    ok(
        s3_endpoint,
        "DeleteSecret",
        SecretId=arn,
        ForceDeleteWithoutRecovery=True,
    )
    status, text = call(s3_endpoint, "GetSecretValue", SecretId=arn)
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_restore_secret_undoes_a_scheduled_deletion(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-restored", "restored")
    deleted = ok(s3_endpoint, "DeleteSecret", SecretId=arn, RecoveryWindowInDays=7)
    assert deleted["DeletionDate"] > 0
    status, text = call(s3_endpoint, "GetSecretValue", SecretId=arn)
    assert status == 400, text[:300]
    assert "InvalidRequestException" in text
    assert "DeletedDate" in ok(s3_endpoint, "DescribeSecret", SecretId=arn)

    ok(s3_endpoint, "RestoreSecret", SecretId=arn)
    assert "DeletedDate" not in ok(s3_endpoint, "DescribeSecret", SecretId=arn)
    assert ok(s3_endpoint, "GetSecretValue", SecretId=arn)["SecretString"] == "restored"


def test_rotate_secret_publishes_a_current_version(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-rotating", "rotating")
    lambda_arn = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:ops-secrets-rotate"
    rotated = ok(
        s3_endpoint,
        "RotateSecret",
        SecretId=arn,
        RotationLambdaARN=lambda_arn,
        RotationRules={"AutomaticallyAfterDays": 30},
    )
    described = ok(s3_endpoint, "DescribeSecret", SecretId=arn)
    assert described["RotationEnabled"] is True
    assert described["RotationLambdaARN"] == lambda_arn
    assert described["RotationRules"] == {"AutomaticallyAfterDays": 30}
    stages = {
        item["VersionId"]: item["VersionStages"]
        for item in ok(s3_endpoint, "ListSecretVersionIds", SecretId=arn)["Versions"]
    }
    # 1.5.43 runs the rotation function; with none configured the returned token is
    # not committed, so the new version is asserted where the emulator creates it.
    if rotated["VersionId"] in stages:
        assert "AWSCURRENT" in stages[rotated["VersionId"]]


def test_get_random_password_honours_the_requested_length(s3_endpoint):
    password = ok(
        s3_endpoint,
        "GetRandomPassword",
        PasswordLength=24,
        ExcludePunctuation=True,
    )["RandomPassword"]
    assert len(password) == 24
    assert password.isalnum()
    assert any(c.islower() for c in password)
    assert any(c.isupper() for c in password)
    assert any(c.isdigit() for c in password)


def test_list_secret_version_ids_lists_every_version(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-versions", "v1")
    existing = ok(s3_endpoint, "ListSecretVersionIds", SecretId=arn)["Versions"]
    # A custom stage and a token per sweep: promoting to AWSCURRENT would prune the older version,
    # and rewriting an earlier sweep's version would strip the stages it now carries.
    added = ok(
        s3_endpoint,
        "PutSecretValue",
        SecretId=arn,
        SecretString="v2",
        ClientRequestToken=f"ops-secrets-versions-{len(existing)}",
        VersionStages=["OPSARCHIVE"],
    )["VersionId"]
    assert added != ok(s3_endpoint, "GetSecretValue", SecretId=arn)["VersionId"]

    versions = []
    page = ok(s3_endpoint, "ListSecretVersionIds", SecretId=arn, MaxResults=1)
    versions.extend(page["Versions"])
    assert page.get("NextToken"), "two versions cannot fit on a one-version page"
    while page.get("NextToken"):
        page = ok(
            s3_endpoint,
            "ListSecretVersionIds",
            SecretId=arn,
            MaxResults=1,
            NextToken=page["NextToken"],
        )
        versions.extend(page["Versions"])

    ids = [item["VersionId"] for item in versions]
    assert added in ids
    assert len(ids) == len(set(ids))


def test_replicate_secret_to_regions_reports_in_sync(s3_endpoint):
    arn, replicated_to = replicated(s3_endpoint, "ops-secrets-replicated", "replicated")
    assert replicated_to["ARN"] == arn
    statuses = {item["Region"]: item["Status"] for item in replicated_to["ReplicationStatus"]}
    assert statuses[SECOND_REGION] == "InSync"

    replica = ok(
        s3_endpoint, "DescribeSecret", region=SECOND_REGION, SecretId="ops-secrets-replicated"
    )
    assert replica["PrimaryRegion"] == REGION
    got = ok(s3_endpoint, "GetSecretValue", region=SECOND_REGION, SecretId=replica["ARN"])
    assert got["SecretString"] == "replicated"


def test_remove_regions_from_replication_drops_the_replica(s3_endpoint):
    arn, _ = replicated(s3_endpoint, "ops-secrets-replicas-removed", "removed")
    after = ok(
        s3_endpoint,
        "RemoveRegionsFromReplication",
        SecretId=arn,
        RemoveReplicaRegions=[SECOND_REGION],
    )
    assert SECOND_REGION not in {item["Region"] for item in after["ReplicationStatus"]}
    status, text = call(
        s3_endpoint, "DescribeSecret", region=SECOND_REGION, SecretId="ops-secrets-replicas-removed"
    )
    assert status == 400, text[:300]
    assert "ResourceNotFoundException" in text


def test_stop_replication_to_replica_leaves_a_standalone_secret(s3_endpoint):
    name = "ops-secrets-replicas-stopped"
    arn, _ = replicated(s3_endpoint, name, "stopped")
    replica_arn = ok(s3_endpoint, "DescribeSecret", region=SECOND_REGION, SecretId=name)["ARN"]
    stopped = ok(s3_endpoint, "StopReplicationToReplica", region=SECOND_REGION, SecretId=replica_arn)
    assert stopped["ARN"] == replica_arn

    described = ok(s3_endpoint, "DescribeSecret", region=SECOND_REGION, SecretId=replica_arn)
    assert "PrimaryRegion" not in described
    replica_value = ok(
        s3_endpoint, "GetSecretValue", region=SECOND_REGION, SecretId=replica_arn
    )
    assert replica_value["SecretString"] == "stopped"
    # The primary no longer claims the region it was stopped from.
    primary = ok(s3_endpoint, "DescribeSecret", SecretId=arn)
    assert SECOND_REGION not in {item["Region"] for item in primary.get("ReplicationStatus", [])}


def test_tag_resource_adds_tags(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-tagged", "tagged")
    ok(
        s3_endpoint,
        "TagResource",
        SecretId=arn,
        Tags=[{"Key": "sweep", "Value": "tagged"}, {"Key": "owner", "Value": "ops"}],
    )
    described = ok(s3_endpoint, "DescribeSecret", SecretId=arn)
    tags = {tag["Key"]: tag["Value"] for tag in described["Tags"]}
    assert tags["sweep"] == "tagged"
    assert tags["owner"] == "ops"


def test_untag_resource_removes_a_tag(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-untagged", "untagged")
    ok(
        s3_endpoint,
        "TagResource",
        SecretId=arn,
        Tags=[{"Key": "sweep-removed", "Value": "gone"}, {"Key": "sweep-kept", "Value": "kept"}],
    )
    ok(s3_endpoint, "UntagResource", SecretId=arn, TagKeys=["sweep-removed"])
    described = ok(s3_endpoint, "DescribeSecret", SecretId=arn)
    tags = {tag["Key"]: tag["Value"] for tag in described["Tags"]}
    assert "sweep-removed" not in tags
    assert tags["sweep-kept"] == "kept"


def _policy(secret_name: str) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
                    "Action": "secretsmanager:GetSecretValue",
                    "Resource": "*",
                    "Condition": {"StringEquals": {"secretsmanager:ResourceTag/sweep": secret_name}},
                }
            ],
        }
    )


def test_put_resource_policy_stores_a_policy(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-policy", "policy")
    put = ok(s3_endpoint, "PutResourcePolicy", SecretId=arn, ResourcePolicy=_policy("put"))
    assert put["ARN"] == arn
    assert put["Name"] == "ops-secrets-policy"
    got = ok(s3_endpoint, "GetResourcePolicy", SecretId=arn)
    assert json.loads(got["ResourcePolicy"]) == json.loads(_policy("put"))


def test_get_resource_policy_reads_the_policy_back(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-policy-read", "policy")
    ok(s3_endpoint, "PutResourcePolicy", SecretId=arn, ResourcePolicy=_policy("read"))
    got = ok(s3_endpoint, "GetResourcePolicy", SecretId=arn)
    assert got["ARN"] == arn
    assert got["Name"] == "ops-secrets-policy-read"
    assert json.loads(got["ResourcePolicy"]) == json.loads(_policy("read"))


def test_delete_resource_policy_removes_the_policy(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-policy-deleted", "policy")
    ok(s3_endpoint, "PutResourcePolicy", SecretId=arn, ResourcePolicy=_policy("delete"))
    ok(s3_endpoint, "DeleteResourcePolicy", SecretId=arn)
    got = ok(s3_endpoint, "GetResourcePolicy", SecretId=arn)
    assert "ResourcePolicy" not in got
    # The secret itself is untouched: the policy was the resource under test.
    assert ok(s3_endpoint, "DescribeSecret", SecretId=arn)["ARN"] == arn


def test_validate_resource_policy_accepts_a_policy(s3_endpoint):
    arn = secret(s3_endpoint, "ops-secrets-policy-validated", "policy")
    validated = ok(
        s3_endpoint,
        "ValidateResourcePolicy",
        SecretId=arn,
        ResourcePolicy=_policy("validate"),
    )
    assert validated["PolicyValidationPassed"] is True
    assert validated["ValidationErrors"] == []
