---
sidebar_position: 54
title: ECS Container Credentials coverage
---

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **1**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **1**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **0**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **1** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `GET /v2/credentials/<uuid>` | — | not yet | tests/control/test_ecs_container_credentials_operations.py |

<!-- coverage:end -->
