---
sidebar_position: 12
title: CloudWatch Logs coverage
---

Every CloudWatch Logs operation the emulator advertises, and what Emuplane does
with it. The console lists, creates and deletes log groups; streams, events,
filters, queries, destinations, deliveries and resource policies are reachable over
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

- Operations upstream advertises: **51**
- Console actions (`/api/exec`, the create page): **4**
- Operations with an emuplane test: **51**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **4**
- Operations that are not console actions: **47**
- GET operations (Get/List/Head/Describe) shown in the console: **2** of **19**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **51** · Console actions: **4**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateLogGroup` | create-log-group | CloudWatch Logs page › Create log group | tests/control/test_logs_operations.py |
| `DeleteLogGroup` | delete-log-group | CloudWatch Logs page › Delete log group | tests/control/test_logs_operations.py |
| `DescribeLogGroups` | describe-log-groups | CloudWatch Logs page › List log groups | tests/control/test_logs_operations.py |
| `CreateLogStream` | — | not a console action | tests/control/test_logs_operations.py |
| `DeleteLogStream` | — | not a console action | tests/control/test_logs_operations.py |
| `DescribeLogStreams` | describe-log-streams | CloudWatch Logs page › List streams | tests/control/test_logs_operations.py |
| `PutLogEvents` | — | not a console action | tests/control/test_logs_operations.py |
| `GetLogEvents` | — | not a console action | tests/control/test_logs_operations.py |
| `FilterLogEvents` | — | not a console action | tests/control/test_logs_operations.py |
| `GetLogRecord` | — | not a console action | tests/control/test_logs_operations.py |
| `GetLogGroupFields` | — | not a console action | tests/control/test_logs_operations.py |
| `StartLiveTail` | — | not a console action | tests/control/test_logs_operations.py |
| `PutRetentionPolicy` | — | not a console action | tests/control/test_logs_operations.py |
| `DeleteRetentionPolicy` | — | not a console action | tests/control/test_logs_operations.py |
| `PutSubscriptionFilter` | — | not a console action | tests/control/test_logs_operations.py |
| `DeleteSubscriptionFilter` | — | not a console action | tests/control/test_logs_operations.py |
| `DescribeSubscriptionFilters` | — | not a console action | tests/control/test_logs_operations.py |
| `PutMetricFilter` | — | not a console action | tests/control/test_logs_operations.py |
| `DeleteMetricFilter` | — | not a console action | tests/control/test_logs_operations.py |
| `DescribeMetricFilters` | — | not a console action | tests/control/test_logs_operations.py |
| `TagLogGroup` | — | not a console action | tests/control/test_logs_operations.py |
| `UntagLogGroup` | — | not a console action | tests/control/test_logs_operations.py |
| `ListTagsLogGroup` | — | not a console action | tests/control/test_logs_operations.py |
| `TagResource` | — | not a console action | tests/control/test_logs_operations.py |
| `UntagResource` | — | not a console action | tests/control/test_logs_operations.py |
| `ListTagsForResource` | — | not a console action | tests/control/test_logs_operations.py |
| `StartQuery` | — | not a console action | tests/control/test_logs_operations.py |
| `GetQueryResults` | — | not a console action | tests/control/test_logs_operations.py |
| `StopQuery` | — | not a console action | tests/control/test_logs_operations.py |
| `PutDestination` | — | not a console action | tests/control/test_logs_operations.py |
| `DeleteDestination` | — | not a console action | tests/control/test_logs_operations.py |
| `DescribeDestinations` | — | not a console action | tests/control/test_logs_operations.py |
| `PutDestinationPolicy` | — | not a console action | tests/control/test_logs_operations.py |
| `PutDeliverySource` | — | not a console action | tests/control/test_logs_operations.py |
| `GetDeliverySource` | — | not a console action | tests/control/test_logs_operations.py |
| `DeleteDeliverySource` | — | not a console action | tests/control/test_logs_operations.py |
| `DescribeDeliverySources` | — | not a console action | tests/control/test_logs_operations.py |
| `PutDeliveryDestination` | — | not a console action | tests/control/test_logs_operations.py |
| `GetDeliveryDestination` | — | not a console action | tests/control/test_logs_operations.py |
| `DeleteDeliveryDestination` | — | not a console action | tests/control/test_logs_operations.py |
| `DescribeDeliveryDestinations` | — | not a console action | tests/control/test_logs_operations.py |
| `PutDeliveryDestinationPolicy` | — | not a console action | tests/control/test_logs_operations.py |
| `GetDeliveryDestinationPolicy` | — | not a console action | tests/control/test_logs_operations.py |
| `DeleteDeliveryDestinationPolicy` | — | not a console action | tests/control/test_logs_operations.py |
| `CreateDelivery` | — | not a console action | tests/control/test_logs_operations.py |
| `GetDelivery` | — | not a console action | tests/control/test_logs_operations.py |
| `DeleteDelivery` | — | not a console action | tests/control/test_logs_operations.py |
| `DescribeDeliveries` | — | not a console action | tests/control/test_logs_operations.py |
| `PutResourcePolicy` | — | not a console action | tests/control/test_logs_operations.py |
| `DescribeResourcePolicies` | — | not a console action | tests/control/test_logs_operations.py |
| `DeleteResourcePolicy` | — | not a console action | tests/control/test_logs_operations.py |

<!-- coverage:end -->
