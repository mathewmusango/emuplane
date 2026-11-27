"""RDS on the wire: all 66 advertised operations, Query/XML.

Signed with the `rds` credential scope and sent form-encoded (`Action=...`).
Instances, clusters, snapshots, groups and proxies are records: nothing here
needs Docker, so a create lands `available` and a read proves it. Stable names
carry the read/modify tests; delete tests and lifecycle tests make their own.
Global-cluster membership spans two regions with the same account.
"""

from __future__ import annotations

import re
import secrets
from urllib.parse import urlencode

import signed
from conftest import ACCOUNT

REGION = "us-east-1"
SECONDARY = "us-west-2"
VERSION = "2014-10-31"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
RUN = secrets.token_hex(3)

INSTANCE = "ops-rds-instance"
LIFECYCLE = f"ops-rds-lifecycle-{RUN}"
CLUSTER = "ops-rds-cluster"
SNAPSHOT = "ops-rds-snapshot"
CLUSTER_SNAPSHOT = "ops-rds-cluster-snapshot"
SUBNET_GROUP = "ops-rds-subnet-group"
PARAM_GROUP = "ops-rds-param-group"
CLUSTER_PARAM_GROUP = "ops-rds-cluster-param-group"
OPTION_GROUP = "ops-rds-option-group"
GLOBAL = f"ops-rds-global-{RUN}"
GLOBAL_WRITER = f"ops-rds-gw-{RUN}"
GLOBAL_SECONDARY = f"ops-rds-gs-{RUN}"
PROXY = "ops-rds-proxy"
PROXY_ENDPOINT = "ops-rds-proxy-endpoint"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/ops-rds-proxy-role"


def call(endpoint, action: str, region: str = REGION, **params):
    body = urlencode({"Action": action, "Version": VERSION, **params})
    return signed.request(endpoint, "rds", ACCOUNT, region, "POST", "/", body, FORM)


def ok(endpoint, action: str, region: str = REGION, **params) -> str:
    status, text = call(endpoint, action, region=region, **params)
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


# --- EC2 defaults the group and proxy creates need --------------------------


def default_subnets(endpoint) -> list[str]:
    body = urlencode({"Action": "DescribeSubnets", "Version": "2016-11-15"})
    status, text = signed.request(
        endpoint, "ec2", ACCOUNT, REGION, "POST", "/", body, FORM
    )
    assert status == 200, text[:300]
    subnets = re.findall(r"<subnetId>([^<]+)</subnetId>", text)
    assert len(subnets) >= 2, "EC2 has no default subnets"
    return subnets[:2]


def subnet_params(endpoint) -> dict:
    first, second = default_subnets(endpoint)
    return {"SubnetIds.member.1": first, "SubnetIds.member.2": second}


# --- Instances --------------------------------------------------------------


def create_instance(endpoint, name: str, **extra) -> str:
    return created(
        endpoint,
        "CreateDBInstance",
        DBInstanceIdentifier=name,
        DBInstanceClass="db.t3.micro",
        Engine="postgres",
        AllocatedStorage="20",
        **extra,
    )


def describe_instance(endpoint, name: str) -> str:
    return ok(endpoint, "DescribeDBInstances", DBInstanceIdentifier=name)


def instance_status(endpoint, name: str) -> str:
    return field(describe_instance(endpoint, name), "DBInstanceStatus")


def instance_arn(endpoint, name: str) -> str:
    return field(describe_instance(endpoint, name), "DBInstanceArn")


def ensure_instance(endpoint, name: str = INSTANCE) -> str:
    create_instance(endpoint, name)
    return describe_instance(endpoint, name)


def ensure_instance_available(endpoint, name: str) -> str:
    create_instance(endpoint, name)
    if instance_status(endpoint, name) != "available":
        ok(endpoint, "StartDBInstance", DBInstanceIdentifier=name)
    return describe_instance(endpoint, name)


# --- Clusters ---------------------------------------------------------------


def create_cluster(endpoint, name: str, region: str = REGION, **extra) -> str:
    return created(
        endpoint,
        "CreateDBCluster",
        region=region,
        DBClusterIdentifier=name,
        Engine="aurora-postgresql",
        MasterUsername="admin",
        MasterUserPassword="password",
        **extra,
    )


def describe_cluster(endpoint, name: str) -> str:
    return ok(endpoint, "DescribeDBClusters", DBClusterIdentifier=name)


def cluster_status(endpoint, name: str) -> str:
    return field(describe_cluster(endpoint, name), "Status")


def ensure_cluster_available(endpoint, name: str = CLUSTER) -> str:
    create_cluster(endpoint, name)
    if cluster_status(endpoint, name) != "available":
        ok(endpoint, "StartDBCluster", DBClusterIdentifier=name)
    return describe_cluster(endpoint, name)


