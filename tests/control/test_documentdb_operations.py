"""Amazon DocumentDB on the wire: all 15 advertised operations, Query/XML signed as `rds`.

Clusters and instances are records; without Docker the shared container is
skipped and both settle `available`. Each call names its cluster, instance or
ARN, which is what the emulator's router claims a DocumentDB request by. Stable
names carry the read and modify tests, and every delete test creates a resource
of its own.
"""

from __future__ import annotations

import os
import re
import secrets
from urllib.parse import urlencode

import pytest

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
VERSION = "2014-10-31"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
RUN = secrets.token_hex(3)

CLUSTER = "ops-docdb-cluster"
INSTANCE = "ops-docdb-instance"
READER = "ops-docdb-reader"
LIFECYCLE = "ops-docdb-lifecycle"

MASTER_USER = "docadmin"
MASTER_PASSWORD = "password"


def call(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, "rds", ACCOUNT, REGION, "POST", "/", body, FORM)


def ok(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:500]}"
    return text


def created(endpoint, action: str, **params) -> str:
    """A create is idempotent across sweeps: an existing record is not a failure."""
    status, text = call(endpoint, action, **params)
    assert status == 200 or "AlreadyExist" in text, f"{action} answered {status}: {text[:500]}"
    return text


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:500]}"
    return match.group(1)


def present(text: str, tag: str) -> bool:
    return f"<{tag}>" in text


# --- Clusters ---------------------------------------------------------------


def create_cluster(endpoint, name: str = CLUSTER, **extra) -> str:
    return created(
        endpoint,
        "CreateDBCluster",
        DBClusterIdentifier=name,
        Engine="docdb",
        MasterUsername=MASTER_USER,
        MasterUserPassword=MASTER_PASSWORD,
        **extra,
    )


def describe_cluster(endpoint, name: str = CLUSTER) -> str:
    return ok(endpoint, "DescribeDBClusters", DBClusterIdentifier=name)


def cluster_status(endpoint, name: str = CLUSTER) -> str:
    return field(describe_cluster(endpoint, name), "Status")


@pytest.fixture(scope="module", autouse=True)
def stop_the_clusters_after_the_run(endpoint):
    """Stop (never delete) the clusters so their containers do not outlive the sweep."""
    yield
    if not os.environ.get("EP_LAB_EMULATOR"):
        return
    for name in (CLUSTER, LIFECYCLE):
        status, text = call(endpoint, "StopDBCluster", DBClusterIdentifier=name)
        if status != 200 and "not found" not in text.lower():
            print(f"could not stop {name}: {status} {text[:200]}")


def ensure_cluster(endpoint, name: str = CLUSTER) -> str:
    create_cluster(endpoint, name)
    return describe_cluster(endpoint, name)


def cluster_members(endpoint, name: str = CLUSTER) -> list[dict]:
    answer = describe_cluster(endpoint, name)
    return [
        {
            "name": field(block, "DBInstanceIdentifier"),
            "writer": field(block, "IsClusterWriter") == "true",
        }
        for block in re.findall(r"<DBClusterMember>(.*?)</DBClusterMember>", answer, re.S)
    ]


# --- Instances --------------------------------------------------------------


def create_instance(endpoint, name: str, cluster: str | None = CLUSTER) -> str:
    params = {
        "DBInstanceIdentifier": name,
        "Engine": "docdb",
        "DBInstanceClass": "db.t3.medium",
    }
    if cluster:
        params["DBClusterIdentifier"] = cluster
    return created(endpoint, "CreateDBInstance", **params)


def describe_instance(endpoint, name: str = INSTANCE) -> str:
    return ok(endpoint, "DescribeDBInstances", DBInstanceIdentifier=name)


def instance_arn(endpoint, name: str = INSTANCE) -> str:
    return field(describe_instance(endpoint, name), "DBInstanceArn")


def ensure_instance(endpoint, name: str = INSTANCE, cluster: str | None = CLUSTER) -> str:
    if cluster:
        ensure_cluster(endpoint, cluster)
    create_instance(endpoint, name, cluster)
    return describe_instance(endpoint, name)


# --- Clusters and instances -------------------------------------------------


def test_create_db_cluster_is_read_back(endpoint):
    answer = ensure_cluster(endpoint)
    assert field(answer, "DBClusterIdentifier") == CLUSTER
    assert field(answer, "Engine") == "docdb"
    assert field(answer, "Status") == "available"


def test_create_db_instance_joins_the_cluster(endpoint):
    answer = ensure_instance(endpoint)
    assert field(answer, "DBInstanceIdentifier") == INSTANCE
    assert field(answer, "Engine") == "docdb"
    assert field(answer, "DBClusterIdentifier") == CLUSTER
    assert field(answer, "DBInstanceStatus") in ("available", "creating")


def test_describe_db_clusters_reports_the_engine(endpoint):
    ensure_cluster(endpoint)
    answer = describe_cluster(endpoint)
    assert field(answer, "EngineVersion") == "8.0.0"
    assert field(answer, "DBClusterParameterGroup") == "default.docdb8.0"
    assert field(answer, "Port") == "27017"


