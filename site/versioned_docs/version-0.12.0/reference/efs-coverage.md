---
sidebar_position: 42
title: EFS coverage
---

Every EFS operation the emulator advertises, and what Emuplane does with it. The
service is REST/JSON under `/2015-02-01/*`, signed with the `elasticfilesystem`
credential scope. There is no console action.

A file system is idempotent on its `CreationToken`. Mount targets are records
checked against the EC2 subnet, security groups and zone. Replication creates
records and copies nothing, and a file system in a replication configuration
cannot be deleted until the configuration is removed.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **28**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **28**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **10**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **28** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateFileSystem` | — | not yet | tests/control/test_efs_operations.py |
| `DescribeFileSystems` | — | not yet | tests/control/test_efs_operations.py |
| `DeleteFileSystem` | — | not yet | tests/control/test_efs_operations.py |
| `UpdateFileSystem` | — | not yet | tests/control/test_efs_operations.py |
| `CreateMountTarget` | — | not yet | tests/control/test_efs_operations.py |
| `DescribeMountTargets` | — | not yet | tests/control/test_efs_operations.py |
| `DeleteMountTarget` | — | not yet | tests/control/test_efs_operations.py |
| `DescribeMountTargetSecurityGroups` | — | not yet | tests/control/test_efs_operations.py |
| `ModifyMountTargetSecurityGroups` | — | not yet | tests/control/test_efs_operations.py |
| `CreateAccessPoint` | — | not yet | tests/control/test_efs_operations.py |
| `DescribeAccessPoints` | — | not yet | tests/control/test_efs_operations.py |
| `DeleteAccessPoint` | — | not yet | tests/control/test_efs_operations.py |
| `TagResource` | — | not yet | tests/control/test_efs_operations.py |
| `UntagResource` | — | not yet | tests/control/test_efs_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_efs_operations.py |
| `PutLifecycleConfiguration` | — | not yet | tests/control/test_efs_operations.py |
| `DescribeLifecycleConfiguration` | — | not yet | tests/control/test_efs_operations.py |
| `PutBackupPolicy` | — | not yet | tests/control/test_efs_operations.py |
| `DescribeBackupPolicy` | — | not yet | tests/control/test_efs_operations.py |
| `PutFileSystemPolicy` | — | not yet | tests/control/test_efs_operations.py |
| `DescribeFileSystemPolicy` | — | not yet | tests/control/test_efs_operations.py |
| `DeleteFileSystemPolicy` | — | not yet | tests/control/test_efs_operations.py |
| `UpdateFileSystemProtection` | — | not yet | tests/control/test_efs_operations.py |
| `CreateReplicationConfiguration` | — | not yet | tests/control/test_efs_operations.py |
| `DescribeReplicationConfigurations` | — | not yet | tests/control/test_efs_operations.py |
| `DeleteReplicationConfiguration` | — | not yet | tests/control/test_efs_operations.py |
| `DescribeAccountPreferences` | — | not yet | tests/control/test_efs_operations.py |
| `PutAccountPreferences` | — | not yet | tests/control/test_efs_operations.py |

<!-- coverage:end -->
