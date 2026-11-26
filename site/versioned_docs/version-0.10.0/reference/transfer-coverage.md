---
sidebar_position: 23
title: Transfer Family coverage
---

Every Transfer Family operation the emulator advertises, and what Emuplane does
with it. There is no console action: servers, users and SSH public keys are
managed over the wire. The emulator also runs a real SFTP listener on `:2222`;
these tests cover the control plane only.

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

- Group: **Infrastructure** · operations: **12** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateServer` | — | not yet | tests/control/test_transfer_operations.py |
| `DescribeServer` | — | not yet | tests/control/test_transfer_operations.py |
| `DeleteServer` | — | not yet | tests/control/test_transfer_operations.py |
| `ListServers` | — | not yet | tests/control/test_transfer_operations.py |
| `StartServer` | — | not yet | tests/control/test_transfer_operations.py |
| `StopServer` | — | not yet | tests/control/test_transfer_operations.py |
| `CreateUser` | — | not yet | tests/control/test_transfer_operations.py |
| `DescribeUser` | — | not yet | tests/control/test_transfer_operations.py |
| `DeleteUser` | — | not yet | tests/control/test_transfer_operations.py |
| `ListUsers` | — | not yet | tests/control/test_transfer_operations.py |
| `ImportSshPublicKey` | — | not yet | tests/control/test_transfer_operations.py |
| `DeleteSshPublicKey` | — | not yet | tests/control/test_transfer_operations.py |

<!-- coverage:end -->