def test_describe_db_instances_reports_its_cluster(endpoint):
    ensure_instance(endpoint)
    answer = describe_instance(endpoint)
    assert field(answer, "DBClusterIdentifier") == CLUSTER
    assert field(answer, "DBInstanceClass") == "db.t3.medium"
    assert present(answer, "Endpoint")


def test_modify_db_cluster_sets_backup_retention(endpoint):
    ensure_cluster(endpoint)
    answer = ok(endpoint, "ModifyDBCluster", DBClusterIdentifier=CLUSTER, BackupRetentionPeriod="7")
    assert field(answer, "BackupRetentionPeriod") == "7"


def test_modify_db_instance_applies_the_class(endpoint):
    ensure_instance(endpoint)
    ok(endpoint, "ModifyDBInstance", DBInstanceIdentifier=INSTANCE, DBInstanceClass="db.t3.small")
    assert field(describe_instance(endpoint), "DBInstanceClass") == "db.t3.small"
    ok(endpoint, "ModifyDBInstance", DBInstanceIdentifier=INSTANCE, DBInstanceClass="db.t3.medium")


def test_reboot_db_instance_returns_it_available(endpoint):
    ensure_instance(endpoint)
    answer = ok(endpoint, "RebootDBInstance", DBInstanceIdentifier=INSTANCE)
    assert field(answer, "DBInstanceIdentifier") == INSTANCE
    assert field(answer, "DBInstanceStatus") == "available"


def test_start_db_cluster_starts_it(endpoint):
    ensure_cluster(endpoint, LIFECYCLE)
    if cluster_status(endpoint, LIFECYCLE) != "stopped":
        ok(endpoint, "StopDBCluster", DBClusterIdentifier=LIFECYCLE)
    answer = ok(endpoint, "StartDBCluster", DBClusterIdentifier=LIFECYCLE)
    assert field(answer, "Status") in ("available", "starting")


def test_stop_db_cluster_stops_it(endpoint):
    ensure_cluster(endpoint, LIFECYCLE)
    if cluster_status(endpoint, LIFECYCLE) == "stopped":
        ok(endpoint, "StartDBCluster", DBClusterIdentifier=LIFECYCLE)
    answer = ok(endpoint, "StopDBCluster", DBClusterIdentifier=LIFECYCLE)
    assert field(answer, "Status") == "stopped"


def test_failover_db_cluster_promotes_a_reader(endpoint):
    ensure_instance(endpoint)
    ensure_instance(endpoint, READER)
    reader = next(member for member in cluster_members(endpoint) if not member["writer"])
    answer = ok(
        endpoint,
        "FailoverDBCluster",
        DBClusterIdentifier=CLUSTER,
        TargetDBInstanceIdentifier=reader["name"],
    )
    assert field(answer, "Status") == "failing-over"
    promoted = next(member for member in cluster_members(endpoint) if member["name"] == reader["name"])
    assert promoted["writer"]


def test_delete_db_cluster_removes_it(endpoint):
    name = f"ops-docdb-delete-cluster-{RUN}"
    create_cluster(endpoint, name)
    ok(endpoint, "DeleteDBCluster", DBClusterIdentifier=name)
    status, _text = call(endpoint, "DescribeDBClusters", DBClusterIdentifier=name)
    assert status == 404


def test_delete_db_instance_removes_it(endpoint):
    name = f"ops-docdb-delete-instance-{RUN}"
    ensure_instance(endpoint, name, cluster=None)
    ok(endpoint, "DeleteDBInstance", DBInstanceIdentifier=name)
    status, _text = call(endpoint, "DescribeDBInstances", DBInstanceIdentifier=name)
    assert status == 404


# --- Tags -------------------------------------------------------------------


def test_add_tags_to_resource_adds_them(endpoint):
    ensure_instance(endpoint)
    arn = instance_arn(endpoint)
    ok(
        endpoint,
        "AddTagsToResource",
        ResourceName=arn,
        **{"Tags.member.1.Key": "ops", "Tags.member.1.Value": "docdb"},
    )
    answer = ok(endpoint, "ListTagsForResource", ResourceName=arn)
    assert "<Key>ops</Key>" in answer


def test_remove_tags_from_resource_removes_them(endpoint):
    ensure_instance(endpoint)
    arn = instance_arn(endpoint)
    ok(
        endpoint,
        "AddTagsToResource",
        ResourceName=arn,
        **{"Tags.member.1.Key": "ops-remove", "Tags.member.1.Value": "docdb"},
    )
    ok(
        endpoint,
        "RemoveTagsFromResource",
        ResourceName=arn,
        **{"TagKeys.member.1": "ops-remove"},
    )
    answer = ok(endpoint, "ListTagsForResource", ResourceName=arn)
    assert "<Key>ops-remove</Key>" not in answer


def test_list_tags_for_resource_reads_them(endpoint):
    ensure_instance(endpoint)
    arn = instance_arn(endpoint)
    ok(
        endpoint,
        "AddTagsToResource",
        ResourceName=arn,
        **{"Tags.member.1.Key": "ops-list", "Tags.member.1.Value": "docdb"},
    )
    answer = ok(endpoint, "ListTagsForResource", ResourceName=arn)
    assert present(answer, "TagList")
    assert "<Key>ops-list</Key>" in answer
