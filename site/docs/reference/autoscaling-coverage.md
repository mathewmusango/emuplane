---
sidebar_position: 63
title: Amazon EC2 Auto Scaling coverage
---

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **23**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **23**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **7**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **23** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateAutoScalingGroup` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DescribeAutoScalingGroups` | — | not yet | tests/control/test_autoscaling_operations.py |
| `UpdateAutoScalingGroup` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DeleteAutoScalingGroup` | — | not yet | tests/control/test_autoscaling_operations.py |
| `SetDesiredCapacity` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DescribeAutoScalingInstances` | — | not yet | tests/control/test_autoscaling_operations.py |
| `CreateLaunchConfiguration` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DescribeLaunchConfigurations` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DeleteLaunchConfiguration` | — | not yet | tests/control/test_autoscaling_operations.py |
| `PutScalingPolicy` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DescribePolicies` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DeletePolicy` | — | not yet | tests/control/test_autoscaling_operations.py |
| `PutLifecycleHook` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DescribeLifecycleHooks` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DeleteLifecycleHook` | — | not yet | tests/control/test_autoscaling_operations.py |
| `CompleteLifecycleAction` | — | not yet | tests/control/test_autoscaling_operations.py |
| `RecordLifecycleActionHeartbeat` | — | not yet | tests/control/test_autoscaling_operations.py |
| `PutScheduledUpdateGroupAction` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DescribeScheduledActions` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DeleteScheduledAction` | — | not yet | tests/control/test_autoscaling_operations.py |
| `CreateOrUpdateTags` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DescribeTags` | — | not yet | tests/control/test_autoscaling_operations.py |
| `DeleteTags` | — | not yet | tests/control/test_autoscaling_operations.py |

<!-- coverage:end -->