def create_cluster_member(endpoint, cluster: str, name: str) -> str:
    return created(
        endpoint,
        "CreateDBInstance",
        DBInstanceIdentifier=name,
        DBInstanceClass="db.t3.micro",
        Engine="aurora-postgresql",
        DBClusterIdentifier=cluster,
    )


def ensure_cluster_members(endpoint, cluster: str = CLUSTER) -> None:
    ensure_cluster_available(endpoint, cluster)
    create_cluster_member(endpoint, cluster, f"{cluster}-a")
    create_cluster_member(endpoint, cluster, f"{cluster}-b")


# --- Snapshots --------------------------------------------------------------


def ensure_snapshot(endpoint, instance: str = INSTANCE) -> None:
    ensure_instance_available(endpoint, instance)
    created(
        endpoint,
        "CreateDBSnapshot",
        DBSnapshotIdentifier=SNAPSHOT,
        DBInstanceIdentifier=instance,
    )


def ensure_cluster_snapshot(endpoint, cluster: str = CLUSTER) -> None:
    ensure_cluster_available(endpoint, cluster)
    created(
        endpoint,
        "CreateDBClusterSnapshot",
        DBClusterSnapshotIdentifier=CLUSTER_SNAPSHOT,
        DBClusterIdentifier=cluster,
    )


# --- Groups -----------------------------------------------------------------


def ensure_subnet_group(endpoint) -> None:
    created(
        endpoint,
        "CreateDBSubnetGroup",
        DBSubnetGroupName=SUBNET_GROUP,
        DBSubnetGroupDescription="ops subnet group",
        **subnet_params(endpoint),
    )


def ensure_param_group(endpoint) -> None:
    created(
        endpoint,
        "CreateDBParameterGroup",
        DBParameterGroupName=PARAM_GROUP,
        DBParameterGroupFamily="postgres15",
        Description="ops parameter group",
    )


def ensure_cluster_param_group(endpoint) -> None:
    created(
        endpoint,
        "CreateDBClusterParameterGroup",
        DBClusterParameterGroupName=CLUSTER_PARAM_GROUP,
        DBParameterGroupFamily="aurora-postgresql15",
        Description="ops cluster parameter group",
    )


def ensure_option_group(endpoint) -> None:
    created(
        endpoint,
        "CreateOptionGroup",
        OptionGroupName=OPTION_GROUP,
        EngineName="postgres",
        MajorEngineVersion="15",
        OptionGroupDescription="ops option group",
    )


# --- Global clusters --------------------------------------------------------


def ensure_global(endpoint) -> None:
    created(
        endpoint,
        "CreateGlobalCluster",
        GlobalClusterIdentifier=GLOBAL,
        Engine="aurora-postgresql",
    )
    create_cluster(endpoint, GLOBAL_WRITER, GlobalClusterIdentifier=GLOBAL)
    create_cluster(
        endpoint,
        GLOBAL_SECONDARY,
        region=SECONDARY,
        GlobalClusterIdentifier=GLOBAL,
    )


def global_members(endpoint, global_id: str = GLOBAL) -> list[tuple[str, bool]]:
    # The emulator nests each cluster in <GlobalClusterMember> where the service
    # model expects <GlobalCluster>, so the member entries are the ones that
    # start with a DBClusterArn; the outer wrapper starts with the identifier.
    text = ok(endpoint, "DescribeGlobalClusters", GlobalClusterIdentifier=global_id)
    members = []
    for block in re.findall(
        r"<GlobalClusterMember>\s*<DBClusterArn>(.*?)</GlobalClusterMember>", text, re.S
    ):
        arn = re.match(r"([^<]+)", block)
        writer = re.search(r"<IsWriter>([^<]+)</IsWriter>", block)
        if arn:
            members.append((arn.group(1), (writer.group(1) if writer else "false") == "true"))
    return members


# --- Proxies ----------------------------------------------------------------


def ensure_proxy(endpoint) -> None:
    first, second = default_subnets(endpoint)
    created(
        endpoint,
        "CreateDBProxy",
        DBProxyName=PROXY,
        EngineFamily="POSTGRESQL",
        RoleArn=ROLE_ARN,
        DefaultAuthScheme="IAM_AUTH",
        **{"VpcSubnetIds.member.1": first, "VpcSubnetIds.member.2": second},
    )


def ensure_proxy_endpoint(endpoint) -> None:
    ensure_proxy(endpoint)
    first, second = default_subnets(endpoint)
    created(
        endpoint,
        "CreateDBProxyEndpoint",
        DBProxyName=PROXY,
        DBProxyEndpointName=PROXY_ENDPOINT,
        **{"VpcSubnetIds.member.1": first, "VpcSubnetIds.member.2": second},
    )


