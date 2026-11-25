---
sidebar_position: 60
title: Amazon EMR coverage
---

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **22**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **22**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **8**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **22** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `RunJobFlow` | — | not yet | tests/control/test_emr_operations.py |
| `DescribeCluster` | — | not yet | tests/control/test_emr_operations.py |
| `ListClusters` | — | not yet | tests/control/test_emr_operations.py |
| `TerminateJobFlows` | — | not yet | tests/control/test_emr_operations.py |
| `ModifyCluster` | — | not yet | tests/control/test_emr_operations.py |
| `SetTerminationProtection` | — | not yet | tests/control/test_emr_operations.py |
| `SetVisibleToAllUsers` | — | not yet | tests/control/test_emr_operations.py |
| `AddJobFlowSteps` | — | not yet | tests/control/test_emr_operations.py |
| `DescribeStep` | — | not yet | tests/control/test_emr_operations.py |
| `ListSteps` | — | not yet | tests/control/test_emr_operations.py |
| `CancelSteps` | — | not yet | tests/control/test_emr_operations.py |
| `AddInstanceFleet` | — | not yet | tests/control/test_emr_operations.py |
| `ListInstanceFleets` | — | not yet | tests/control/test_emr_operations.py |
| `ModifyInstanceFleet` | — | not yet | tests/control/test_emr_operations.py |
| `AddInstanceGroups` | — | not yet | tests/control/test_emr_operations.py |
| `ListInstanceGroups` | — | not yet | tests/control/test_emr_operations.py |
| `ModifyInstanceGroups` | — | not yet | tests/control/test_emr_operations.py |
| `ListBootstrapActions` | — | not yet | tests/control/test_emr_operations.py |
| `AddTags` | — | not yet | tests/control/test_emr_operations.py |
| `RemoveTags` | — | not yet | tests/control/test_emr_operations.py |
| `GetBlockPublicAccessConfiguration` | — | not yet | tests/control/test_emr_operations.py |
| `PutBlockPublicAccessConfiguration` | — | not yet | tests/control/test_emr_operations.py |

<!-- coverage:end -->
