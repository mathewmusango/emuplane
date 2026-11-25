---
sidebar_position: 15
title: SSM Parameter Store coverage
---

Every Parameter Store operation the emulator advertises, and what Emuplane does
with it. The console describes, puts, gets and deletes parameters; hierarchy,
history, labels, tags, service settings, documents and automations are reachable
over the wire and are exercised by the API tests.

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
- Console actions (`/api/exec`, the create page): **4**
- Operations with an emuplane test: **24**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **4**
- Operations that are not console actions: **20**
- GET operations (Get/List/Head/Describe) shown in the console: **2** of **12**
- Operations with no emuplane test: **0**

- Group: **Extended** · operations: **24** · Console actions: **4**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `PutParameter` | put-parameter | SSM Parameter Store page › Put parameter | tests/control/test_ssm_operations.py |
| `GetParameter` | get-parameter | SSM Parameter Store page › Get parameter | tests/control/test_ssm_operations.py |
| `GetParameters` | — | not a console action | tests/control/test_ssm_operations.py |
| `GetParametersByPath` | — | not a console action | tests/control/test_ssm_operations.py |
| `DeleteParameter` | delete-parameter | SSM Parameter Store page › Delete parameter | tests/control/test_ssm_operations.py |
| `DeleteParameters` | — | not a console action | tests/control/test_ssm_operations.py |
| `DescribeParameters` | describe-parameters | SSM Parameter Store page › List parameters | tests/control/test_ssm_operations.py |
| `GetParameterHistory` | — | not a console action | tests/control/test_ssm_operations.py |
| `LabelParameterVersion` | — | not a console action | tests/control/test_ssm_operations.py |
| `AddTagsToResource` | — | not a console action | tests/control/test_ssm_operations.py |
| `RemoveTagsFromResource` | — | not a console action | tests/control/test_ssm_operations.py |
| `ListTagsForResource` | — | not a console action | tests/control/test_ssm_operations.py |
| `GetServiceSetting` | — | not a console action | tests/control/test_ssm_operations.py |
| `UpdateServiceSetting` | — | not a console action | tests/control/test_ssm_operations.py |
| `ResetServiceSetting` | — | not a console action | tests/control/test_ssm_operations.py |
| `CreateDocument` | — | not a console action | tests/control/test_ssm_operations.py |
| `DescribeDocument` | — | not a console action | tests/control/test_ssm_operations.py |
| `GetDocument` | — | not a console action | tests/control/test_ssm_operations.py |
| `ListDocuments` | — | not a console action | tests/control/test_ssm_operations.py |
| `DeleteDocument` | — | not a console action | tests/control/test_ssm_operations.py |
| `StartAutomationExecution` | — | not a console action | tests/control/test_ssm_operations.py |
| `GetAutomationExecution` | — | not a console action | tests/control/test_ssm_operations.py |
| `DescribeAutomationExecutions` | — | not a console action | tests/control/test_ssm_operations.py |
| `StopAutomationExecution` | — | not a console action | tests/control/test_ssm_operations.py |

<!-- coverage:end -->