def proxy_targets(endpoint) -> list[str]:
    text = ok(endpoint, "DescribeDBProxyTargets", DBProxyName=PROXY, TargetGroupName="default")
    return re.findall(r"<RdsResourceId>([^<]+)</RdsResourceId>", text)


def ensure_proxy_target(endpoint) -> None:
    ensure_proxy(endpoint)
    ensure_instance_available(endpoint, INSTANCE)
    if INSTANCE not in proxy_targets(endpoint):
        ok(
            endpoint,
            "RegisterDBProxyTargets",
            DBProxyName=PROXY,
            TargetGroupName="default",
            **{"DBInstanceIdentifiers.member.1": INSTANCE},
        )


# --- Instances --------------------------------------------------------------


def test_create_db_instance_answers_the_instance(endpoint):
    answer = ensure_instance(endpoint)
    assert field(answer, "DBInstanceIdentifier") == INSTANCE
    assert field(answer, "DBInstanceStatus") in ("available", "creating")


def test_describe_db_instances_reads_it(endpoint):
    ensure_instance(endpoint)
    answer = describe_instance(endpoint, INSTANCE)
    assert field(answer, "Engine") == "postgres"
    assert field(answer, "DBInstanceIdentifier") == INSTANCE


def test_delete_db_instance_removes_it(endpoint):
    name = f"ops-rds-delete-instance-{RUN}"
    create_instance(endpoint, name)
    ok(endpoint, "DeleteDBInstance", DBInstanceIdentifier=name, SkipFinalSnapshot="true")
    status, _text = call(endpoint, "DescribeDBInstances", DBInstanceIdentifier=name)
    assert status == 404


def test_modify_db_instance_applies_the_class(endpoint):
    ensure_instance_available(endpoint, INSTANCE)
    ok(
        endpoint,
        "ModifyDBInstance",
        DBInstanceIdentifier=INSTANCE,
        DBInstanceClass="db.t3.small",
        ApplyImmediately="true",
    )
    assert field(describe_instance(endpoint, INSTANCE), "DBInstanceClass") == "db.t3.small"
    ok(
        endpoint,
        "ModifyDBInstance",
        DBInstanceIdentifier=INSTANCE,
        DBInstanceClass="db.t3.micro",
        ApplyImmediately="true",
    )


def test_create_db_instance_read_replica_answers_the_replica(endpoint):
    ensure_instance_available(endpoint, INSTANCE)
    replica = f"ops-rds-replica-{RUN}"
    created(
        endpoint,
        "CreateDBInstanceReadReplica",
        DBInstanceIdentifier=replica,
        SourceDBInstanceIdentifier=INSTANCE,
    )
    answer = describe_instance(endpoint, replica)
    assert field(answer, "ReadReplicaSourceDBInstanceIdentifier") == INSTANCE


def test_restore_db_instance_from_db_snapshot_answers_the_instance(endpoint):
    ensure_snapshot(endpoint)
    restored = f"ops-rds-restored-{RUN}"
    created(
        endpoint,
        "RestoreDBInstanceFromDBSnapshot",
        DBInstanceIdentifier=restored,
        DBSnapshotIdentifier=SNAPSHOT,
    )
    assert field(describe_instance(endpoint, restored), "DBInstanceIdentifier") == restored


# --- Instance lifecycle (stopped/started/rebuilt in place) -------------------


def test_stop_db_instance_stops_it(endpoint):
    ensure_instance_available(endpoint, LIFECYCLE)
    answer = ok(endpoint, "StopDBInstance", DBInstanceIdentifier=LIFECYCLE)
    assert field(answer, "DBInstanceStatus") == "stopped"


def test_start_db_instance_starts_it(endpoint):
    create_instance(endpoint, LIFECYCLE)
    if instance_status(endpoint, LIFECYCLE) != "stopped":
        ok(endpoint, "StopDBInstance", DBInstanceIdentifier=LIFECYCLE)
    answer = ok(endpoint, "StartDBInstance", DBInstanceIdentifier=LIFECYCLE)
    assert field(answer, "DBInstanceStatus") in ("available", "starting")


def test_reboot_db_instance_reboots_it(endpoint):
    ensure_instance_available(endpoint, LIFECYCLE)
    answer = ok(endpoint, "RebootDBInstance", DBInstanceIdentifier=LIFECYCLE)
    assert field(answer, "DBInstanceIdentifier") == LIFECYCLE


# --- Clusters ---------------------------------------------------------------


def test_create_db_cluster_answers_the_cluster(endpoint):
    answer = ensure_cluster_available(endpoint)
    assert field(answer, "DBClusterIdentifier") == CLUSTER
    assert field(answer, "Status") in ("available", "creating")


def test_describe_db_clusters_reads_it(endpoint):
    ensure_cluster_available(endpoint)
    answer = describe_cluster(endpoint, CLUSTER)
    assert field(answer, "Engine") == "aurora-postgresql"


