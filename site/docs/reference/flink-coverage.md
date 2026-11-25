---
sidebar_position: 81
title: Managed Service for Apache Flink coverage
---

Every Managed Service for Apache Flink operation the emulator advertises, and what
Emuplane does with it. The service is JSON 1.1 under the `kinesisanalytics`
credential scope with the `KinesisAnalytics_20180523` target prefix, and there is no
console action: applications, snapshots, logging options and tags are driven over
the wire.

The emulator is a control plane for `FLINK-*` runtimes. SQL applications and Studio
notebooks are not implemented, so `CreateApplication` refuses any runtime that is
not a Flink runtime. Job execution needs Docker and an image for the runtime; without
one the application stays a record, and a transitional status settles on the next
read (`STARTING` and `UPDATING` become `RUNNING`, `STOPPING` and `FORCE_STOPPING`
become `READY`). An application restored after a restart comes back `READY`.

The table is generated from the emulator's own operation list; every row names the
test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **15**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **15**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **4**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **15** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateApplication` | — | not yet | tests/control/test_flink_operations.py |
| `DescribeApplication` | — | not yet | tests/control/test_flink_operations.py |
| `UpdateApplication` | — | not yet | tests/control/test_flink_operations.py |
| `DeleteApplication` | — | not yet | tests/control/test_flink_operations.py |
| `StartApplication` | — | not yet | tests/control/test_flink_operations.py |
| `StopApplication` | — | not yet | tests/control/test_flink_operations.py |
| `CreateApplicationSnapshot` | — | not yet | tests/control/test_flink_operations.py |
| `ListApplicationSnapshots` | — | not yet | tests/control/test_flink_operations.py |
| `DescribeApplicationSnapshot` | — | not yet | tests/control/test_flink_operations.py |
| `DeleteApplicationSnapshot` | — | not yet | tests/control/test_flink_operations.py |
| `AddApplicationCloudWatchLoggingOption` | — | not yet | tests/control/test_flink_operations.py |
| `DeleteApplicationCloudWatchLoggingOption` | — | not yet | tests/control/test_flink_operations.py |
| `TagResource` | — | not yet | tests/control/test_flink_operations.py |
| `UntagResource` | — | not yet | tests/control/test_flink_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_flink_operations.py |

<!-- coverage:end -->
