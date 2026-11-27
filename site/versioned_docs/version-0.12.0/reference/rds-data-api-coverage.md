---
sidebar_position: 55
title: RDS Data API coverage
---

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **5**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **5**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **0**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **5** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `ExecuteStatement` | — | not yet | tests/control/test_rds_data_api_operations.py |
| `BatchExecuteStatement` | — | not yet | tests/control/test_rds_data_api_live_operations.py |
| `BeginTransaction` | — | not yet | tests/control/test_rds_data_api_live_operations.py |
| `CommitTransaction` | — | not yet | tests/control/test_rds_data_api_live_operations.py |
| `RollbackTransaction` | — | not yet | tests/control/test_rds_data_api_live_operations.py |

<!-- coverage:end -->
