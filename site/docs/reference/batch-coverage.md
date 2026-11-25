---
sidebar_position: 51
title: AWS Batch coverage
---

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **10**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **10**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **5**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **10** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateComputeEnvironment` | — | not yet | tests/control/test_batch_operations.py |
| `UpdateComputeEnvironment` | — | not yet | tests/control/test_batch_operations.py |
| `DescribeComputeEnvironments` | — | not yet | tests/control/test_batch_operations.py |
| `CreateJobQueue` | — | not yet | tests/control/test_batch_operations.py |
| `DescribeJobQueues` | — | not yet | tests/control/test_batch_operations.py |
| `RegisterJobDefinition` | — | not yet | tests/control/test_batch_operations.py |
| `DescribeJobDefinitions` | — | not yet | tests/control/test_batch_operations.py |
| `SubmitJob` | — | not yet | tests/control/test_batch_operations.py |
| `DescribeJobs` | — | not yet | tests/control/test_batch_operations.py |
| `ListJobs` | — | not yet | tests/control/test_batch_operations.py |

<!-- coverage:end -->