def test_modify_db_cluster_sets_backup_retention(endpoint):
    ensure_cluster_available(endpoint)
    answer = ok(endpoint, "ModifyDBCluster", DBClusterIdentifier=CLUSTER, BackupRetentionPeriod="7")
    assert field(answer, "BackupRetentionPeriod") == "7"


def test_stop_db_cluster_stops_it(endpoint):
    ensure_cluster_available(endpoint)
    answer = ok(endpoint, "StopDBCluster", DBClusterIdentifier=CLUSTER)
    assert field(answer, "Status") == "stopped"


def test_start_db_cluster_starts_it(endpoint):
    create_cluster(endpoint, CLUSTER)
    if cluster_status(endpoint, CLUSTER) != "stopped":
        ok(endpoint, "StopDBCluster", DBClusterIdentifier=CLUSTER)
    answer = ok(endpoint, "StartDBCluster", DBClusterIdentifier=CLUSTER)
    assert field(answer, "Status") in ("available", "starting")


def test_failover_db_cluster_promotes_a_reader(endpoint):
    ensure_cluster_members(endpoint)
    answer = ok(endpoint, "FailoverDBCluster", DBClusterIdentifier=CLUSTER)
    assert field(answer, "DBClusterIdentifier") == CLUSTER


def test_delete_db_cluster_removes_it(endpoint):
    cluster = f"ops-rds-delete-cluster-{RUN}"
    create_cluster(endpoint, cluster)
    ok(endpoint, "DeleteDBCluster", DBClusterIdentifier=cluster)
    status, _text = call(endpoint, "DescribeDBClusters", DBClusterIdentifier=cluster)
    assert status == 404


# --- Snapshots --------------------------------------------------------------


def test_create_db_snapshot_answers_the_snapshot(endpoint):
    ensure_instance_available(endpoint, INSTANCE)
    created(
        endpoint,
        "CreateDBSnapshot",
        DBSnapshotIdentifier=SNAPSHOT,
        DBInstanceIdentifier=INSTANCE,
    )
    answer = ok(endpoint, "DescribeDBSnapshots", DBSnapshotIdentifier=SNAPSHOT)
    assert field(answer, "DBSnapshotIdentifier") == SNAPSHOT
    assert field(answer, "DBInstanceIdentifier") == INSTANCE


def test_describe_db_snapshots_reads_it(endpoint):
    ensure_snapshot(endpoint)
    answer = ok(endpoint, "DescribeDBSnapshots", DBSnapshotIdentifier=SNAPSHOT)
    assert field(answer, "DBSnapshotIdentifier") == SNAPSHOT


def test_delete_db_snapshot_removes_it(endpoint):
    snapshot = f"ops-rds-delete-snapshot-{RUN}"
    ensure_instance_available(endpoint, INSTANCE)
    created(
        endpoint,
        "CreateDBSnapshot",
        DBSnapshotIdentifier=snapshot,
        DBInstanceIdentifier=INSTANCE,
    )
    ok(endpoint, "DeleteDBSnapshot", DBSnapshotIdentifier=snapshot)
    status, _text = call(endpoint, "DescribeDBSnapshots", DBSnapshotIdentifier=snapshot)
    assert status == 404


def test_create_db_cluster_snapshot_answers_the_snapshot(endpoint):
    ensure_cluster_snapshot(endpoint)
    answer = ok(
        endpoint, "DescribeDBClusterSnapshots", DBClusterSnapshotIdentifier=CLUSTER_SNAPSHOT
    )
    assert field(answer, "DBClusterSnapshotIdentifier") == CLUSTER_SNAPSHOT


def test_describe_db_cluster_snapshots_reads_it(endpoint):
    ensure_cluster_snapshot(endpoint)
    answer = ok(
        endpoint, "DescribeDBClusterSnapshots", DBClusterSnapshotIdentifier=CLUSTER_SNAPSHOT
    )
    assert field(answer, "DBClusterSnapshotIdentifier") == CLUSTER_SNAPSHOT


def test_describe_db_cluster_snapshot_attributes_reads_them(endpoint):
    ensure_cluster_snapshot(endpoint)
    answer = ok(
        endpoint,
        "DescribeDBClusterSnapshotAttributes",
        DBClusterSnapshotIdentifier=CLUSTER_SNAPSHOT,
    )
    assert field(answer, "DBClusterSnapshotIdentifier") == CLUSTER_SNAPSHOT


def test_delete_db_cluster_snapshot_removes_it(endpoint):
    snapshot = f"ops-rds-delete-cluster-snapshot-{RUN}"
    ensure_cluster_available(endpoint)
    created(
        endpoint,
        "CreateDBClusterSnapshot",
        DBClusterSnapshotIdentifier=snapshot,
        DBClusterIdentifier=CLUSTER,
    )
    ok(endpoint, "DeleteDBClusterSnapshot", DBClusterSnapshotIdentifier=snapshot)
    status, _text = call(
        endpoint, "DescribeDBClusterSnapshots", DBClusterSnapshotIdentifier=snapshot
    )
    assert status == 404


