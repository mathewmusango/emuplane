---
sidebar_position: 56
title: AWS CloudTrail coverage
---

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **15**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **15**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **6**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **15** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `LookupEvents` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `CreateTrail` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `DeleteTrail` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `GetTrail` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `DescribeTrails` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `ListTrails` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `UpdateTrail` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `GetTrailStatus` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `StartLogging` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `StopLogging` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `PutEventSelectors` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `GetEventSelectors` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `AddTags` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `ListTags` | — | not yet | tests/control/test_cloudtrail_operations.py |
| `RemoveTags` | — | not yet | tests/control/test_cloudtrail_operations.py |

<!-- coverage:end -->
