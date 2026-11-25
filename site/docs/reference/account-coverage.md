---
sidebar_position: 5
title: Account coverage
---

Every Account operation the emulator advertises, and what Emuplane does with it.
Account is the service that answers who the caller is, the account's contact
details, and which regions it may use.

The table is generated from the emulator's own operation list.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **4**
- Console actions (`/api/exec`, the create page): **4**
- Operations with an emuplane test: **4**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **4**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **4** of **4**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **4** · Console actions: **4**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `GetAccountInformation` | get-account-information | Account page > Account details | tests/control/test_account_api.py |
| `GetContactInformation` | get-contact-information | Account page > Contact information | tests/control/test_account_api.py |
| `ListRegions` | list-regions | Account page > AWS Regions | tests/control/test_account_api.py |
| `GetRegionOptStatus` | get-region-opt-status | Account page > AWS Regions > the signed-in region | tests/control/test_account_api.py |

<!-- coverage:end -->
