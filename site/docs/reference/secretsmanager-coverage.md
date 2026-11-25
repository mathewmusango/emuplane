---
sidebar_position: 13
title: Secrets Manager coverage
---

Every Secrets Manager operation the emulator advertises, and what Emuplane does
with it. The console lists, creates, puts a value and deletes; updates, versions,
restore, rotation, replication, tags and resource policies are reachable over the
wire and are exercised by the API tests.

The table is generated from the emulator's own operation list; the console column
names the page or API explorer entry that reaches an operation, and a row under
*Emuplane test* names the test that exercises it. A blocked operation names the
dependant it is waiting on.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **21**
- Console actions (`/api/exec`, the create page): **4**
- Operations with an emuplane test: **21**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **4**
- Operations that are not console actions: **17**
- GET operations (Get/List/Head/Describe) shown in the console: **1** of **6**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **21** · Console actions: **4**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateSecret` | create-secret | Secrets Manager page › Create secret | tests/control/test_secretsmanager_operations.py |
| `GetSecretValue` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `ListSecrets` | list-secrets | Secrets Manager page › List secrets | tests/control/test_secretsmanager_operations.py |
| `DeleteSecret` | delete-secret | Secrets Manager page › Delete secret | tests/control/test_secretsmanager_operations.py |
| `UpdateSecret` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `DescribeSecret` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `PutSecretValue` | put-secret-value | Secrets Manager page › Put value | tests/control/test_secretsmanager_operations.py |
| `UpdateSecretVersionStage` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `RestoreSecret` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `RotateSecret` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `GetRandomPassword` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `ListSecretVersionIds` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `ReplicateSecretToRegions` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `RemoveRegionsFromReplication` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `StopReplicationToReplica` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `TagResource` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `UntagResource` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `PutResourcePolicy` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `GetResourcePolicy` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `DeleteResourcePolicy` | — | not a console action | tests/control/test_secretsmanager_operations.py |
| `ValidateResourcePolicy` | — | not a console action | tests/control/test_secretsmanager_operations.py |

<!-- coverage:end -->
