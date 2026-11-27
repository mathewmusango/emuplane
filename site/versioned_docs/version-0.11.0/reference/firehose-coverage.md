---
sidebar_position: 47
title: Data Firehose coverage
---

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **12**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **12**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **3**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **12** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateDeliveryStream` | — | not yet | tests/control/test_firehose_operations.py |
| `DeleteDeliveryStream` | — | not yet | tests/control/test_firehose_operations.py |
| `DescribeDeliveryStream` | — | not yet | tests/control/test_firehose_operations.py |
| `ListDeliveryStreams` | — | not yet | tests/control/test_firehose_operations.py |
| `PutRecord` | — | not yet | tests/control/test_firehose_operations.py |
| `PutRecordBatch` | — | not yet | tests/control/test_firehose_operations.py |
| `UpdateDestination` | — | not yet | tests/control/test_firehose_operations.py |
| `TagDeliveryStream` | — | not yet | tests/control/test_firehose_operations.py |
| `UntagDeliveryStream` | — | not yet | tests/control/test_firehose_operations.py |
| `ListTagsForDeliveryStream` | — | not yet | tests/control/test_firehose_operations.py |
| `StartDeliveryStreamEncryption` | — | not yet | tests/control/test_firehose_operations.py |
| `StopDeliveryStreamEncryption` | — | not yet | tests/control/test_firehose_operations.py |

<!-- coverage:end -->
