---
sidebar_position: 59
title: Amazon ECR coverage
---

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **26**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **26**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **9**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **26** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateRepository` | — | not yet | tests/control/test_ecr_operations.py |
| `DescribeRepositories` | — | not yet | tests/control/test_ecr_operations.py |
| `DeleteRepository` | — | not yet | tests/control/test_ecr_operations.py |
| `ListImages` | — | not yet | tests/control/test_ecr_operations.py |
| `DescribeImages` | — | not yet | tests/control/test_ecr_operations.py |
| `PutImage` | — | not yet | tests/control/test_ecr_operations.py |
| `BatchGetImage` | — | not yet | tests/control/test_ecr_operations.py |
| `BatchDeleteImage` | — | not yet | tests/control/test_ecr_operations.py |
| `GetAuthorizationToken` | — | not yet | tests/control/test_ecr_operations.py |
| `GetRepositoryPolicy` | — | not yet | tests/control/test_ecr_operations.py |
| `SetRepositoryPolicy` | — | not yet | tests/control/test_ecr_operations.py |
| `DeleteRepositoryPolicy` | — | not yet | tests/control/test_ecr_operations.py |
| `PutLifecyclePolicy` | — | not yet | tests/control/test_ecr_operations.py |
| `GetLifecyclePolicy` | — | not yet | tests/control/test_ecr_operations.py |
| `DeleteLifecyclePolicy` | — | not yet | tests/control/test_ecr_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_ecr_operations.py |
| `TagResource` | — | not yet | tests/control/test_ecr_operations.py |
| `UntagResource` | — | not yet | tests/control/test_ecr_operations.py |
| `PutImageTagMutability` | — | not yet | tests/control/test_ecr_operations.py |
| `PutImageScanningConfiguration` | — | not yet | tests/control/test_ecr_operations.py |
| `DescribeRegistry` | — | not yet | tests/control/test_ecr_operations.py |
| `GetDownloadUrlForLayer` | — | not yet | tests/control/test_ecr_operations.py |
| `BatchCheckLayerAvailability` | — | not yet | tests/control/test_ecr_operations.py |
| `InitiateLayerUpload` | — | not yet | tests/control/test_ecr_operations.py |
| `UploadLayerPart` | — | not yet | tests/control/test_ecr_operations.py |
| `CompleteLayerUpload` | — | not yet | tests/control/test_ecr_operations.py |

<!-- coverage:end -->
