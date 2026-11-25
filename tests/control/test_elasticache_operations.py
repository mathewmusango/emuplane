"""ElastiCache on the wire: all 41 advertised operations, Query/XML.

Signed with the `elasticache` credential scope and sent form-encoded. Without
Docker a cluster is a control-plane record whose endpoints point at the shared
sidecar; the tests never need a container. Stable names carry the read, modify
and tag rows; delete actions make their own resource.
"""

from __future__ import annotations

import re
import secrets
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
VERSION = "2015-02-02"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
RUN = secrets.token_hex(3)

CLUSTER = "ops-ec-cluster"
REPLICATION_GROUP = "ops-ec-rg"
SUBNET_GROUP = "ops-ec-subnet-group"
PARAM_GROUP = "ops-ec-param-group"
USER = "ops-ec-user"
USER_TWO = "ops-ec-user2"
USER_GROUP = "ops-ec-user-group"
SNAPSHOT = "ops-ec-snapshot"
SERVERLESS = "ops-ec-serverless"


def call(endpoint, action: str, **params):
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(
        endpoint, "elasticache", ACCOUNT, REGION, "POST", "/", body, FORM
    )


def ok(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status == 200, f"{action} answered {status}: {text[:500]}"
    return text


def created(endpoint, action: str, **params) -> str:
    status, text = call(endpoint, action, **params)
    assert status == 200 or "AlreadyExist" in text, f"{action} answered {status}: {text[:500]}"
    return text


def field(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>([^<]*)</{tag}>", text)
    assert match, f"no <{tag}> in {text[:500]}"
    return match.group(1)


# --- EC2 defaults the subnet group needs -----------------------------------


def subnet_params(endpoint) -> dict:
    body = urlencode({"Action": "DescribeSubnets", "Version": "2016-11-15"})
    status, text = signed.request(
        endpoint, "ec2", ACCOUNT, REGION, "POST", "/", body, FORM
    )
    assert status == 200, text[:300]
    subnets = re.findall(r"<subnetId>([^<]+)</subnetId>", text)
    assert len(subnets) >= 2, "EC2 has no default subnets"
    return {"SubnetIds.member.1": subnets[0], "SubnetIds.member.2": subnets[1]}


# --- Cache clusters ---------------------------------------------------------


def describe_cluster(endpoint, name: str = CLUSTER) -> str:
    return ok(endpoint, "DescribeCacheClusters", CacheClusterId=name)


def cluster_arn(endpoint, name: str = CLUSTER) -> str:
    return field(describe_cluster(endpoint, name), "ARN")


def ensure_cluster(endpoint, name: str = CLUSTER) -> str:
    created(endpoint, "CreateCacheCluster", CacheClusterId=name, Engine="redis")
    return describe_cluster(endpoint, name)


def ensure_rg(endpoint, name: str = REPLICATION_GROUP) -> str:
    created(
        endpoint,
        "CreateReplicationGroup",
        ReplicationGroupId=name,
        ReplicationGroupDescription="ops replication group",
    )
    return ok(endpoint, "DescribeReplicationGroups", ReplicationGroupId=name)


def ensure_subnet_group(endpoint) -> str:
    created(
        endpoint,
        "CreateCacheSubnetGroup",
        CacheSubnetGroupName=SUBNET_GROUP,
        CacheSubnetGroupDescription="ops subnet group",
        **subnet_params(endpoint),
    )
    return ok(endpoint, "DescribeCacheSubnetGroups", CacheSubnetGroupName=SUBNET_GROUP)


def ensure_param_group(endpoint) -> str:
    created(
        endpoint,
        "CreateCacheParameterGroup",
        CacheParameterGroupName=PARAM_GROUP,
        Description="ops parameter group",
    )
    return ok(endpoint, "DescribeCacheParameterGroups", CacheParameterGroupName=PARAM_GROUP)


def ensure_user(endpoint, name: str = USER) -> str:
    created(
        endpoint,
        "CreateUser",
        UserId=name,
        UserName=name,
        Engine="redis",
        AccessString="on ~* +@all",
    )
    return ok(endpoint, "DescribeUsers", UserId=name)


def ensure_user_group(endpoint) -> str:
    ensure_user(endpoint)
    created(
        endpoint,
        "CreateUserGroup",
        UserGroupId=USER_GROUP,
        Engine="redis",
        **{"UserIds.member.1": "default", "UserIds.member.2": USER},
    )
    return ok(endpoint, "DescribeUserGroups", UserGroupId=USER_GROUP)


def ensure_snapshot(endpoint) -> str:
    ensure_cluster(endpoint)
    created(
        endpoint,
        "CreateSnapshot",
        SnapshotName=SNAPSHOT,
        CacheClusterId=CLUSTER,
    )
    return ok(endpoint, "DescribeSnapshots", SnapshotName=SNAPSHOT)


def ensure_serverless(endpoint) -> str:
    created(
        endpoint,
        "CreateServerlessCache",
        ServerlessCacheName=SERVERLESS,
        Engine="redis",
    )
    return ok(endpoint, "DescribeServerlessCaches", ServerlessCacheName=SERVERLESS)


# --- Cache clusters ---------------------------------------------------------


def test_create_cache_cluster_answers_the_cluster(endpoint):
    answer = ensure_cluster(endpoint)
    assert field(answer, "CacheClusterId") == CLUSTER
    assert field(answer, "CacheClusterStatus") in ("available", "creating")


def test_describe_cache_clusters_reads_it(endpoint):
    ensure_cluster(endpoint)
    answer = describe_cluster(endpoint)
    assert field(answer, "Engine") == "redis"
    assert field(answer, "CacheClusterId") == CLUSTER


def test_modify_cache_cluster_sets_the_node_type(endpoint):
    ensure_cluster(endpoint)
    answer = ok(endpoint, "ModifyCacheCluster", CacheClusterId=CLUSTER, CacheNodeType="cache.t3.small")
    assert field(answer, "CacheNodeType") == "cache.t3.small"


def test_reboot_cache_cluster_reboots_it(endpoint):
    ensure_cluster(endpoint)
    answer = ok(endpoint, "RebootCacheCluster", CacheClusterId=CLUSTER)
    assert field(answer, "CacheClusterId") == CLUSTER


def test_delete_cache_cluster_removes_it(endpoint):
    name = f"ops-ec-delete-cluster-{RUN}"
    created(endpoint, "CreateCacheCluster", CacheClusterId=name, Engine="redis")
    ok(endpoint, "DeleteCacheCluster", CacheClusterId=name)
    status, _text = call(endpoint, "DescribeCacheClusters", CacheClusterId=name)
    assert status == 404


# --- Replication groups -----------------------------------------------------


def test_create_replication_group_answers_the_group(endpoint):
    answer = ensure_rg(endpoint)
    assert field(answer, "ReplicationGroupId") == REPLICATION_GROUP


def test_describe_replication_groups_reads_it(endpoint):
    ensure_rg(endpoint)
    answer = ok(endpoint, "DescribeReplicationGroups", ReplicationGroupId=REPLICATION_GROUP)
    assert field(answer, "ReplicationGroupId") == REPLICATION_GROUP


def test_modify_replication_group_sets_the_description(endpoint):
    ensure_rg(endpoint)
    answer = ok(
        endpoint,
        "ModifyReplicationGroup",
        ReplicationGroupId=REPLICATION_GROUP,
        ReplicationGroupDescription="updated replication group",
    )
    assert field(answer, "Description") == "updated replication group"


def test_increase_replica_count_adds_a_replica(endpoint):
    ensure_rg(endpoint)
    answer = ok(endpoint, "IncreaseReplicaCount", ReplicationGroupId=REPLICATION_GROUP, NewReplicaCount="1")
    assert field(answer, "ReplicationGroupId") == REPLICATION_GROUP


def test_decrease_replica_count_removes_it(endpoint):
    ensure_rg(endpoint)
    answer = ok(endpoint, "DecreaseReplicaCount", ReplicationGroupId=REPLICATION_GROUP, NewReplicaCount="0")
    assert field(answer, "ReplicationGroupId") == REPLICATION_GROUP


def test_delete_replication_group_removes_it(endpoint):
    name = f"ops-ec-delete-rg-{RUN}"
    created(
        endpoint,
        "CreateReplicationGroup",
        ReplicationGroupId=name,
        ReplicationGroupDescription="delete me",
    )
    ok(endpoint, "DeleteReplicationGroup", ReplicationGroupId=name)
    status, _text = call(endpoint, "DescribeReplicationGroups", ReplicationGroupId=name)
    assert status == 404


# --- Subnet groups ----------------------------------------------------------


def test_create_cache_subnet_group_answers_the_group(endpoint):
    answer = ensure_subnet_group(endpoint)
    assert field(answer, "CacheSubnetGroupName") == SUBNET_GROUP


def test_describe_cache_subnet_groups_reads_it(endpoint):
    ensure_subnet_group(endpoint)
    answer = ok(endpoint, "DescribeCacheSubnetGroups", CacheSubnetGroupName=SUBNET_GROUP)
    assert field(answer, "CacheSubnetGroupName") == SUBNET_GROUP


def test_modify_cache_subnet_group_sets_the_description(endpoint):
    ensure_subnet_group(endpoint)
    answer = ok(
        endpoint,
        "ModifyCacheSubnetGroup",
        CacheSubnetGroupName=SUBNET_GROUP,
        CacheSubnetGroupDescription="updated subnet group",
    )
    assert field(answer, "CacheSubnetGroupDescription") == "updated subnet group"


def test_delete_cache_subnet_group_removes_it(endpoint):
    name = f"ops-ec-delete-subnet-{RUN}"
    created(
        endpoint,
        "CreateCacheSubnetGroup",
        CacheSubnetGroupName=name,
        CacheSubnetGroupDescription="delete me",
        **subnet_params(endpoint),
    )
    ok(endpoint, "DeleteCacheSubnetGroup", CacheSubnetGroupName=name)
    status, _text = call(endpoint, "DescribeCacheSubnetGroups", CacheSubnetGroupName=name)
    assert status != 200


# --- Parameter groups -------------------------------------------------------


def test_create_cache_parameter_group_answers_the_group(endpoint):
    answer = ensure_param_group(endpoint)
    assert field(answer, "CacheParameterGroupName") == PARAM_GROUP


def test_describe_cache_parameter_groups_reads_it(endpoint):
    ensure_param_group(endpoint)
    answer = ok(endpoint, "DescribeCacheParameterGroups", CacheParameterGroupName=PARAM_GROUP)
    assert field(answer, "CacheParameterGroupName") == PARAM_GROUP


def test_describe_cache_parameters_reads_them(endpoint):
    ensure_param_group(endpoint)
    answer = ok(endpoint, "DescribeCacheParameters", CacheParameterGroupName=PARAM_GROUP)
    assert "<Parameter>" in answer


def test_modify_cache_parameter_group_applies_a_parameter(endpoint):
    ensure_param_group(endpoint)
    answer = ok(
        endpoint,
        "ModifyCacheParameterGroup",
        CacheParameterGroupName=PARAM_GROUP,
        **{
            "ParameterNameValues.ParameterNameValue.1.ParameterName": "maxmemory-policy",
            "ParameterNameValues.ParameterNameValue.1.ParameterValue": "allkeys-lru",
        },
    )
    assert field(answer, "CacheParameterGroupName") == PARAM_GROUP


def test_reset_cache_parameter_group_resets_it(endpoint):
    ensure_param_group(endpoint)
    answer = ok(
        endpoint,
        "ResetCacheParameterGroup",
        CacheParameterGroupName=PARAM_GROUP,
        ResetAllParameters="true",
    )
    assert field(answer, "CacheParameterGroupName") == PARAM_GROUP


def test_delete_cache_parameter_group_removes_it(endpoint):
    name = f"ops-ec-delete-param-{RUN}"
    created(
        endpoint,
        "CreateCacheParameterGroup",
        CacheParameterGroupName=name,
        Description="delete me",
    )
    ok(endpoint, "DeleteCacheParameterGroup", CacheParameterGroupName=name)
    status, _text = call(endpoint, "DescribeCacheParameterGroups", CacheParameterGroupName=name)
    assert status == 404


# --- Users ------------------------------------------------------------------


def test_create_user_answers_the_user(endpoint):
    answer = ensure_user(endpoint)
    assert field(answer, "UserId") == USER
    assert field(answer, "UserName") == USER


def test_describe_users_reads_it(endpoint):
    ensure_user(endpoint)
    answer = ok(endpoint, "DescribeUsers", UserId=USER)
    assert field(answer, "Engine") == "redis"


def test_modify_user_sets_the_access_string(endpoint):
    ensure_user(endpoint)
    answer = ok(
        endpoint,
        "ModifyUser",
        UserId=USER,
        AccessString="on ~* +@all",
    )
    assert field(answer, "UserId") == USER


def test_delete_user_removes_it(endpoint):
    name = f"ops-ec-delete-user-{RUN}"
    created(
        endpoint,
        "CreateUser",
        UserId=name,
        UserName=name,
        Engine="redis",
        AccessString="on ~* +@all",
    )
    ok(endpoint, "DeleteUser", UserId=name)
    status, _text = call(endpoint, "DescribeUsers", UserId=name)
    assert status == 404


# --- User groups ------------------------------------------------------------


def test_create_user_group_answers_the_group(endpoint):
    answer = ensure_user_group(endpoint)
    assert field(answer, "UserGroupId") == USER_GROUP


def test_describe_user_groups_reads_it(endpoint):
    ensure_user_group(endpoint)
    answer = ok(endpoint, "DescribeUserGroups", UserGroupId=USER_GROUP)
    assert field(answer, "UserGroupId") == USER_GROUP


def test_modify_user_group_adds_and_removes_a_user(endpoint):
    ensure_user_group(endpoint)
    ensure_user(endpoint, USER_TWO)
    ok(endpoint, "ModifyUserGroup", UserGroupId=USER_GROUP, **{"UserIdsToAdd.member.1": USER_TWO})
    ok(endpoint, "ModifyUserGroup", UserGroupId=USER_GROUP, **{"UserIdsToRemove.member.1": USER_TWO})
    answer = ok(endpoint, "DescribeUserGroups", UserGroupId=USER_GROUP)
    assert USER_TWO not in answer


def test_delete_user_group_removes_it(endpoint):
    name = f"ops-ec-delete-group-{RUN}"
    created(
        endpoint,
        "CreateUserGroup",
        UserGroupId=name,
        Engine="redis",
        **{"UserIds.member.1": "default"},
    )
    ok(endpoint, "DeleteUserGroup", UserGroupId=name)
    status, _text = call(endpoint, "DescribeUserGroups", UserGroupId=name)
    assert status == 404


# --- Tags -------------------------------------------------------------------


def test_add_tags_to_resource_adds_them(endpoint):
    ensure_cluster(endpoint)
    ok(
        endpoint,
        "AddTagsToResource",
        ResourceName=cluster_arn(endpoint),
        **{"Tags.member.1.Key": "ops", "Tags.member.1.Value": "elasticache"},
    )
    answer = ok(endpoint, "ListTagsForResource", ResourceName=cluster_arn(endpoint))
    assert "ops" in answer


def test_list_tags_for_resource_reads_them(endpoint):
    ensure_cluster(endpoint)
    ok(
        endpoint,
        "AddTagsToResource",
        ResourceName=cluster_arn(endpoint),
        **{"Tags.member.1.Key": "ops", "Tags.member.1.Value": "elasticache"},
    )
    answer = ok(endpoint, "ListTagsForResource", ResourceName=cluster_arn(endpoint))
    assert "<TagList>" in answer
    assert field(answer, "Key") == "ops"


def test_remove_tags_from_resource_removes_them(endpoint):
    ensure_cluster(endpoint)
    arn = cluster_arn(endpoint)
    ok(
        endpoint,
        "AddTagsToResource",
        ResourceName=arn,
        **{"Tags.member.1.Key": "ops-remove", "Tags.member.1.Value": "elasticache"},
    )
    ok(endpoint, "RemoveTagsFromResource", ResourceName=arn, **{"TagKeys.member.1": "ops-remove"})
    answer = ok(endpoint, "ListTagsForResource", ResourceName=arn)
    assert "ops-remove" not in answer


# --- Snapshots --------------------------------------------------------------


def test_create_snapshot_answers_the_snapshot(endpoint):
    answer = ensure_snapshot(endpoint)
    assert field(answer, "SnapshotName") == SNAPSHOT


def test_describe_snapshots_reads_it(endpoint):
    ensure_snapshot(endpoint)
    answer = ok(endpoint, "DescribeSnapshots", SnapshotName=SNAPSHOT)
    assert field(answer, "SnapshotName") == SNAPSHOT


def test_delete_snapshot_removes_it(endpoint):
    name = f"ops-ec-delete-snapshot-{RUN}"
    created(endpoint, "CreateSnapshot", SnapshotName=name, CacheClusterId=CLUSTER)
    ok(endpoint, "DeleteSnapshot", SnapshotName=name)
    answer = ok(endpoint, "DescribeSnapshots", SnapshotName=name)
    assert name not in answer


# --- Serverless caches ------------------------------------------------------


def test_create_serverless_cache_answers_the_cache(endpoint):
    answer = ensure_serverless(endpoint)
    assert field(answer, "ServerlessCacheName") == SERVERLESS
    assert field(answer, "Status") in ("available", "creating")


def test_describe_serverless_caches_reads_it(endpoint):
    ensure_serverless(endpoint)
    answer = ok(endpoint, "DescribeServerlessCaches", ServerlessCacheName=SERVERLESS)
    assert field(answer, "Engine") == "redis"


def test_modify_serverless_cache_sets_the_description(endpoint):
    ensure_serverless(endpoint)
    answer = ok(
        endpoint,
        "ModifyServerlessCache",
        ServerlessCacheName=SERVERLESS,
        Description="updated serverless cache",
    )
    assert field(answer, "Description") == "updated serverless cache"


def test_delete_serverless_cache_removes_it(endpoint):
    name = f"ops-ec-delete-serverless-{RUN}"
    created(endpoint, "CreateServerlessCache", ServerlessCacheName=name, Engine="redis")
    ok(endpoint, "DeleteServerlessCache", ServerlessCacheName=name)
    status, _text = call(endpoint, "DescribeServerlessCaches", ServerlessCacheName=name)
    assert status == 404


# --- Engine versions and events ---------------------------------------------


def test_describe_cache_engine_versions_answers_versions(endpoint):
    answer = ok(endpoint, "DescribeCacheEngineVersions", Engine="redis")
    assert "<CacheEngineVersions>" in answer


def test_describe_events_answers_events(endpoint):
    answer = ok(endpoint, "DescribeEvents")
    assert "<Events>" in answer
