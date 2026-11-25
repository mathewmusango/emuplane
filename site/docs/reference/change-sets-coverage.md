---
sidebar_position: 36
title: Change Sets coverage
---

Every CloudFormation change-set operation the emulator advertises, and what
Emuplane does with it. A change set previews the difference a stack update would
make; it is created, described, listed, executed or deleted over the Query
protocol. There is no console action.

A change set with no changes ends `FAILED` and cannot be executed, as on AWS. An
`UPDATE` set is created against the stack it would change; a `CREATE` set creates
a placeholder stack in `REVIEW_IN_PROGRESS` until it is executed.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **5**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **5**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **2**
- Operations with no emuplane test: **0**

- Group: **CloudFormation** · operations: **5** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateChangeSet` | — | not yet | tests/control/test_change_sets_operations.py |
| `DescribeChangeSet` | — | not yet | tests/control/test_change_sets_operations.py |
| `ExecuteChangeSet` | — | not yet | tests/control/test_change_sets_operations.py |
| `DeleteChangeSet` | — | not yet | tests/control/test_change_sets_operations.py |
| `ListChangeSets` | — | not yet | tests/control/test_change_sets_operations.py |

<!-- coverage:end -->
