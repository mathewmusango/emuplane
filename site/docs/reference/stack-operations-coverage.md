---
sidebar_position: 27
title: Stack Operations coverage
---

Every CloudFormation stack operation the emulator advertises, and what Emuplane
does with it. There is no console action: stacks are created, read, updated,
rolled back and deleted over the wire. Stacks deploy asynchronously, so the
in-process stand-in cancels the deploy before completion and the live sweep
proves the completed lifecycle; the operations themselves are all covered.

The table is generated from the operation list; every row names the test that
exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **12**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **12**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **7**
- Operations with no emuplane test: **0**

- Group: **CloudFormation** · operations: **12** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateStack` | — | not yet | tests/control/test_cloudformation_operations.py |
| `UpdateStack` | — | not yet | tests/control/test_cloudformation_operations.py |
| `DeleteStack` | — | not yet | tests/control/test_cloudformation_operations.py |
| `DescribeStacks` | — | not yet | tests/control/test_cloudformation_operations.py |
| `ListStacks` | — | not yet | tests/control/test_cloudformation_operations.py |
| `DescribeStackEvents` | — | not yet | tests/control/test_cloudformation_operations.py |
| `DescribeStackResource` | — | not yet | tests/control/test_cloudformation_operations.py |
| `DescribeStackResources` | — | not yet | tests/control/test_cloudformation_operations.py |
| `GetTemplate` | — | not yet | tests/control/test_cloudformation_operations.py |
| `ValidateTemplate` | — | not yet | tests/control/test_cloudformation_operations.py |
| `GetTemplateSummary` | — | not yet | tests/control/test_cloudformation_operations.py |
| `RollbackStack` | — | not yet | tests/control/test_cloudformation_operations.py |

<!-- coverage:end -->
