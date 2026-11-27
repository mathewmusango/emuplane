---
sidebar_position: 46
title: AWS Budgets coverage
---

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **16**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **16**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **5**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **16** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateBudget` | — | not yet | tests/control/test_budgets_operations.py |
| `DescribeBudget` | — | not yet | tests/control/test_budgets_operations.py |
| `DescribeBudgets` | — | not yet | tests/control/test_budgets_operations.py |
| `UpdateBudget` | — | not yet | tests/control/test_budgets_operations.py |
| `DeleteBudget` | — | not yet | tests/control/test_budgets_operations.py |
| `CreateNotification` | — | not yet | tests/control/test_budgets_operations.py |
| `UpdateNotification` | — | not yet | tests/control/test_budgets_operations.py |
| `DeleteNotification` | — | not yet | tests/control/test_budgets_operations.py |
| `DescribeNotificationsForBudget` | — | not yet | tests/control/test_budgets_operations.py |
| `CreateSubscriber` | — | not yet | tests/control/test_budgets_operations.py |
| `UpdateSubscriber` | — | not yet | tests/control/test_budgets_operations.py |
| `DeleteSubscriber` | — | not yet | tests/control/test_budgets_operations.py |
| `DescribeSubscribersForNotification` | — | not yet | tests/control/test_budgets_operations.py |
| `TagResource` | — | not yet | tests/control/test_budgets_operations.py |
| `UntagResource` | — | not yet | tests/control/test_budgets_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_budgets_operations.py |

<!-- coverage:end -->
