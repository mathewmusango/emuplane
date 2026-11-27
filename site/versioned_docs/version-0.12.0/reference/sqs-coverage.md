---
sidebar_position: 8
title: SQS coverage
---

Every SQS operation the emulator advertises, and what Emuplane does with it.
The console creates, deletes, sends, receives and purges; attributes, visibility,
batches and tags are reachable over the wire and are exercised by the API tests.

The table is generated from the emulator's own operation list; the console column
names the page or API explorer entry that reaches an operation, and a row under
*Emuplane test* names the test that exercises it. A blocked operation names the
dependant it is waiting on.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **20**
- Console actions (`/api/exec`, the create page): **5**
- Operations with an emuplane test: **20**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **5**
- Operations that are not console actions: **15**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **5**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **20** · Console actions: **5**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateQueue` | create-queue | SQS page › Create queue | tests/control/test_sqs_operations.py |
| `DeleteQueue` | delete-queue | SQS page › Delete queue | tests/control/test_sqs_operations.py |
| `ListQueues` | — | not a console action | tests/control/test_sqs_operations.py |
| `GetQueueUrl` | — | not a console action | tests/control/test_sqs_operations.py |
| `GetQueueAttributes` | — | not a console action | tests/control/test_sqs_operations.py |
| `SetQueueAttributes` | — | not a console action | tests/control/test_sqs_operations.py |
| `PurgeQueue` | purge-queue | SQS page › Purge queue | tests/control/test_sqs_operations.py |
| `SendMessage` | send-message | SQS page › Send message | tests/control/test_sqs_operations.py |
| `ReceiveMessage` | receive-message | SQS page › Receive message | tests/control/test_sqs_operations.py |
| `DeleteMessage` | — | not a console action | tests/control/test_sqs_operations.py |
| `ChangeMessageVisibility` | — | not a console action | tests/control/test_sqs_operations.py |
| `ChangeMessageVisibilityBatch` | — | not a console action | tests/control/test_sqs_operations.py |
| `SendMessageBatch` | — | not a console action | tests/control/test_sqs_operations.py |
| `DeleteMessageBatch` | — | not a console action | tests/control/test_sqs_operations.py |
| `TagQueue` | — | not a console action | tests/control/test_sqs_operations.py |
| `UntagQueue` | — | not a console action | tests/control/test_sqs_operations.py |
| `ListQueueTags` | — | not a console action | tests/control/test_sqs_operations.py |
| `StartMessageMoveTask` | — | not a console action | tests/control/test_sqs_operations.py |
| `ListMessageMoveTasks` | — | not a console action | tests/control/test_sqs_operations.py |
| `CancelMessageMoveTask` | — | not a console action | tests/control/test_sqs_operations.py |

<!-- coverage:end -->
