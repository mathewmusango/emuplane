---
sidebar_position: 48
title: CodeBuild coverage
---

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **11**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **11**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **3**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **11** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateProject` | — | not yet | tests/control/test_codebuild_operations.py |
| `BatchGetProjects` | — | not yet | tests/control/test_codebuild_operations.py |
| `ListProjects` | — | not yet | tests/control/test_codebuild_operations.py |
| `UpdateProject` | — | not yet | tests/control/test_codebuild_operations.py |
| `DeleteProject` | — | not yet | tests/control/test_codebuild_operations.py |
| `StartBuild` | — | not yet | tests/control/test_codebuild_operations.py |
| `BatchGetBuilds` | — | not yet | tests/control/test_codebuild_operations.py |
| `StopBuild` | — | not yet | tests/control/test_codebuild_operations.py |
| `ListBuilds` | — | not yet | tests/control/test_codebuild_operations.py |
| `ListBuildsForProject` | — | not yet | tests/control/test_codebuild_operations.py |
| `BatchDeleteBuilds` | — | not yet | tests/control/test_codebuild_operations.py |

<!-- coverage:end -->
