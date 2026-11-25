---
sidebar_position: 34
title: DynamoDB Streams coverage
---

Every DynamoDB Streams operation the emulator advertises, and what Emuplane does
with it. The service reads the records the main DynamoDB service emits on every
write that changes an item. It signs with the `dynamodb` credential scope and is
told apart by the `DynamoDBStreams_20120810` target prefix. There is no console
action.

A table gets one synthetic shard and no shard splitting. Iterator tokens are
opaque and expire after 15 minutes, `GetRecords` stops at 1,000 records or 1 MB,
and a disabled stream stays readable for 24 hours.

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
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **4**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **4** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `ListStreams` | — | not yet | tests/control/test_dynamodb_streams_operations.py |
| `DescribeStream` | — | not yet | tests/control/test_dynamodb_streams_operations.py |
| `GetShardIterator` | — | not yet | tests/control/test_dynamodb_streams_operations.py |
| `GetRecords` | — | not yet | tests/control/test_dynamodb_streams_operations.py |

<!-- coverage:end -->
