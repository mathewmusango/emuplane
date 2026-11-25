---
sidebar_position: 74
title: ElastiCache coverage
---

Every ElastiCache operation the emulator advertises, and what Emuplane does with it.
The control plane is the Query API (`Action=…`, XML answers) signed with the
`elasticache` credential scope. There is no console action.

With Docker the emulator starts real Redis/Valkey/Memcached containers; without it —
the usual case, and the one the tests run against — every cache, group and user is a
control-plane record whose endpoints point at the shared sidecar, so nothing here
waits on an image. Stable names carry the read, modify and tag rows; delete actions
make their own resource. A user group includes the built-in `default` user, which
Redis groups require.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **41**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **41**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **12**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **41** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateCacheCluster` | — | not yet | tests/control/test_elasticache_operations.py |
| `DeleteCacheCluster` | — | not yet | tests/control/test_elasticache_operations.py |
| `DescribeCacheClusters` | — | not yet | tests/control/test_elasticache_operations.py |
| `ModifyCacheCluster` | — | not yet | tests/control/test_elasticache_operations.py |
| `RebootCacheCluster` | — | not yet | tests/control/test_elasticache_operations.py |
| `CreateReplicationGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `DeleteReplicationGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `DescribeReplicationGroups` | — | not yet | tests/control/test_elasticache_operations.py |
| `ModifyReplicationGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `IncreaseReplicaCount` | — | not yet | tests/control/test_elasticache_operations.py |
| `DecreaseReplicaCount` | — | not yet | tests/control/test_elasticache_operations.py |
| `CreateCacheSubnetGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `DescribeCacheSubnetGroups` | — | not yet | tests/control/test_elasticache_operations.py |
| `ModifyCacheSubnetGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `DeleteCacheSubnetGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `CreateCacheParameterGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `DescribeCacheParameterGroups` | — | not yet | tests/control/test_elasticache_operations.py |
| `ModifyCacheParameterGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `ResetCacheParameterGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `DeleteCacheParameterGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `DescribeCacheParameters` | — | not yet | tests/control/test_elasticache_operations.py |
| `DescribeCacheEngineVersions` | — | not yet | tests/control/test_elasticache_operations.py |
| `CreateUser` | — | not yet | tests/control/test_elasticache_operations.py |
| `DescribeUsers` | — | not yet | tests/control/test_elasticache_operations.py |
| `DeleteUser` | — | not yet | tests/control/test_elasticache_operations.py |
| `ModifyUser` | — | not yet | tests/control/test_elasticache_operations.py |
| `CreateUserGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `DescribeUserGroups` | — | not yet | tests/control/test_elasticache_operations.py |
| `DeleteUserGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `ModifyUserGroup` | — | not yet | tests/control/test_elasticache_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_elasticache_operations.py |
| `AddTagsToResource` | — | not yet | tests/control/test_elasticache_operations.py |
| `RemoveTagsFromResource` | — | not yet | tests/control/test_elasticache_operations.py |
| `CreateSnapshot` | — | not yet | tests/control/test_elasticache_operations.py |
| `DeleteSnapshot` | — | not yet | tests/control/test_elasticache_operations.py |
| `DescribeSnapshots` | — | not yet | tests/control/test_elasticache_operations.py |
| `CreateServerlessCache` | — | not yet | tests/control/test_elasticache_operations.py |
| `DescribeServerlessCaches` | — | not yet | tests/control/test_elasticache_operations.py |
| `ModifyServerlessCache` | — | not yet | tests/control/test_elasticache_operations.py |
| `DeleteServerlessCache` | — | not yet | tests/control/test_elasticache_operations.py |
| `DescribeEvents` | — | not yet | tests/control/test_elasticache_operations.py |

<!-- coverage:end -->
