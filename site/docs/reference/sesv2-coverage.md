---
sidebar_position: 30
title: SES v2 coverage
---

Every SES v2 operation the emulator advertises, and what Emuplane does with it.
The service speaks REST/JSON under `/v2/email/` and is signed with the `ses`
credential scope. There is no console action: identities, sends, configuration
sets, templates, tenants and dedicated IP pools are driven over the wire.

Identities are auto-verified, emails are stored in memory and never sent, and
templates are shared with SES v1, so a template created through either API
renders on a send from either one. A tenant association blocks the delete of the
resource it names until the association is removed, and a dedicated IP pool is a
record with no IP addresses behind it.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **46**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **46**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **16**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **46** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `SendEmail` | — | not yet | tests/control/test_sesv2_operations.py |
| `CreateEmailIdentity` | — | not yet | tests/control/test_sesv2_operations.py |
| `GetEmailIdentity` | — | not yet | tests/control/test_sesv2_operations.py |
| `DeleteEmailIdentity` | — | not yet | tests/control/test_sesv2_operations.py |
| `PutEmailIdentityConfigurationSetAttributes` | — | not yet | tests/control/test_sesv2_operations.py |
| `ListEmailIdentities` | — | not yet | tests/control/test_sesv2_operations.py |
| `CreateConfigurationSet` | — | not yet | tests/control/test_sesv2_operations.py |
| `GetConfigurationSet` | — | not yet | tests/control/test_sesv2_operations.py |
| `DeleteConfigurationSet` | — | not yet | tests/control/test_sesv2_operations.py |
| `ListConfigurationSets` | — | not yet | tests/control/test_sesv2_operations.py |
| `PutConfigurationSetTrackingOptions` | — | not yet | tests/control/test_sesv2_operations.py |
| `PutConfigurationSetDeliveryOptions` | — | not yet | tests/control/test_sesv2_operations.py |
| `PutConfigurationSetReputationOptions` | — | not yet | tests/control/test_sesv2_operations.py |
| `PutConfigurationSetSendingOptions` | — | not yet | tests/control/test_sesv2_operations.py |
| `PutConfigurationSetSuppressionOptions` | — | not yet | tests/control/test_sesv2_operations.py |
| `PutConfigurationSetVdmOptions` | — | not yet | tests/control/test_sesv2_operations.py |
| `PutConfigurationSetArchivingOptions` | — | not yet | tests/control/test_sesv2_operations.py |
| `CreateConfigurationSetEventDestination` | — | not yet | tests/control/test_sesv2_operations.py |
| `GetConfigurationSetEventDestinations` | — | not yet | tests/control/test_sesv2_operations.py |
| `UpdateConfigurationSetEventDestination` | — | not yet | tests/control/test_sesv2_operations.py |
| `DeleteConfigurationSetEventDestination` | — | not yet | tests/control/test_sesv2_operations.py |
| `CreateEmailTemplate` | — | not yet | tests/control/test_sesv2_operations.py |
| `GetEmailTemplate` | — | not yet | tests/control/test_sesv2_operations.py |
| `UpdateEmailTemplate` | — | not yet | tests/control/test_sesv2_operations.py |
| `DeleteEmailTemplate` | — | not yet | tests/control/test_sesv2_operations.py |
| `ListEmailTemplates` | — | not yet | tests/control/test_sesv2_operations.py |
| `GetAccount` | — | not yet | tests/control/test_sesv2_operations.py |
| `PutAccountDetails` | — | not yet | tests/control/test_sesv2_operations.py |
| `PutAccountSuppressionAttributes` | — | not yet | tests/control/test_sesv2_operations.py |
| `ListSuppressedDestinations` | — | not yet | tests/control/test_sesv2_operations.py |
| `TagResource` | — | not yet | tests/control/test_sesv2_operations.py |
| `UntagResource` | — | not yet | tests/control/test_sesv2_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_sesv2_operations.py |
| `CreateTenant` | — | not yet | tests/control/test_sesv2_operations.py |
| `GetTenant` | — | not yet | tests/control/test_sesv2_operations.py |
| `ListTenants` | — | not yet | tests/control/test_sesv2_operations.py |
| `DeleteTenant` | — | not yet | tests/control/test_sesv2_operations.py |
| `CreateTenantResourceAssociation` | — | not yet | tests/control/test_sesv2_operations.py |
| `DeleteTenantResourceAssociation` | — | not yet | tests/control/test_sesv2_operations.py |
| `ListTenantResources` | — | not yet | tests/control/test_sesv2_operations.py |
| `ListResourceTenants` | — | not yet | tests/control/test_sesv2_operations.py |
| `PutTenantSuppressionAttributes` | — | not yet | tests/control/test_sesv2_operations.py |
| `CreateDedicatedIpPool` | — | not yet | tests/control/test_sesv2_operations.py |
| `GetDedicatedIpPool` | — | not yet | tests/control/test_sesv2_operations.py |
| `ListDedicatedIpPools` | — | not yet | tests/control/test_sesv2_operations.py |
| `DeleteDedicatedIpPool` | — | not yet | tests/control/test_sesv2_operations.py |

<!-- coverage:end -->
