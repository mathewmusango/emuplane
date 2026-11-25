---
sidebar_position: 45
title: AWS Config coverage
---

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **14**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **14**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **8**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **14** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `PutConfigRule` | — | not yet | tests/control/test_config_operations.py |
| `DescribeConfigRules` | — | not yet | tests/control/test_config_operations.py |
| `DeleteConfigRule` | — | not yet | tests/control/test_config_operations.py |
| `PutConfigurationRecorder` | — | not yet | tests/control/test_config_operations.py |
| `DescribeConfigurationRecorders` | — | not yet | tests/control/test_config_operations.py |
| `DescribeConfigurationRecorderStatus` | — | not yet | tests/control/test_config_operations.py |
| `PutDeliveryChannel` | — | not yet | tests/control/test_config_operations.py |
| `DescribeDeliveryChannels` | — | not yet | tests/control/test_config_operations.py |
| `DescribeDeliveryChannelStatus` | — | not yet | tests/control/test_config_operations.py |
| `StartConfigurationRecorder` | — | not yet | tests/control/test_config_operations.py |
| `StopConfigurationRecorder` | — | not yet | tests/control/test_config_operations.py |
| `DescribeComplianceByConfigRule` | — | not yet | tests/control/test_config_operations.py |
| `GetComplianceDetailsByConfigRule` | — | not yet | tests/control/test_config_operations.py |
| `DescribeConfigRuleEvaluationStatus` | — | not yet | tests/control/test_config_operations.py |

<!-- coverage:end -->
