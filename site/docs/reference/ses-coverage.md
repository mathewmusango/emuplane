---
sidebar_position: 29
title: SES coverage
---

Every SES (v1) operation the emulator advertises, and what Emuplane does with it.
There is no console action: identities, sends, configuration sets, templates and
receipt rule sets are driven over the wire. Emails are stored in memory and never
sent; the sender must be verified, and a sandboxed account may only reach verified
or `@simulator.amazonses.com` recipients.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **35**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **35**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **14**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **35** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `SendEmail` | — | not yet | tests/control/test_ses_operations.py |
| `SendRawEmail` | — | not yet | tests/control/test_ses_operations.py |
| `SendTemplatedEmail` | — | not yet | tests/control/test_ses_operations.py |
| `SendBulkTemplatedEmail` | — | not yet | tests/control/test_ses_operations.py |
| `VerifyEmailIdentity` | — | not yet | tests/control/test_ses_operations.py |
| `VerifyEmailAddress` | — | not yet | tests/control/test_ses_operations.py |
| `VerifyDomainIdentity` | — | not yet | tests/control/test_ses_operations.py |
| `VerifyDomainDkim` | — | not yet | tests/control/test_ses_operations.py |
| `ListIdentities` | — | not yet | tests/control/test_ses_operations.py |
| `ListVerifiedEmailAddresses` | — | not yet | tests/control/test_ses_operations.py |
| `GetIdentityVerificationAttributes` | — | not yet | tests/control/test_ses_operations.py |
| `GetIdentityDkimAttributes` | — | not yet | tests/control/test_ses_operations.py |
| `DeleteIdentity` | — | not yet | tests/control/test_ses_operations.py |
| `GetSendQuota` | — | not yet | tests/control/test_ses_operations.py |
| `GetSendStatistics` | — | not yet | tests/control/test_ses_operations.py |
| `SetIdentityNotificationTopic` | — | not yet | tests/control/test_ses_operations.py |
| `SetIdentityFeedbackForwardingEnabled` | — | not yet | tests/control/test_ses_operations.py |
| `CreateConfigurationSet` | — | not yet | tests/control/test_ses_operations.py |
| `DeleteConfigurationSet` | — | not yet | tests/control/test_ses_operations.py |
| `DescribeConfigurationSet` | — | not yet | tests/control/test_ses_operations.py |
| `ListConfigurationSets` | — | not yet | tests/control/test_ses_operations.py |
| `CreateTemplate` | — | not yet | tests/control/test_ses_operations.py |
| `GetTemplate` | — | not yet | tests/control/test_ses_operations.py |
| `UpdateTemplate` | — | not yet | tests/control/test_ses_operations.py |
| `DeleteTemplate` | — | not yet | tests/control/test_ses_operations.py |
| `ListTemplates` | — | not yet | tests/control/test_ses_operations.py |
| `CreateReceiptRuleSet` | — | not yet | tests/control/test_ses_operations.py |
| `DescribeReceiptRuleSet` | — | not yet | tests/control/test_ses_operations.py |
| `ListReceiptRuleSets` | — | not yet | tests/control/test_ses_operations.py |
| `DeleteReceiptRuleSet` | — | not yet | tests/control/test_ses_operations.py |
| `SetActiveReceiptRuleSet` | — | not yet | tests/control/test_ses_operations.py |
| `DescribeActiveReceiptRuleSet` | — | not yet | tests/control/test_ses_operations.py |
| `CreateReceiptRule` | — | not yet | tests/control/test_ses_operations.py |
| `DescribeReceiptRule` | — | not yet | tests/control/test_ses_operations.py |
| `DeleteReceiptRule` | — | not yet | tests/control/test_ses_operations.py |

<!-- coverage:end -->