# --- Subnet groups ----------------------------------------------------------


def test_create_db_subnet_group_answers_the_group(endpoint):
    answer = created(
        endpoint,
        "CreateDBSubnetGroup",
        DBSubnetGroupName=SUBNET_GROUP,
        DBSubnetGroupDescription="ops subnet group",
        **subnet_params(endpoint),
    )
    assert field(answer, "DBSubnetGroupName") == SUBNET_GROUP


def test_describe_db_subnet_groups_reads_it(endpoint):
    ensure_subnet_group(endpoint)
    answer = ok(endpoint, "DescribeDBSubnetGroups", DBSubnetGroupName=SUBNET_GROUP)
    assert field(answer, "DBSubnetGroupName") == SUBNET_GROUP


def test_modify_db_subnet_group_sets_the_description(endpoint):
    ensure_subnet_group(endpoint)
    answer = ok(
        endpoint,
        "ModifyDBSubnetGroup",
        DBSubnetGroupName=SUBNET_GROUP,
        DBSubnetGroupDescription="updated subnet group",
    )
    assert field(answer, "DBSubnetGroupDescription") == "updated subnet group"


def test_delete_db_subnet_group_removes_it(endpoint):
    group = f"ops-rds-delete-subnet-{RUN}"
    created(
        endpoint,
        "CreateDBSubnetGroup",
        DBSubnetGroupName=group,
        DBSubnetGroupDescription="delete me",
        **subnet_params(endpoint),
    )
    ok(endpoint, "DeleteDBSubnetGroup", DBSubnetGroupName=group)
    status, _text = call(endpoint, "DescribeDBSubnetGroups", DBSubnetGroupName=group)
    assert status == 404


# --- Parameter groups -------------------------------------------------------


def test_create_db_parameter_group_answers_the_group(endpoint):
    ensure_param_group(endpoint)
    answer = ok(endpoint, "DescribeDBParameterGroups", DBParameterGroupName=PARAM_GROUP)
    assert field(answer, "DBParameterGroupName") == PARAM_GROUP


def test_describe_db_parameter_groups_reads_it(endpoint):
    ensure_param_group(endpoint)
    answer = ok(endpoint, "DescribeDBParameterGroups", DBParameterGroupName=PARAM_GROUP)
    assert field(answer, "DBParameterGroupName") == PARAM_GROUP


def test_describe_db_parameters_reads_them(endpoint):
    ensure_param_group(endpoint)
    ok(
        endpoint,
        "ModifyDBParameterGroup",
        DBParameterGroupName=PARAM_GROUP,
        **{
            "Parameters.member.1.ParameterName": "max_connections",
            "Parameters.member.1.ParameterValue": "200",
        },
    )
    answer = ok(endpoint, "DescribeDBParameters", DBParameterGroupName=PARAM_GROUP)
    assert present(answer, "Parameter")


def test_modify_db_parameter_group_applies_a_parameter(endpoint):
    ensure_param_group(endpoint)
    answer = ok(
        endpoint,
        "ModifyDBParameterGroup",
        DBParameterGroupName=PARAM_GROUP,
        **{
            "Parameters.member.1.ParameterName": "work_mem",
            "Parameters.member.1.ParameterValue": "8MB",
        },
    )
    assert field(answer, "DBParameterGroupName") == PARAM_GROUP


def test_delete_db_parameter_group_removes_it(endpoint):
    group = f"ops-rds-delete-param-{RUN}"
    created(
        endpoint,
        "CreateDBParameterGroup",
        DBParameterGroupName=group,
        DBParameterGroupFamily="postgres15",
        Description="delete me",
    )
    ok(endpoint, "DeleteDBParameterGroup", DBParameterGroupName=group)
    status, _text = call(endpoint, "DescribeDBParameterGroups", DBParameterGroupName=group)
    assert status == 404


def test_create_db_cluster_parameter_group_answers_the_group(endpoint):
    ensure_cluster_param_group(endpoint)
    answer = ok(
        endpoint,
        "DescribeDBClusterParameterGroups",
        DBClusterParameterGroupName=CLUSTER_PARAM_GROUP,
    )
    assert field(answer, "DBClusterParameterGroupName") == CLUSTER_PARAM_GROUP


def test_describe_db_cluster_parameter_groups_reads_it(endpoint):
    ensure_cluster_param_group(endpoint)
    answer = ok(
        endpoint,
        "DescribeDBClusterParameterGroups",
        DBClusterParameterGroupName=CLUSTER_PARAM_GROUP,
    )
    assert field(answer, "DBClusterParameterGroupName") == CLUSTER_PARAM_GROUP


