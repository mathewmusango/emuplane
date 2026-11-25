---
sidebar_position: 73
title: RDS coverage
---

Every RDS operation the emulator advertises, and what Emuplane does with it. The
control plane is the Query API (`Action=…`, XML answers) signed with the `rds`
credential scope. There is no console action.

The emulator can back an instance or cluster with a real Postgres/MySQL container
when Docker is available; without it — the usual case, and the one the tests run
against — every resource is a control-plane record that provisions `available`. A
stable instance, cluster, snapshot, group and proxy carry the read, modify and tag
rows; delete and lifecycle actions make their own resource. Global clusters span two
regions under one account so switchover and failover have a secondary to promote.

One wire-shape caveat: the emulator wraps each global cluster in
`<GlobalClusterMember>` in `DescribeGlobalClusters`, where the service model expects
`<GlobalCluster>`, so a botocore client parses an empty list even though the clusters
are there. The coverage test reads the raw XML, which is also how the other RDS rows
are asserted.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **66**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **66**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **20**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **66** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateDBInstance` | — | not yet | tests/control/test_rds_operations.py |
| `DeleteDBInstance` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBInstances` | — | not yet | tests/control/test_rds_operations.py |
| `ModifyDBInstance` | — | not yet | tests/control/test_rds_operations.py |
| `StartDBInstance` | — | not yet | tests/control/test_rds_operations.py |
| `StopDBInstance` | — | not yet | tests/control/test_rds_operations.py |
| `RebootDBInstance` | — | not yet | tests/control/test_rds_operations.py |
| `CreateDBInstanceReadReplica` | — | not yet | tests/control/test_rds_operations.py |
| `RestoreDBInstanceFromDBSnapshot` | — | not yet | tests/control/test_rds_operations.py |
| `CreateDBCluster` | — | not yet | tests/control/test_rds_operations.py |
| `DeleteDBCluster` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBClusters` | — | not yet | tests/control/test_rds_operations.py |
| `ModifyDBCluster` | — | not yet | tests/control/test_rds_operations.py |
| `StartDBCluster` | — | not yet | tests/control/test_rds_operations.py |
| `StopDBCluster` | — | not yet | tests/control/test_rds_operations.py |
| `FailoverDBCluster` | — | not yet | tests/control/test_rds_operations.py |
| `SwitchoverGlobalCluster` | — | not yet | tests/control/test_rds_operations.py |
| `FailoverGlobalCluster` | — | not yet | tests/control/test_rds_operations.py |
| `CreateDBSnapshot` | — | not yet | tests/control/test_rds_operations.py |
| `DeleteDBSnapshot` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBSnapshots` | — | not yet | tests/control/test_rds_operations.py |
| `CreateDBClusterSnapshot` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBClusterSnapshots` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBClusterSnapshotAttributes` | — | not yet | tests/control/test_rds_operations.py |
| `DeleteDBClusterSnapshot` | — | not yet | tests/control/test_rds_operations.py |
| `CreateDBSubnetGroup` | — | not yet | tests/control/test_rds_operations.py |
| `DeleteDBSubnetGroup` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBSubnetGroups` | — | not yet | tests/control/test_rds_operations.py |
| `ModifyDBSubnetGroup` | — | not yet | tests/control/test_rds_operations.py |
| `CreateDBParameterGroup` | — | not yet | tests/control/test_rds_operations.py |
| `DeleteDBParameterGroup` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBParameterGroups` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBParameters` | — | not yet | tests/control/test_rds_operations.py |
| `ModifyDBParameterGroup` | — | not yet | tests/control/test_rds_operations.py |
| `CreateDBClusterParameterGroup` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBClusterParameterGroups` | — | not yet | tests/control/test_rds_operations.py |
| `DeleteDBClusterParameterGroup` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBClusterParameters` | — | not yet | tests/control/test_rds_operations.py |
| `ModifyDBClusterParameterGroup` | — | not yet | tests/control/test_rds_operations.py |
| `CreateOptionGroup` | — | not yet | tests/control/test_rds_operations.py |
| `DeleteOptionGroup` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeOptionGroups` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeOptionGroupOptions` | — | not yet | tests/control/test_rds_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_rds_operations.py |
| `AddTagsToResource` | — | not yet | tests/control/test_rds_operations.py |
| `RemoveTagsFromResource` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBEngineVersions` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeOrderableDBInstanceOptions` | — | not yet | tests/control/test_rds_operations.py |
| `CreateGlobalCluster` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeGlobalClusters` | — | not yet | tests/control/test_rds_operations.py |
| `DeleteGlobalCluster` | — | not yet | tests/control/test_rds_operations.py |
| `RemoveFromGlobalCluster` | — | not yet | tests/control/test_rds_operations.py |
| `ModifyGlobalCluster` | — | not yet | tests/control/test_rds_operations.py |
| `CreateDBProxy` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBProxies` | — | not yet | tests/control/test_rds_operations.py |
| `ModifyDBProxy` | — | not yet | tests/control/test_rds_operations.py |
| `DeleteDBProxy` | — | not yet | tests/control/test_rds_operations.py |
| `CreateDBProxyEndpoint` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBProxyEndpoints` | — | not yet | tests/control/test_rds_operations.py |
| `ModifyDBProxyEndpoint` | — | not yet | tests/control/test_rds_operations.py |
| `DeleteDBProxyEndpoint` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBProxyTargetGroups` | — | not yet | tests/control/test_rds_operations.py |
| `ModifyDBProxyTargetGroup` | — | not yet | tests/control/test_rds_operations.py |
| `RegisterDBProxyTargets` | — | not yet | tests/control/test_rds_operations.py |
| `DeregisterDBProxyTargets` | — | not yet | tests/control/test_rds_operations.py |
| `DescribeDBProxyTargets` | — | not yet | tests/control/test_rds_operations.py |

<!-- coverage:end -->
