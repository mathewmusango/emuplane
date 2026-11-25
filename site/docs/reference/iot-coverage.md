---
sidebar_position: 81
title: IoT Core coverage
---

Every IoT Core operation the emulator advertises, and what Emuplane does with it.
The control plane is REST-style — the verb and path select the action — signed with
the `iot` scope; `Publish` and the retained-message reads are the `iot-data` plane.
The README row's own "76 operations" counts `MQTT-over-WebSocket pub/sub`, which is
a transport rather than a callable operation, so the ledger excludes it and names
the row's `Publish (HTTP)` as `Publish`: 75 callable operations.

Certificates are real X.509. The suite builds its own CA and a verification
certificate whose CN is the account's registration code, registers the CA, and
issues leaves with it for `RegisterCertificate` and
`RegisterCertificateWithoutCA`; `CreateCertificateFromCsr` signs a locally generated
CSR with the emulator's local CA. Policy attachment needs a certificate target, and
a custom domain configuration needs an ACM certificate, which the delete test
requests. Rule actions carry a role ARN that the live `AUTH=true` evaluator
resolves, so the suite creates that IAM role; the in-process stand-in does not
check it. Delete tests create their own resource and update tests restore the
stable record.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **75**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **75**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **30**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **75** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateThing` | — | not yet | tests/control/test_iot_operations.py |
| `DescribeThing` | — | not yet | tests/control/test_iot_operations.py |
| `ListThings` | — | not yet | tests/control/test_iot_operations.py |
| `UpdateThing` | — | not yet | tests/control/test_iot_operations.py |
| `DeleteThing` | — | not yet | tests/control/test_iot_operations.py |
| `CreateThingType` | — | not yet | tests/control/test_iot_operations.py |
| `CreateThingGroup` | — | not yet | tests/control/test_iot_operations.py |
| `AddThingToThingGroup` | — | not yet | tests/control/test_iot_operations.py |
| `ListThingsInThingGroup` | — | not yet | tests/control/test_iot_operations.py |
| `ListThingGroupsForThing` | — | not yet | tests/control/test_iot_operations.py |
| `CreateKeysAndCertificate` | — | not yet | tests/control/test_iot_operations.py |
| `RegisterCertificate` | — | not yet | tests/control/test_iot_operations.py |
| `RegisterCertificateWithoutCA` | — | not yet | tests/control/test_iot_operations.py |
| `CreateCertificateFromCsr` | — | not yet | tests/control/test_iot_operations.py |
| `UpdateCertificate` | — | not yet | tests/control/test_iot_operations.py |
| `DeleteCertificate` | — | not yet | tests/control/test_iot_operations.py |
| `GetRegistrationCode` | — | not yet | tests/control/test_iot_operations.py |
| `DeleteRegistrationCode` | — | not yet | tests/control/test_iot_operations.py |
| `RegisterCACertificate` | — | not yet | tests/control/test_iot_operations.py |
| `DescribeCACertificate` | — | not yet | tests/control/test_iot_operations.py |
| `UpdateCACertificate` | — | not yet | tests/control/test_iot_operations.py |
| `ListCACertificates` | — | not yet | tests/control/test_iot_operations.py |
| `DeleteCACertificate` | — | not yet | tests/control/test_iot_operations.py |
| `ListCertificatesByCA` | — | not yet | tests/control/test_iot_operations.py |
| `CreateProvisioningTemplate` | — | not yet | tests/control/test_iot_operations.py |
| `DescribeProvisioningTemplate` | — | not yet | tests/control/test_iot_operations.py |
| `ListProvisioningTemplates` | — | not yet | tests/control/test_iot_operations.py |
| `UpdateProvisioningTemplate` | — | not yet | tests/control/test_iot_operations.py |
| `DeleteProvisioningTemplate` | — | not yet | tests/control/test_iot_operations.py |
| `CreateProvisioningTemplateVersion` | — | not yet | tests/control/test_iot_operations.py |
| `ListProvisioningTemplateVersions` | — | not yet | tests/control/test_iot_operations.py |
| `DescribeProvisioningTemplateVersion` | — | not yet | tests/control/test_iot_operations.py |
| `DeleteProvisioningTemplateVersion` | — | not yet | tests/control/test_iot_operations.py |
| `CreateProvisioningClaim` | — | not yet | tests/control/test_iot_operations.py |
| `AttachThingPrincipal` | — | not yet | tests/control/test_iot_operations.py |
| `DetachThingPrincipal` | — | not yet | tests/control/test_iot_operations.py |
| `ListThingPrincipals` | — | not yet | tests/control/test_iot_operations.py |
| `ListPrincipalThings` | — | not yet | tests/control/test_iot_operations.py |
| `CreatePolicy` | — | not yet | tests/control/test_iot_operations.py |
| `CreatePolicyVersion` | — | not yet | tests/control/test_iot_operations.py |
| `SetDefaultPolicyVersion` | — | not yet | tests/control/test_iot_operations.py |
| `AttachPolicy` | — | not yet | tests/control/test_iot_operations.py |
| `DetachPolicy` | — | not yet | tests/control/test_iot_operations.py |
| `ListAttachedPolicies` | — | not yet | tests/control/test_iot_operations.py |
| `ListTargetsForPolicy` | — | not yet | tests/control/test_iot_operations.py |
| `AttachPrincipalPolicy` | — | not yet | tests/control/test_iot_operations.py |
| `DetachPrincipalPolicy` | — | not yet | tests/control/test_iot_operations.py |
| `ListPrincipalPolicies` | — | not yet | tests/control/test_iot_operations.py |
| `ListPolicyPrincipals` | — | not yet | tests/control/test_iot_operations.py |
| `CreateTopicRule` | — | not yet | tests/control/test_iot_operations.py |
| `GetTopicRule` | — | not yet | tests/control/test_iot_operations.py |
| `ReplaceTopicRule` | — | not yet | tests/control/test_iot_operations.py |
| `DeleteTopicRule` | — | not yet | tests/control/test_iot_operations.py |
| `ListTopicRules` | — | not yet | tests/control/test_iot_operations.py |
| `EnableTopicRule` | — | not yet | tests/control/test_iot_operations.py |
| `DisableTopicRule` | — | not yet | tests/control/test_iot_operations.py |
| `UpdateIndexingConfiguration` | — | not yet | tests/control/test_iot_operations.py |
| `GetIndexingConfiguration` | — | not yet | tests/control/test_iot_operations.py |
| `DescribeIndex` | — | not yet | tests/control/test_iot_operations.py |
| `ListIndices` | — | not yet | tests/control/test_iot_operations.py |
| `SearchIndex` | — | not yet | tests/control/test_iot_operations.py |
| `DescribeEndpoint` | — | not yet | tests/control/test_iot_operations.py |
| `Publish` | — | not yet | tests/control/test_iot_operations.py |
| `GetRetainedMessage` | — | not yet | tests/control/test_iot_operations.py |
| `ListRetainedMessages` | — | not yet | tests/control/test_iot_operations.py |
| `DescribeEventConfigurations` | — | not yet | tests/control/test_iot_operations.py |
| `UpdateEventConfigurations` | — | not yet | tests/control/test_iot_operations.py |
| `CreateDomainConfiguration` | — | not yet | tests/control/test_iot_operations.py |
| `DescribeDomainConfiguration` | — | not yet | tests/control/test_iot_operations.py |
| `ListDomainConfigurations` | — | not yet | tests/control/test_iot_operations.py |
| `UpdateDomainConfiguration` | — | not yet | tests/control/test_iot_operations.py |
| `DeleteDomainConfiguration` | — | not yet | tests/control/test_iot_operations.py |
| `TagResource` | — | not yet | tests/control/test_iot_operations.py |
| `UntagResource` | — | not yet | tests/control/test_iot_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_iot_operations.py |

<!-- coverage:end -->
