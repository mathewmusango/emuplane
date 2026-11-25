---
sidebar_position: 11
title: Step Functions coverage
---

Every Step Functions operation the emulator advertises, and what Emuplane does
with it. The console lists, creates and deletes state machines; executions,
history, activities, callbacks, tags and `TestState` are reachable over the wire
and are exercised by the API tests.

The table is generated from the emulator's own operation list; the console column
names the page or API explorer entry that reaches an operation, and a row under
*Emuplane test* names the test that exercises it. A blocked operation names the
dependant it is waiting on.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **24**
- Console actions (`/api/exec`, the create page): **3**
- Operations with an emuplane test: **24**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **3**
- Operations that are not console actions: **21**
- GET operations (Get/List/Head/Describe) shown in the console: **1** of **10**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **24** · Console actions: **3**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateStateMachine` | create-state-machine | Step Functions page › Create state machine | tests/control/test_stepfunctions_operations.py |
| `DeleteStateMachine` | delete-state-machine | Step Functions page › Delete state machine | tests/control/test_stepfunctions_operations.py |
| `DescribeStateMachine` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `UpdateStateMachine` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `ListStateMachines` | list-state-machines | Step Functions page › List state machines | tests/control/test_stepfunctions_operations.py |
| `StartExecution` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `StartSyncExecution` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `StopExecution` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `DescribeExecution` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `DescribeStateMachineForExecution` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `ListExecutions` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `GetExecutionHistory` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `SendTaskSuccess` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `SendTaskFailure` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `SendTaskHeartbeat` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `CreateActivity` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `DeleteActivity` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `DescribeActivity` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `ListActivities` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `GetActivityTask` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `TestState` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `TagResource` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `UntagResource` | — | not a console action | tests/control/test_stepfunctions_operations.py |
| `ListTagsForResource` | — | not a console action | tests/control/test_stepfunctions_operations.py |

<!-- coverage:end -->
