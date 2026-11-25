---
sidebar_position: 18
title: Amazon Location (trackers) coverage
---

Every Amazon Location tracker operation the emulator advertises, and what
Emuplane does with it. There is no console action: trackers and device positions
are driven over the wire (credential scope `geo`), and every advertised operation
is exercised by the API tests.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **9**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **9**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **4**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **9** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateTracker` | — | not yet | tests/control/test_location_operations.py |
| `DescribeTracker` | — | not yet | tests/control/test_location_operations.py |
| `UpdateTracker` | — | not yet | tests/control/test_location_operations.py |
| `ListTrackers` | — | not yet | tests/control/test_location_operations.py |
| `DeleteTracker` | — | not yet | tests/control/test_location_operations.py |
| `BatchUpdateDevicePosition` | — | not yet | tests/control/test_location_operations.py |
| `GetDevicePosition` | — | not yet | tests/control/test_location_operations.py |
| `BatchGetDevicePosition` | — | not yet | tests/control/test_location_operations.py |
| `GetDevicePositionHistory` | — | not yet | tests/control/test_location_operations.py |

<!-- coverage:end -->
