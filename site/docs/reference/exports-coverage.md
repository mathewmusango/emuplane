---
sidebar_position: 37
title: Exports coverage
---

The one CloudFormation export operation the emulator advertises, and what Emuplane
does with it: `ListExports` reads the cross-stack values a stack's `Outputs`
publish through `Export.Name` and that another stack consumes with
`Fn::ImportValue`. There is no console action.

The README row also names `Fn::ImportValue`, which is a template function rather
than an API operation, so it is not counted here.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **1**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **1**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **1**
- Operations with no emuplane test: **0**

- Group: **CloudFormation** · operations: **1** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `ListExports` | — | not yet | tests/control/test_exports_operations.py |

<!-- coverage:end -->
