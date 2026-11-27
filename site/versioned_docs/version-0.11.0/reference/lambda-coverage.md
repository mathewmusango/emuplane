---
sidebar_position: 7
title: Lambda coverage
---

Every Lambda operation the emulator advertises, and what Emuplane does with it.
The console lists, inspects, invokes and deletes functions; versions, aliases,
layers, event sources, function URLs, concurrency and durable executions are
reachable over the wire and are exercised by the API tests.

The table is generated from the emulator's own operation list; the console column
names the page or API explorer entry that reaches an operation, and a row under
*Emuplane test* names the test that exercises it. A blocked operation names the
dependant it is waiting on.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **55**
- Console actions (`/api/exec`, the create page): **4**
- Operations with an emuplane test: **55**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **4**
- Operations that are not console actions: **51**
- GET operations (Get/List/Head/Describe) shown in the console: **2** of **23**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **55** · Console actions: **4**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateFunction` | — | not a console action | tests/control/test_lambda_operations.py |
| `DeleteFunction` | delete-function | Lambda page › Delete function | tests/control/test_lambda_operations.py |
| `GetFunction` | get-function | Lambda page › Get function | tests/control/test_lambda_operations.py |
| `GetFunctionConfiguration` | — | not a console action | tests/control/test_lambda_operations.py |
| `ListFunctions` | list-functions | Lambda page › List functions | tests/control/test_lambda_operations.py |
| `Invoke` | invoke-function | Lambda page › Invoke function | tests/control/test_lambda_operations.py |
| `UpdateFunctionCode` | — | not a console action | tests/control/test_lambda_operations.py |
| `UpdateFunctionConfiguration` | — | not a console action | tests/control/test_lambda_operations.py |
| `AddPermission` | — | not a console action | tests/control/test_lambda_operations.py |
| `RemovePermission` | — | not a console action | tests/control/test_lambda_operations.py |
| `GetPolicy` | — | not a console action | tests/control/test_lambda_operations.py |
| `ListVersionsByFunction` | — | not a console action | tests/control/test_lambda_operations.py |
| `PublishVersion` | — | not a console action | tests/control/test_lambda_operations.py |
| `CreateAlias` | — | not a console action | tests/control/test_lambda_operations.py |
| `GetAlias` | — | not a console action | tests/control/test_lambda_operations.py |
| `UpdateAlias` | — | not a console action | tests/control/test_lambda_operations.py |
| `DeleteAlias` | — | not a console action | tests/control/test_lambda_operations.py |
| `ListAliases` | — | not a console action | tests/control/test_lambda_operations.py |
| `TagResource` | — | not a console action | tests/control/test_lambda_operations.py |
| `UntagResource` | — | not a console action | tests/control/test_lambda_operations.py |
| `ListTags` | — | not a console action | tests/control/test_lambda_operations.py |
| `CreateEventSourceMapping` | — | not a console action | tests/control/test_lambda_operations.py |
| `DeleteEventSourceMapping` | — | not a console action | tests/control/test_lambda_operations.py |
| `GetEventSourceMapping` | — | not a console action | tests/control/test_lambda_operations.py |
| `ListEventSourceMappings` | — | not a console action | tests/control/test_lambda_operations.py |
| `UpdateEventSourceMapping` | — | not a console action | tests/control/test_lambda_operations.py |
| `CreateFunctionUrlConfig` | — | not a console action | tests/control/test_lambda_operations.py |
| `GetFunctionUrlConfig` | — | not a console action | tests/control/test_lambda_operations.py |
| `UpdateFunctionUrlConfig` | — | not a console action | tests/control/test_lambda_operations.py |
| `DeleteFunctionUrlConfig` | — | not a console action | tests/control/test_lambda_operations.py |
| `ListFunctionUrlConfigs` | — | not a console action | tests/control/test_lambda_operations.py |
| `PutFunctionConcurrency` | — | not a console action | tests/control/test_lambda_operations.py |
| `GetFunctionConcurrency` | — | not a console action | tests/control/test_lambda_operations.py |
| `DeleteFunctionConcurrency` | — | not a console action | tests/control/test_lambda_operations.py |
| `PutFunctionEventInvokeConfig` | — | not a console action | tests/control/test_lambda_operations.py |
| `GetFunctionEventInvokeConfig` | — | not a console action | tests/control/test_lambda_operations.py |
| `DeleteFunctionEventInvokeConfig` | — | not a console action | tests/control/test_lambda_operations.py |
| `PublishLayerVersion` | — | not a console action | tests/control/test_lambda_operations.py |
| `GetLayerVersion` | — | not a console action | tests/control/test_lambda_operations.py |
| `GetLayerVersionByArn` | — | not a console action | tests/control/test_lambda_operations.py |
| `ListLayerVersions` | — | not a console action | tests/control/test_lambda_operations.py |
| `DeleteLayerVersion` | — | not a console action | tests/control/test_lambda_operations.py |
| `ListLayers` | — | not a console action | tests/control/test_lambda_operations.py |
| `AddLayerVersionPermission` | — | not a console action | tests/control/test_lambda_operations.py |
| `RemoveLayerVersionPermission` | — | not a console action | tests/control/test_lambda_operations.py |
| `GetLayerVersionPolicy` | — | not a console action | tests/control/test_lambda_operations.py |
| `CheckpointDurableExecution` | — | not a console action | tests/control/test_lambda_operations.py |
| `GetDurableExecution` | — | not a console action | tests/control/test_lambda_operations.py |
| `GetDurableExecutionState` | — | not a console action | tests/control/test_lambda_operations.py |
| `GetDurableExecutionHistory` | — | not a console action | tests/control/test_lambda_operations.py |
| `ListDurableExecutionsByFunction` | — | not a console action | tests/control/test_lambda_operations.py |
| `StopDurableExecution` | — | not a console action | tests/control/test_lambda_operations.py |
| `SendDurableExecutionCallbackSuccess` | — | not a console action | tests/control/test_lambda_operations.py |
| `SendDurableExecutionCallbackFailure` | — | not a console action | tests/control/test_lambda_operations.py |
| `SendDurableExecutionCallbackHeartbeat` | — | not a console action | tests/control/test_lambda_operations.py |

<!-- coverage:end -->
