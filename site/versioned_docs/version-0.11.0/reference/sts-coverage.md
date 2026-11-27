---
sidebar_position: 5
title: STS coverage
---

What the emulator's security token service answers, and what Emuplane does with it.
There is no console page for STS and none is planned, because a session is used from
a CLI or a tool, so every row below reads *not a console action* rather than a gap.

Two things are worth knowing before you read the table.

- **The gateway forwards STS** the way it forwards any other global service, so
  `aws sts get-caller-identity --endpoint-url http://localhost:4571` answers the
  account the key was issued for. That call is the first thing to run when a tool's
  credentials look wrong.
- **A trust policy is not decided here.** `AssumeRole` and
  `AssumeRoleWithWebIdentity` issue a session; whether the caller was allowed to
  assume the role is evaluated against the role's trust policy only when the
  emulator runs with `AUTH=true`. The lab matrix covers that decision; the suite
  behind this page covers the credentials and their ARNs.

The emulator also implements `GetAccessKeyInfo` and `GetWebIdentityToken`, which its
README row does not advertise; both are exercised on the wire by the same test file.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **5**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **5**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **5**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **3**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **5** · Console actions: **0**






## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `GetCallerIdentity` | — | not a console action (a session is used from a CLI or a tool) | tests/control/test_sts.py |
| `AssumeRole` | — | not a console action (a session is used from a CLI or a tool) | tests/control/test_sts.py |
| `GetSessionToken` | — | not a console action (a session is used from a CLI or a tool) | tests/control/test_sts.py |
| `GetFederationToken` | — | not a console action (a session is used from a CLI or a tool) | tests/control/test_sts.py |
| `AssumeRoleWithWebIdentity` | — | not a console action (a session is used from a CLI or a tool) | tests/control/test_sts.py |

<!-- coverage:end -->
