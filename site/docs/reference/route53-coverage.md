---
sidebar_position: 66
title: Amazon Route 53 coverage
---

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **19**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **19**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **9**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **19** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateHostedZone` | — | not yet | tests/control/test_route53_operations.py |
| `GetHostedZone` | — | not yet | tests/control/test_route53_operations.py |
| `DeleteHostedZone` | — | not yet | tests/control/test_route53_operations.py |
| `ListHostedZones` | — | not yet | tests/control/test_route53_operations.py |
| `ListHostedZonesByName` | — | not yet | tests/control/test_route53_operations.py |
| `UpdateHostedZoneComment` | — | not yet | tests/control/test_route53_operations.py |
| `AssociateVPCWithHostedZone` | — | not yet | tests/control/test_route53_operations.py |
| `DisassociateVPCFromHostedZone` | — | not yet | tests/control/test_route53_operations.py |
| `ListHostedZonesByVPC` | — | not yet | tests/control/test_route53_operations.py |
| `ChangeResourceRecordSets` | — | not yet | tests/control/test_route53_operations.py |
| `ListResourceRecordSets` | — | not yet | tests/control/test_route53_operations.py |
| `GetChange` | — | not yet | tests/control/test_route53_operations.py |
| `CreateHealthCheck` | — | not yet | tests/control/test_route53_operations.py |
| `GetHealthCheck` | — | not yet | tests/control/test_route53_operations.py |
| `DeleteHealthCheck` | — | not yet | tests/control/test_route53_operations.py |
| `ListHealthChecks` | — | not yet | tests/control/test_route53_operations.py |
| `UpdateHealthCheck` | — | not yet | tests/control/test_route53_operations.py |
| `ChangeTagsForResource` | — | not yet | tests/control/test_route53_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_route53_operations.py |

<!-- coverage:end -->
