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

- Operations upstream advertises: **4**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **4**
- Operations with no emuplane test: **4**

- Group: **Infrastructure** · operations: **4** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `GetAccountInformation` | — | not yet | — |
| `GetContactInformation` | — | not yet | — |
| `ListRegions` | — | not yet | — |
| `GetRegionOptStatus` | — | not yet | — |

<!-- coverage:end -->
