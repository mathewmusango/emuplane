---
sidebar_position: 31
title: Signer coverage
---

Every Signer operation the emulator advertises, and what Emuplane does with it.
The service is REST/JSON on `/signing-jobs` and `/signing-profiles`, signed with
the `signer` credential scope. There is no console action: profiles are created
and cancelled, jobs started and described, and profile permissions added and
removed over the wire.

Signing is synchronous: `StartSigningJob` validates the source object against the
local S3 store and writes the signed object to the destination bucket before it
returns, so the job is already `Succeeded` and a caller never has to poll. Without
ACM-held signing material the written object is a JSON receipt rather than a
signature. A cancelled profile keeps its name and its permissions.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **9**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **9**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **4**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **9** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `StartSigningJob` | — | not yet | tests/control/test_signer_operations.py |
| `DescribeSigningJob` | — | not yet | tests/control/test_signer_operations.py |
| `ListSigningJobs` | — | not yet | tests/control/test_signer_operations.py |
| `PutSigningProfile` | — | not yet | tests/control/test_signer_operations.py |
| `GetSigningProfile` | — | not yet | tests/control/test_signer_operations.py |
| `CancelSigningProfile` | — | not yet | tests/control/test_signer_operations.py |
| `AddProfilePermission` | — | not yet | tests/control/test_signer_operations.py |
| `ListProfilePermissions` | — | not yet | tests/control/test_signer_operations.py |
| `RemoveProfilePermission` | — | not yet | tests/control/test_signer_operations.py |

<!-- coverage:end -->
