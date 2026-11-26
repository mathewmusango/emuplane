---
sidebar_position: 44
title: Cloud Control API coverage
---

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **8**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **8**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **4**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **8** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateResource` | — | not yet | tests/control/test_cloudcontrol_operations.py |
| `GetResource` | — | not yet | tests/control/test_cloudcontrol_operations.py |
| `UpdateResource` | — | not yet | tests/control/test_cloudcontrol_operations.py |
| `DeleteResource` | — | not yet | tests/control/test_cloudcontrol_operations.py |
| `ListResources` | — | not yet | tests/control/test_cloudcontrol_operations.py |
| `ListResourceRequests` | — | not yet | tests/control/test_cloudcontrol_operations.py |
| `GetResourceRequestStatus` | — | not yet | tests/control/test_cloudcontrol_operations.py |
| `CancelResourceRequest` | — | not yet | tests/control/test_cloudcontrol_operations.py |

<!-- coverage:end -->
