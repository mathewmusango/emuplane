---
sidebar_position: 9
title: SNS coverage
---

Every SNS operation the emulator advertises, and what Emuplane does with it.
The console creates, deletes and publishes topics; subscriptions, attributes,
permissions, platform applications and endpoints and tags are reachable over the
wire and are exercised by the API tests.

The table is generated from the emulator's own operation list; the console column
names the page or API explorer entry that reaches an operation, and a row under
*Emuplane test* names the test that exercises it. A blocked operation names the
dependant it is waiting on.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **28**
- Console actions (`/api/exec`, the create page): **3**
- Operations with an emuplane test: **28**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **3**
- Operations that are not console actions: **25**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **9**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **28** · Console actions: **3**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateTopic` | create-topic | SNS page › Create topic | tests/control/test_sns_operations.py |
| `DeleteTopic` | delete-topic | SNS page › Delete topic | tests/control/test_sns_operations.py |
| `ListTopics` | — | not a console action | tests/control/test_sns_operations.py |
| `GetTopicAttributes` | — | not a console action | tests/control/test_sns_operations.py |
| `SetTopicAttributes` | — | not a console action | tests/control/test_sns_operations.py |
| `AddPermission` | — | not a console action | tests/control/test_sns_operations.py |
| `RemovePermission` | — | not a console action | tests/control/test_sns_operations.py |
| `Subscribe` | — | not a console action | tests/control/test_sns_operations.py |
| `Unsubscribe` | — | not a console action | tests/control/test_sns_operations.py |
| `ListSubscriptions` | — | not a console action | tests/control/test_sns_operations.py |
| `ListSubscriptionsByTopic` | — | not a console action | tests/control/test_sns_operations.py |
| `GetSubscriptionAttributes` | — | not a console action | tests/control/test_sns_operations.py |
| `SetSubscriptionAttributes` | — | not a console action | tests/control/test_sns_operations.py |
| `ConfirmSubscription` | — | not a console action | tests/control/test_sns_operations.py |
| `Publish` | publish | SNS page › Publish | tests/control/test_sns_operations.py |
| `PublishBatch` | — | not a console action | tests/control/test_sns_operations.py |
| `TagResource` | — | not a console action | tests/control/test_sns_operations.py |
| `UntagResource` | — | not a console action | tests/control/test_sns_operations.py |
| `ListTagsForResource` | — | not a console action | tests/control/test_sns_operations.py |
| `CreatePlatformApplication` | — | not a console action | tests/control/test_sns_operations.py |
| `ListPlatformApplications` | — | not a console action | tests/control/test_sns_operations.py |
| `GetPlatformApplicationAttributes` | — | not a console action | tests/control/test_sns_operations.py |
| `SetPlatformApplicationAttributes` | — | not a console action | tests/control/test_sns_operations.py |
| `CreatePlatformEndpoint` | — | not a console action | tests/control/test_sns_operations.py |
| `GetEndpointAttributes` | — | not a console action | tests/control/test_sns_operations.py |
| `SetEndpointAttributes` | — | not a console action | tests/control/test_sns_operations.py |
| `DeleteEndpoint` | — | not a console action | tests/control/test_sns_operations.py |
| `DeletePlatformApplication` | — | not a console action | tests/control/test_sns_operations.py |

<!-- coverage:end -->
