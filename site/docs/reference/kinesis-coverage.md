---
sidebar_position: 14
title: Kinesis coverage
---

Every Kinesis operation the emulator advertises, and what Emuplane does with it.
The console lists, creates and deletes streams; shards, records, retention,
encryption, monitoring, consumers, tags and resource policies are reachable over
the wire and are exercised by the API tests.

The table is generated from the emulator's own operation list; the console column
names the page or API explorer entry that reaches an operation, and a row under
*Emuplane test* names the test that exercises it. A blocked operation names the
dependant it is waiting on.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **30**
- Console actions (`/api/exec`, the create page): **3**
- Operations with an emuplane test: **30**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **3**
- Operations that are not console actions: **27**
- GET operations (Get/List/Head/Describe) shown in the console: **1** of **10**
- Operations with no emuplane test: **0**

- Group: **Extended** · operations: **30** · Console actions: **3**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateStream` | create-stream | Kinesis page › Create stream | tests/control/test_kinesis_operations.py |
| `DeleteStream` | delete-stream | Kinesis page › Delete stream | tests/control/test_kinesis_operations.py |
| `DescribeStream` | — | not a console action | tests/control/test_kinesis_operations.py |
| `DescribeStreamSummary` | — | not a console action | tests/control/test_kinesis_operations.py |
| `ListStreams` | list-streams | Kinesis page › List streams | tests/control/test_kinesis_operations.py |
| `ListShards` | — | not a console action | tests/control/test_kinesis_operations.py |
| `PutRecord` | — | not a console action | tests/control/test_kinesis_operations.py |
| `PutRecords` | — | not a console action | tests/control/test_kinesis_operations.py |
| `GetShardIterator` | — | not a console action | tests/control/test_kinesis_operations.py |
| `GetRecords` | — | not a console action | tests/control/test_kinesis_operations.py |
| `IncreaseStreamRetentionPeriod` | — | not a console action | tests/control/test_kinesis_operations.py |
| `DecreaseStreamRetentionPeriod` | — | not a console action | tests/control/test_kinesis_operations.py |
| `MergeShards` | — | not a console action | tests/control/test_kinesis_operations.py |
| `SplitShard` | — | not a console action | tests/control/test_kinesis_operations.py |
| `UpdateShardCount` | — | not a console action | tests/control/test_kinesis_operations.py |
| `StartStreamEncryption` | — | not a console action | tests/control/test_kinesis_operations.py |
| `StopStreamEncryption` | — | not a console action | tests/control/test_kinesis_operations.py |
| `EnableEnhancedMonitoring` | — | not a console action | tests/control/test_kinesis_operations.py |
| `DisableEnhancedMonitoring` | — | not a console action | tests/control/test_kinesis_operations.py |
| `RegisterStreamConsumer` | — | not a console action | tests/control/test_kinesis_operations.py |
| `DeregisterStreamConsumer` | — | not a console action | tests/control/test_kinesis_operations.py |
| `ListStreamConsumers` | — | not a console action | tests/control/test_kinesis_operations.py |
| `DescribeStreamConsumer` | — | not a console action | tests/control/test_kinesis_operations.py |
| `SubscribeToShard` | — | not a console action | tests/control/test_kinesis_operations.py |
| `AddTagsToStream` | — | not a console action | tests/control/test_kinesis_operations.py |
| `RemoveTagsFromStream` | — | not a console action | tests/control/test_kinesis_operations.py |
| `ListTagsForStream` | — | not a console action | tests/control/test_kinesis_operations.py |
| `PutResourcePolicy` | — | not a console action | tests/control/test_kinesis_operations.py |
| `GetResourcePolicy` | — | not a console action | tests/control/test_kinesis_operations.py |
| `DeleteResourcePolicy` | — | not a console action | tests/control/test_kinesis_operations.py |

<!-- coverage:end -->
