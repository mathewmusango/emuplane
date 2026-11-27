---
sidebar_position: 16
title: ACM coverage
---

Every ACM operation the emulator advertises, and what Emuplane does with it.
There is no console action: certificates are requested, imported and tagged over
the wire, and every advertised operation is exercised by the API tests.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **12**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **12**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **4**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **12** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `RequestCertificate` | — | not yet | tests/control/test_acm_operations.py |
| `DescribeCertificate` | — | not yet | tests/control/test_acm_operations.py |
| `ListCertificates` | — | not yet | tests/control/test_acm_operations.py |
| `DeleteCertificate` | — | not yet | tests/control/test_acm_operations.py |
| `GetCertificate` | — | not yet | tests/control/test_acm_operations.py |
| `ImportCertificate` | — | not yet | tests/control/test_acm_operations.py |
| `AddTagsToCertificate` | — | not yet | tests/control/test_acm_operations.py |
| `RemoveTagsFromCertificate` | — | not yet | tests/control/test_acm_operations.py |
| `ListTagsForCertificate` | — | not yet | tests/control/test_acm_operations.py |
| `UpdateCertificateOptions` | — | not yet | tests/control/test_acm_operations.py |
| `RenewCertificate` | — | not yet | tests/control/test_acm_operations.py |
| `ResendValidationEmail` | — | not yet | tests/control/test_acm_operations.py |

<!-- coverage:end -->
