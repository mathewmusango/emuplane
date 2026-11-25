---
sidebar_position: 33
title: CloudWatch Metrics coverage
---

Every CloudWatch Metrics operation the emulator advertises, and what Emuplane does
with it. The service is signed with the `monitoring` credential scope and answers
the JSON, CBOR and Query protocols. There is no console action.

Metrics, alarms, composite alarms and dashboards are records held in memory; an
alarm is evaluated against the data points already published to its metric. Tags
apply to an alarm's ARN, so an alarm has to exist before it can be tagged.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **20**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **20**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **9**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **20** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `PutMetricData` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `GetMetricStatistics` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `GetMetricData` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `ListMetrics` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `PutMetricAlarm` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `PutCompositeAlarm` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `DescribeAlarms` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `DescribeAlarmsForMetric` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `DescribeAlarmHistory` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `DeleteAlarms` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `SetAlarmState` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `EnableAlarmActions` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `DisableAlarmActions` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `TagResource` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `UntagResource` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `PutDashboard` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `GetDashboard` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `DeleteDashboards` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |
| `ListDashboards` | — | not yet | tests/control/test_cloudwatch_metrics_operations.py |

<!-- coverage:end -->
