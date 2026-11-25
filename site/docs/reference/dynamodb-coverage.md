---
sidebar_position: 10
title: DynamoDB coverage
---

Every DynamoDB operation the emulator advertises, and what Emuplane does with it.
The console lists, creates, deletes, scans and puts items; queries, batches,
transactions, TTL, backups, tags and streaming destinations are reachable over the
wire and are exercised by the API tests.

The table is generated from the emulator's own operation list; the console column
names the page or API explorer entry that reaches an operation, and a row under
*Emuplane test* names the test that exercises it. A blocked operation names the
dependant it is waiting on.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **27**
- Console actions (`/api/exec`, the create page): **5**
- Operations with an emuplane test: **27**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **5**
- Operations that are not console actions: **22**
- GET operations (Get/List/Head/Describe) shown in the console: **1** of **8**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **27** · Console actions: **5**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateTable` | create-table | DynamoDB page › Create table | tests/control/test_dynamodb_operations.py |
| `UpdateTable` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `DeleteTable` | delete-table | DynamoDB page › Delete table | tests/control/test_dynamodb_operations.py |
| `DescribeTable` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `ListTables` | list-tables | DynamoDB page › List tables | tests/control/test_dynamodb_operations.py |
| `PutItem` | put-item | DynamoDB page › Put item | tests/control/test_dynamodb_operations.py |
| `GetItem` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `DeleteItem` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `UpdateItem` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `Query` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `Scan` | scan | DynamoDB page › Scan table | tests/control/test_dynamodb_operations.py |
| `BatchWriteItem` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `BatchGetItem` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `TransactWriteItems` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `TransactGetItems` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `DescribeTimeToLive` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `UpdateTimeToLive` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `DescribeContinuousBackups` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `UpdateContinuousBackups` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `DescribeEndpoints` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `TagResource` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `UntagResource` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `ListTagsOfResource` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `EnableKinesisStreamingDestination` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `DisableKinesisStreamingDestination` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `DescribeKinesisStreamingDestination` | — | not a console action | tests/control/test_dynamodb_operations.py |
| `UpdateKinesisStreamingDestination` | — | not a console action | tests/control/test_dynamodb_operations.py |

<!-- coverage:end -->