def test_describe_db_cluster_parameters_reads_them(endpoint):
    ensure_cluster_param_group(endpoint)
    ok(
        endpoint,
        "ModifyDBClusterParameterGroup",
        DBClusterParameterGroupName=CLUSTER_PARAM_GROUP,
        **{
            "Parameters.member.1.ParameterName": "max_connections",
            "Parameters.member.1.ParameterValue": "250",
        },
    )
    answer = ok(
        endpoint, "DescribeDBClusterParameters", DBClusterParameterGroupName=CLUSTER_PARAM_GROUP
    )
    assert present(answer, "Parameter")


def test_modify_db_cluster_parameter_group_applies_a_parameter(endpoint):
    ensure_cluster_param_group(endpoint)
    answer = ok(
        endpoint,
        "ModifyDBClusterParameterGroup",
        DBClusterParameterGroupName=CLUSTER_PARAM_GROUP,
        **{
            "Parameters.member.1.ParameterName": "work_mem",
            "Parameters.member.1.ParameterValue": "8MB",
        },
    )
    assert field(answer, "DBClusterParameterGroupName") == CLUSTER_PARAM_GROUP


def test_delete_db_cluster_parameter_group_removes_it(endpoint):
    group = f"ops-rds-delete-cluster-param-{RUN}"
    created(
        endpoint,
        "CreateDBClusterParameterGroup",
        DBClusterParameterGroupName=group,
        DBParameterGroupFamily="aurora-postgresql15",
        Description="delete me",
    )
    ok(endpoint, "DeleteDBClusterParameterGroup", DBClusterParameterGroupName=group)
    status, _text = call(
        endpoint, "DescribeDBClusterParameterGroups", DBClusterParameterGroupName=group
    )
    assert status == 404


# --- Option groups ----------------------------------------------------------


def test_create_option_group_answers_the_group(endpoint):
    ensure_option_group(endpoint)
    answer = ok(endpoint, "DescribeOptionGroups", OptionGroupName=OPTION_GROUP)
    assert field(answer, "OptionGroupName") == OPTION_GROUP


def test_describe_option_groups_reads_it(endpoint):
    ensure_option_group(endpoint)
    answer = ok(endpoint, "DescribeOptionGroups", OptionGroupName=OPTION_GROUP)
    assert field(answer, "OptionGroupName") == OPTION_GROUP


def test_describe_option_group_options_answers_options(endpoint):
    answer = ok(
        endpoint,
        "DescribeOptionGroupOptions",
        EngineName="postgres",
        MajorEngineVersion="15",
    )
    assert "OptionGroupOptions" in answer


def test_delete_option_group_removes_it(endpoint):
    group = f"ops-rds-delete-option-{RUN}"
    created(
        endpoint,
        "CreateOptionGroup",
        OptionGroupName=group,
        EngineName="postgres",
        MajorEngineVersion="15",
        OptionGroupDescription="delete me",
    )
    ok(endpoint, "DeleteOptionGroup", OptionGroupName=group)
    status, _text = call(endpoint, "DescribeOptionGroups", OptionGroupName=group)
    assert status == 404


# --- Tags -------------------------------------------------------------------


def test_add_tags_to_resource_adds_them(endpoint):
    ensure_instance_available(endpoint, INSTANCE)
    arn = instance_arn(endpoint, INSTANCE)
    ok(
        endpoint,
        "AddTagsToResource",
        ResourceName=arn,
        **{"Tags.member.1.Key": "ops", "Tags.member.1.Value": "rds"},
    )
    answer = ok(endpoint, "ListTagsForResource", ResourceName=arn)
    assert "ops" in answer


def test_list_tags_for_resource_reads_them(endpoint):
    ensure_instance_available(endpoint, INSTANCE)
    arn = instance_arn(endpoint, INSTANCE)
    ok(
        endpoint,
        "AddTagsToResource",
        ResourceName=arn,
        **{"Tags.member.1.Key": "ops", "Tags.member.1.Value": "rds"},
    )
    answer = ok(endpoint, "ListTagsForResource", ResourceName=arn)
    assert present(answer, "TagList")
    assert field(answer, "Key") == "ops"


def test_remove_tags_from_resource_removes_them(endpoint):
    ensure_instance_available(endpoint, INSTANCE)
    arn = instance_arn(endpoint, INSTANCE)
    ok(
        endpoint,
        "AddTagsToResource",
        ResourceName=arn,
        **{"Tags.member.1.Key": "ops-remove", "Tags.member.1.Value": "rds"},
    )
    ok(
        endpoint,
        "RemoveTagsFromResource",
        ResourceName=arn,
        **{"TagKeys.member.1": "ops-remove"},
    )
    answer = ok(endpoint, "ListTagsForResource", ResourceName=arn)
    assert "ops-remove" not in answer


