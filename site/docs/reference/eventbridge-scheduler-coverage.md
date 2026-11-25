---
sidebar_position: 49
title: EventBridge Scheduler coverage
---

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **12**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **12**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **5**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **12** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateSchedule` | — | not yet | tests/control/test_scheduler_operations.py |
| `GetSchedule` | — | not yet | tests/control/test_scheduler_operations.py |
| `UpdateSchedule` | — | not yet | tests/control/test_scheduler_operations.py |
| `DeleteSchedule` | — | not yet | tests/control/test_scheduler_operations.py |
| `ListSchedules` | — | not yet | tests/control/test_scheduler_operations.py |
| `CreateScheduleGroup` | — | not yet | tests/control/test_scheduler_operations.py |
| `GetScheduleGroup` | — | not yet | tests/control/test_scheduler_operations.py |
| `DeleteScheduleGroup` | — | not yet | tests/control/test_scheduler_operations.py |
| `ListScheduleGroups` | — | not yet | tests/control/test_scheduler_operations.py |
| `TagResource` | — | not yet | tests/control/test_scheduler_operations.py |
| `UntagResource` | — | not yet | tests/control/test_scheduler_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_scheduler_operations.py |

<!-- coverage:end -->
