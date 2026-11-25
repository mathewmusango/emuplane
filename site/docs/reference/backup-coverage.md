---
sidebar_position: 64
title: AWS Backup coverage
---

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **21**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **21**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **10**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **21** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateBackupVault` | — | not yet | tests/control/test_backup_operations.py |
| `DescribeBackupVault` | — | not yet | tests/control/test_backup_operations.py |
| `DeleteBackupVault` | — | not yet | tests/control/test_backup_operations.py |
| `ListBackupVaults` | — | not yet | tests/control/test_backup_operations.py |
| `CreateBackupPlan` | — | not yet | tests/control/test_backup_operations.py |
| `GetBackupPlan` | — | not yet | tests/control/test_backup_operations.py |
| `UpdateBackupPlan` | — | not yet | tests/control/test_backup_operations.py |
| `DeleteBackupPlan` | — | not yet | tests/control/test_backup_operations.py |
| `ListBackupPlans` | — | not yet | tests/control/test_backup_operations.py |
| `ListBackupPlanVersions` | — | not yet | tests/control/test_backup_operations.py |
| `CreateBackupSelection` | — | not yet | tests/control/test_backup_operations.py |
| `GetBackupSelection` | — | not yet | tests/control/test_backup_operations.py |
| `DeleteBackupSelection` | — | not yet | tests/control/test_backup_operations.py |
| `ListBackupSelections` | — | not yet | tests/control/test_backup_operations.py |
| `StartBackupJob` | — | not yet | tests/control/test_backup_operations.py |
| `StopBackupJob` | — | not yet | tests/control/test_backup_operations.py |
| `DescribeBackupJob` | — | not yet | tests/control/test_backup_operations.py |
| `ListBackupJobs` | — | not yet | tests/control/test_backup_operations.py |
| `TagResource` | — | not yet | tests/control/test_backup_operations.py |
| `UntagResource` | — | not yet | tests/control/test_backup_operations.py |
| `ListTags` | — | not yet | tests/control/test_backup_operations.py |

<!-- coverage:end -->
