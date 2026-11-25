---
sidebar_position: 75
title: ECS coverage
---

Every ECS operation the emulator advertises, and what Emuplane does with it.
Requests are JSON with an `X-Amz-Target` naming the action, signed with the `ecs`
credential scope. There is no console action.

With Docker `RunTask` starts real containers and a task reports `PROVISIONING` first;
without it — the usual case, and the one the tests run against — a task is recorded
`RUNNING` at once, so nothing here pulls an image. A stable cluster, task definition
and service carry the read and update rows; delete actions and lifecycle tests make
their own. `UpdateTaskProtection` only accepts a task that belongs to a service, and
the four agent operations are acknowledgments.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **47**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **47**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **18**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **47** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateCluster` | — | not yet | tests/control/test_ecs_operations.py |
| `DeleteCluster` | — | not yet | tests/control/test_ecs_operations.py |
| `DescribeClusters` | — | not yet | tests/control/test_ecs_operations.py |
| `ListClusters` | — | not yet | tests/control/test_ecs_operations.py |
| `UpdateCluster` | — | not yet | tests/control/test_ecs_operations.py |
| `UpdateClusterSettings` | — | not yet | tests/control/test_ecs_operations.py |
| `PutClusterCapacityProviders` | — | not yet | tests/control/test_ecs_operations.py |
| `RegisterTaskDefinition` | — | not yet | tests/control/test_ecs_operations.py |
| `DeregisterTaskDefinition` | — | not yet | tests/control/test_ecs_operations.py |
| `DescribeTaskDefinition` | — | not yet | tests/control/test_ecs_operations.py |
| `ListTaskDefinitions` | — | not yet | tests/control/test_ecs_operations.py |
| `ListTaskDefinitionFamilies` | — | not yet | tests/control/test_ecs_operations.py |
| `DeleteTaskDefinitions` | — | not yet | tests/control/test_ecs_operations.py |
| `CreateService` | — | not yet | tests/control/test_ecs_operations.py |
| `DeleteService` | — | not yet | tests/control/test_ecs_operations.py |
| `DescribeServices` | — | not yet | tests/control/test_ecs_operations.py |
| `UpdateService` | — | not yet | tests/control/test_ecs_operations.py |
| `ListServices` | — | not yet | tests/control/test_ecs_operations.py |
| `ListServicesByNamespace` | — | not yet | tests/control/test_ecs_operations.py |
| `RunTask` | — | not yet | tests/control/test_ecs_operations.py |
| `StopTask` | — | not yet | tests/control/test_ecs_operations.py |
| `DescribeTasks` | — | not yet | tests/control/test_ecs_operations.py |
| `ListTasks` | — | not yet | tests/control/test_ecs_operations.py |
| `ExecuteCommand` | — | not yet | tests/control/test_ecs_operations.py |
| `UpdateTaskProtection` | — | not yet | tests/control/test_ecs_operations.py |
| `GetTaskProtection` | — | not yet | tests/control/test_ecs_operations.py |
| `CreateCapacityProvider` | — | not yet | tests/control/test_ecs_operations.py |
| `UpdateCapacityProvider` | — | not yet | tests/control/test_ecs_operations.py |
| `DeleteCapacityProvider` | — | not yet | tests/control/test_ecs_operations.py |
| `DescribeCapacityProviders` | — | not yet | tests/control/test_ecs_operations.py |
| `TagResource` | — | not yet | tests/control/test_ecs_operations.py |
| `UntagResource` | — | not yet | tests/control/test_ecs_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_ecs_operations.py |
| `ListAccountSettings` | — | not yet | tests/control/test_ecs_operations.py |
| `PutAccountSetting` | — | not yet | tests/control/test_ecs_operations.py |
| `PutAccountSettingDefault` | — | not yet | tests/control/test_ecs_operations.py |
| `DeleteAccountSetting` | — | not yet | tests/control/test_ecs_operations.py |
| `PutAttributes` | — | not yet | tests/control/test_ecs_operations.py |
| `DeleteAttributes` | — | not yet | tests/control/test_ecs_operations.py |
| `ListAttributes` | — | not yet | tests/control/test_ecs_operations.py |
| `DescribeServiceDeployments` | — | not yet | tests/control/test_ecs_operations.py |
| `ListServiceDeployments` | — | not yet | tests/control/test_ecs_operations.py |
| `DescribeServiceRevisions` | — | not yet | tests/control/test_ecs_operations.py |
| `SubmitTaskStateChange` | — | not yet | tests/control/test_ecs_operations.py |
| `SubmitContainerStateChange` | — | not yet | tests/control/test_ecs_operations.py |
| `SubmitAttachmentStateChanges` | — | not yet | tests/control/test_ecs_operations.py |
| `DiscoverPollEndpoint` | — | not yet | tests/control/test_ecs_operations.py |

<!-- coverage:end -->
