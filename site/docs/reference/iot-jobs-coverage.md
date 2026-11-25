---
sidebar_position: 72
title: IoT Jobs coverage
---

Every AWS IoT Jobs operation the emulator advertises, and what Emuplane does with it.
The row names **16 control-plane operations** in the `iot` scope and **4 device
data-plane operations** in `iot-jobs-data`; both planes share the `iot` module's job
store. There is no console action.

`DescribeJobExecution` exists on **both planes**, so it appears under each heading and
the total counts it twice, as the README row does. A job targets a thing, which is
created first; a new job materializes each target's execution as `QUEUED`, and the
device plane starts and reports it. Documents are JSON strings, and a job template is
a record a job may copy its document and configuration from. Delete actions create
their own job or template and remove it.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **20**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **20**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **10**
- Operations with no emuplane test: **0**



## Control plane (`iot`)


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateJob` | — | — | tests/control/test_iot_jobs_operations.py |
| `UpdateJob` | — | — | tests/control/test_iot_jobs_operations.py |
| `DescribeJob` | — | — | tests/control/test_iot_jobs_operations.py |
| `ListJobs` | — | — | tests/control/test_iot_jobs_operations.py |
| `GetJobDocument` | — | — | tests/control/test_iot_jobs_operations.py |
| `CancelJob` | — | — | tests/control/test_iot_jobs_operations.py |
| `DeleteJob` | — | — | tests/control/test_iot_jobs_operations.py |
| `ListJobExecutionsForThing` | — | — | tests/control/test_iot_jobs_operations.py |
| `ListJobExecutionsForJob` | — | — | tests/control/test_iot_jobs_operations.py |
| `DescribeJobExecution` | — | — | tests/control/test_iot_jobs_operations.py (control plane and device plane) |
| `CancelJobExecution` | — | — | tests/control/test_iot_jobs_operations.py |
| `DeleteJobExecution` | — | — | tests/control/test_iot_jobs_operations.py |
| `CreateJobTemplate` | — | — | tests/control/test_iot_jobs_operations.py |
| `DescribeJobTemplate` | — | — | tests/control/test_iot_jobs_operations.py |
| `ListJobTemplates` | — | — | tests/control/test_iot_jobs_operations.py |
| `DeleteJobTemplate` | — | — | tests/control/test_iot_jobs_operations.py |


## Device data plane (`iot-jobs-data`)


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `GetPendingJobExecutions` | — | — | tests/control/test_iot_jobs_operations.py |
| `StartNextPendingJobExecution` | — | — | tests/control/test_iot_jobs_operations.py |
| `DescribeJobExecution` | — | — | tests/control/test_iot_jobs_operations.py (control plane and device plane) |
| `UpdateJobExecution` | — | — | tests/control/test_iot_jobs_operations.py |


## GET operations



- [ ] `DescribeJob` — not shown
- [ ] `ListJobs` — not shown
- [ ] `GetJobDocument` — not shown
- [ ] `ListJobExecutionsForThing` — not shown
- [ ] `ListJobExecutionsForJob` — not shown
- [ ] `DescribeJobExecution` — not shown
- [ ] `DescribeJobTemplate` — not shown
- [ ] `ListJobTemplates` — not shown
- [ ] `GetPendingJobExecutions` — not shown
- [ ] `DescribeJobExecution` — not shown

<!-- coverage:end -->