# --- Engine and orderable options -------------------------------------------


def test_describe_db_engine_versions_answers_versions(endpoint):
    answer = ok(endpoint, "DescribeDBEngineVersions", Engine="postgres")
    assert present(answer, "DBEngineVersions")


def test_describe_orderable_db_instance_options_answers_options(endpoint):
    answer = ok(
        endpoint,
        "DescribeOrderableDBInstanceOptions",
        Engine="postgres",
        DBInstanceClass="db.t3.micro",
    )
    assert present(answer, "OrderableDBInstanceOptions")


# --- Global clusters --------------------------------------------------------


def test_create_global_cluster_answers_the_cluster(endpoint):
    created(
        endpoint,
        "CreateGlobalCluster",
        GlobalClusterIdentifier=GLOBAL,
        Engine="aurora-postgresql",
    )
    answer = ok(endpoint, "DescribeGlobalClusters", GlobalClusterIdentifier=GLOBAL)
    assert field(answer, "GlobalClusterIdentifier") == GLOBAL


def test_describe_global_clusters_reads_it(endpoint):
    ensure_global(endpoint)
    answer = ok(endpoint, "DescribeGlobalClusters", GlobalClusterIdentifier=GLOBAL)
    assert field(answer, "GlobalClusterIdentifier") == GLOBAL
    assert len(global_members(endpoint)) == 2


def test_modify_global_cluster_sets_deletion_protection(endpoint):
    ensure_global(endpoint)
    answer = ok(
        endpoint,
        "ModifyGlobalCluster",
        GlobalClusterIdentifier=GLOBAL,
        DeletionProtection="true",
    )
    assert field(answer, "DeletionProtection") == "true"
    ok(
        endpoint,
        "ModifyGlobalCluster",
        GlobalClusterIdentifier=GLOBAL,
        DeletionProtection="false",
    )


def test_switchover_global_cluster_promotes_the_secondary(endpoint):
    ensure_global(endpoint)
    secondary = next((arn for arn, writer in global_members(endpoint) if not writer), None)
    assert secondary, "global cluster has no secondary"
    answer = ok(
        endpoint,
        "SwitchoverGlobalCluster",
        GlobalClusterIdentifier=GLOBAL,
        TargetDbClusterIdentifier=secondary,
    )
    assert field(answer, "GlobalClusterIdentifier") == GLOBAL


def test_failover_global_cluster_promotes_the_secondary(endpoint):
    ensure_global(endpoint)
    secondary = next((arn for arn, writer in global_members(endpoint) if not writer), None)
    assert secondary, "global cluster has no secondary"
    answer = ok(
        endpoint,
        "FailoverGlobalCluster",
        GlobalClusterIdentifier=GLOBAL,
        TargetDbClusterIdentifier=secondary,
        AllowDataLoss="true",
    )
    assert field(answer, "GlobalClusterIdentifier") == GLOBAL


def test_remove_from_global_cluster_removes_the_member(endpoint):
    global_id = f"ops-rds-remove-global-{RUN}"
    member = f"ops-rds-remove-member-{RUN}"
    created(
        endpoint,
        "CreateGlobalCluster",
        GlobalClusterIdentifier=global_id,
        Engine="aurora-postgresql",
    )
    create_cluster(endpoint, member, GlobalClusterIdentifier=global_id)
    member_arn = field(describe_cluster(endpoint, member), "DBClusterArn")
    answer = ok(
        endpoint,
        "RemoveFromGlobalCluster",
        GlobalClusterIdentifier=global_id,
        DbClusterIdentifier=member_arn,
    )
    assert field(answer, "GlobalClusterIdentifier") == global_id
    assert not [arn for arn, _writer in global_members(endpoint, global_id)]


def test_delete_global_cluster_removes_it(endpoint):
    global_id = f"ops-rds-delete-global-{RUN}"
    created(
        endpoint,
        "CreateGlobalCluster",
        GlobalClusterIdentifier=global_id,
        Engine="aurora-postgresql",
    )
    ok(endpoint, "DeleteGlobalCluster", GlobalClusterIdentifier=global_id)
    status, _text = call(endpoint, "DescribeGlobalClusters", GlobalClusterIdentifier=global_id)
    assert status == 404


# --- Proxies ----------------------------------------------------------------


def test_create_db_proxy_answers_the_proxy(endpoint):
    ensure_proxy(endpoint)
    text = ok(endpoint, "DescribeDBProxies", DBProxyName=PROXY)
    assert field(text, "DBProxyName") == PROXY
    assert field(text, "EngineFamily") == "POSTGRESQL"


def test_describe_db_proxies_reads_it(endpoint):
    ensure_proxy(endpoint)
    answer = ok(endpoint, "DescribeDBProxies", DBProxyName=PROXY)
    assert field(answer, "EngineFamily") == "POSTGRESQL"


