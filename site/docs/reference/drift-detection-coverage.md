---
sidebar_position: 38
title: Drift Detection coverage
---

Every CloudFormation drift operation the emulator advertises, and what Emuplane
does with it. Detection completes synchronously: it compares the properties the
template set with the service's current record, and records `DriftInformation` on
the stack and on each checked resource. There is no console action.

The README row also describes property-level drift for a set of resource types
and assigns `NOT_CHECKED` to every other type; those are behaviour notes rather
than operations, so this page lists only the four callable operations. A resource
type that does not support drift is refused by `DetectStackResourceDrift` and is
absent from `DescribeStackResourceDrifts`, which lists only what was checked.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **4**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **4**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **2**
- Operations with no emuplane test: **0**

- Group: **CloudFormation** · operations: **4** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `DetectStackDrift` | — | not yet | tests/control/test_drift_detection_operations.py |
| `DescribeStackDriftDetectionStatus` | — | not yet | tests/control/test_drift_detection_operations.py |
| `DetectStackResourceDrift` | — | not yet | tests/control/test_drift_detection_operations.py |
| `DescribeStackResourceDrifts` | — | not yet | tests/control/test_drift_detection_operations.py |

<!-- coverage:end -->
