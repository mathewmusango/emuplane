---
sidebar_position: 53
title: ECS Task Metadata V4 coverage
---

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **4**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **4**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **0**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **4** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `GET /v4/<token>` | — | not yet | tests/control/test_ecs_task_metadata_operations.py |
| `GET /v4/<token>/task` | — | not yet | tests/control/test_ecs_task_metadata_operations.py |
| `GET /v4/<token>/stats` | — | not yet | tests/control/test_ecs_task_metadata_operations.py |
| `GET /v4/<token>/task/stats` | — | not yet | tests/control/test_ecs_task_metadata_operations.py |

<!-- coverage:end -->