def test_modify_db_proxy_sets_idle_timeout(endpoint):
    ensure_proxy(endpoint)
    answer = ok(endpoint, "ModifyDBProxy", DBProxyName=PROXY, IdleClientTimeout="1200")
    assert field(answer, "IdleClientTimeout") == "1200"


def test_delete_db_proxy_removes_it(endpoint):
    proxy = f"ops-rds-delete-proxy-{RUN}"
    first, second = default_subnets(endpoint)
    created(
        endpoint,
        "CreateDBProxy",
        DBProxyName=proxy,
        EngineFamily="POSTGRESQL",
        RoleArn=ROLE_ARN,
        DefaultAuthScheme="IAM_AUTH",
        **{"VpcSubnetIds.member.1": first, "VpcSubnetIds.member.2": second},
    )
    ok(endpoint, "DeleteDBProxy", DBProxyName=proxy)
    status, _text = call(endpoint, "DescribeDBProxies", DBProxyName=proxy)
    assert status == 404


def test_create_db_proxy_endpoint_answers_the_endpoint(endpoint):
    ensure_proxy_endpoint(endpoint)
    answer = ok(
        endpoint, "DescribeDBProxyEndpoints", DBProxyEndpointName=PROXY_ENDPOINT
    )
    assert field(answer, "DBProxyEndpointName") == PROXY_ENDPOINT


def test_describe_db_proxy_endpoints_reads_it(endpoint):
    ensure_proxy_endpoint(endpoint)
    answer = ok(endpoint, "DescribeDBProxyEndpoints", DBProxyName=PROXY)
    assert PROXY_ENDPOINT in answer


def test_modify_db_proxy_endpoint_sets_security_groups(endpoint):
    ensure_proxy_endpoint(endpoint)
    answer = ok(
        endpoint,
        "ModifyDBProxyEndpoint",
        DBProxyEndpointName=PROXY_ENDPOINT,
        **{"VpcSecurityGroupIds.member.1": "sg-ops-proxy"},
    )
    assert "sg-ops-proxy" in answer


def test_delete_db_proxy_endpoint_removes_it(endpoint):
    ensure_proxy(endpoint)
    name = f"ops-rds-delete-proxy-endpoint-{RUN}"
    first, second = default_subnets(endpoint)
    created(
        endpoint,
        "CreateDBProxyEndpoint",
        DBProxyName=PROXY,
        DBProxyEndpointName=name,
        **{"VpcSubnetIds.member.1": first, "VpcSubnetIds.member.2": second},
    )
    ok(endpoint, "DeleteDBProxyEndpoint", DBProxyEndpointName=name)
    status, _text = call(endpoint, "DescribeDBProxyEndpoints", DBProxyEndpointName=name)
    assert status == 404


def test_describe_db_proxy_target_groups_reads_the_default_group(endpoint):
    ensure_proxy(endpoint)
    answer = ok(endpoint, "DescribeDBProxyTargetGroups", DBProxyName=PROXY)
    assert field(answer, "TargetGroupName") == "default"


def test_modify_db_proxy_target_group_sets_the_pool(endpoint):
    ensure_proxy(endpoint)
    answer = ok(
        endpoint,
        "ModifyDBProxyTargetGroup",
        DBProxyName=PROXY,
        TargetGroupName="default",
        **{"ConnectionPoolConfig.MaxConnectionsPercent": "50"},
    )
    assert field(answer, "MaxConnectionsPercent") == "50"


def test_register_db_proxy_targets_registers_the_instance(endpoint):
    ensure_proxy(endpoint)
    ensure_instance_available(endpoint, INSTANCE)
    if INSTANCE in proxy_targets(endpoint):
        ok(
            endpoint,
            "DeregisterDBProxyTargets",
            DBProxyName=PROXY,
            TargetGroupName="default",
            **{"DBInstanceIdentifiers.member.1": INSTANCE},
        )
    answer = ok(
        endpoint,
        "RegisterDBProxyTargets",
        DBProxyName=PROXY,
        TargetGroupName="default",
        **{"DBInstanceIdentifiers.member.1": INSTANCE},
    )
    assert INSTANCE in answer


def test_describe_db_proxy_targets_reads_the_target(endpoint):
    ensure_proxy_target(endpoint)
    assert INSTANCE in proxy_targets(endpoint)


def test_deregister_db_proxy_targets_removes_the_target(endpoint):
    ensure_proxy_target(endpoint)
    answer = ok(
        endpoint,
        "DeregisterDBProxyTargets",
        DBProxyName=PROXY,
        TargetGroupName="default",
        **{"DBInstanceIdentifiers.member.1": INSTANCE},
    )
    assert "DeregisterDBProxyTargetsResult" in answer
    assert INSTANCE not in proxy_targets(endpoint)
