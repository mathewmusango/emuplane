---
sidebar_position: 28
title: StackSets coverage
---

The StackSet read operations the emulator advertises, and what Emuplane does
with them. The README row describes the set created by an
`AWS::CloudFormation::StackSet` resource rather than listing an operation set,
so the universe here is the two operations it names.

The table is generated from the operation list; every row names the test that
exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **2**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **2**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **2**
- Operations with no emuplane test: **0**

- Group: **CloudFormation** · operations: **2** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `DescribeStackSet` | — | not yet | tests/control/test_cloudformation_operations.py |
| `ListStackInstances` | — | not yet | tests/control/test_cloudformation_operations.py |

<!-- coverage:end -->
