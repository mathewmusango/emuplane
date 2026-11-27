---
sidebar_position: 80
title: Amazon DocumentDB coverage
---

Every DocumentDB operation the emulator advertises, and what Emuplane does with
it. The service is the RDS Query API (`Action=...`, XML answers) signed with the
`rds` credential scope, and the router claims a request by its `docdb` host, its
`Engine=docdb` member, or a cluster, instance or ARN it already holds, so clients
reach it without a `docdb` host name. There is no console action:
clusters, instances and their tags are driven over the wire.

A cluster is the unit and an instance is a member of one; engine versions run
from `3.6.0` through `8.0.2` and default to `8.0.0`, with the
`default.docdb8.0` cluster parameter group. Subnet groups and parameter groups
are shared with RDS — the emulator reads and writes the same stores — so a group
created through either service is visible to both.

When Docker is available the emulator backs a cluster with a real
`documentdb-local` container; without it — the usual case, and the one these
tests run against — clusters and instances are control-plane records that settle
`available`, so start, stop and failover move status and membership rather than
compute. A stable cluster, its writer and a reader carry the read, modify,
reboot and failover rows; the delete rows create a cluster or instance of their
own.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **15**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **15**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **3**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **15** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateDBCluster` | — | not yet | tests/control/test_documentdb_operations.py |
| `CreateDBInstance` | — | not yet | tests/control/test_documentdb_operations.py |
| `DescribeDBClusters` | — | not yet | tests/control/test_documentdb_operations.py |
| `DescribeDBInstances` | — | not yet | tests/control/test_documentdb_operations.py |
| `ModifyDBCluster` | — | not yet | tests/control/test_documentdb_operations.py |
| `ModifyDBInstance` | — | not yet | tests/control/test_documentdb_operations.py |
| `RebootDBInstance` | — | not yet | tests/control/test_documentdb_operations.py |
| `StartDBCluster` | — | not yet | tests/control/test_documentdb_operations.py |
| `StopDBCluster` | — | not yet | tests/control/test_documentdb_operations.py |
| `FailoverDBCluster` | — | not yet | tests/control/test_documentdb_operations.py |
| `DeleteDBCluster` | — | not yet | tests/control/test_documentdb_operations.py |
| `DeleteDBInstance` | — | not yet | tests/control/test_documentdb_operations.py |
| `AddTagsToResource` | — | not yet | tests/control/test_documentdb_operations.py |
| `RemoveTagsFromResource` | — | not yet | tests/control/test_documentdb_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_documentdb_operations.py |

<!-- coverage:end -->
