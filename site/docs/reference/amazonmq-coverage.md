---
sidebar_position: 17
title: AmazonMQ coverage
---

Every AmazonMQ operation the emulator advertises, and what Emuplane does with it.
There is no console action: brokers, users and tags are managed over the wire, and
every advertised operation is exercised by the API tests. The emulator is
metadata-only — no broker runs a container.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **16**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **16**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **7**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **16** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateBroker` | — | not yet | tests/control/test_mq_operations.py |
| `ListBrokers` | — | not yet | tests/control/test_mq_operations.py |
| `DescribeBrokers` | — | not yet | tests/control/test_mq_operations.py |
| `DeleteBrokers` | — | not yet | tests/control/test_mq_operations.py |
| `UpdateBroker` | — | not yet | tests/control/test_mq_operations.py |
| `RebootBroker` | — | not yet | tests/control/test_mq_operations.py |
| `DescribeBrokerEngineTypes` | — | not yet | tests/control/test_mq_operations.py |
| `DescribeBrokerInstanceOptions` | — | not yet | tests/control/test_mq_operations.py |
| `CreateTags` | — | not yet | tests/control/test_mq_operations.py |
| `ListTags` | — | not yet | tests/control/test_mq_operations.py |
| `DeleteTags` | — | not yet | tests/control/test_mq_operations.py |
| `CreateUser` | — | not yet | tests/control/test_mq_operations.py |
| `DeleteUser` | — | not yet | tests/control/test_mq_operations.py |
| `ListUsers` | — | not yet | tests/control/test_mq_operations.py |
| `UpdateUser` | — | not yet | tests/control/test_mq_operations.py |
| `DescribeUser` | — | not yet | tests/control/test_mq_operations.py |

<!-- coverage:end -->
