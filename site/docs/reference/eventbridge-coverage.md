---
sidebar_position: 76
title: EventBridge coverage
---

Every EventBridge operation the emulator advertises, and what Emuplane does with it.
Requests are JSON with an `X-Amz-Target` naming the action, signed with the `events`
credential scope. There is no console action.

Buses, rules, targets, archives, connections, API destinations and global endpoints
are records. A rule's target is validated but not delivered to, so the tests need no
consumer. An archive stores the events a matching publish sends it, and a replay of
an archive with no matching events completes synchronously — the reachable
`CancelReplay` answer is therefore the “already completed” refusal. A global endpoint
is accepted only with an existing Route53 health check (created under the `route53`
scope) and two same-named buses in the primary and secondary regions; replication is
disabled in the test so no IAM role is needed. Stable names carry the read and update
rows; delete actions make their own resource.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **57**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **57**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **22**
- Operations with no emuplane test: **0**

- Group: **Extended** · operations: **57** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateEventBus` | — | not yet | tests/control/test_eventbridge_operations.py |
| `UpdateEventBus` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DeleteEventBus` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListEventBuses` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DescribeEventBus` | — | not yet | tests/control/test_eventbridge_operations.py |
| `PutRule` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DeleteRule` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListRules` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DescribeRule` | — | not yet | tests/control/test_eventbridge_operations.py |
| `EnableRule` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DisableRule` | — | not yet | tests/control/test_eventbridge_operations.py |
| `PutTargets` | — | not yet | tests/control/test_eventbridge_operations.py |
| `RemoveTargets` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListTargetsByRule` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListRuleNamesByTarget` | — | not yet | tests/control/test_eventbridge_operations.py |
| `PutEvents` | — | not yet | tests/control/test_eventbridge_operations.py |
| `TestEventPattern` | — | not yet | tests/control/test_eventbridge_operations.py |
| `TagResource` | — | not yet | tests/control/test_eventbridge_operations.py |
| `UntagResource` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_eventbridge_operations.py |
| `CreateArchive` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DeleteArchive` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DescribeArchive` | — | not yet | tests/control/test_eventbridge_operations.py |
| `UpdateArchive` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListArchives` | — | not yet | tests/control/test_eventbridge_operations.py |
| `PutPermission` | — | not yet | tests/control/test_eventbridge_operations.py |
| `RemovePermission` | — | not yet | tests/control/test_eventbridge_operations.py |
| `CreateConnection` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DescribeConnection` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DeleteConnection` | — | not yet | tests/control/test_eventbridge_operations.py |
| `UpdateConnection` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DeauthorizeConnection` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListConnections` | — | not yet | tests/control/test_eventbridge_operations.py |
| `CreateApiDestination` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DescribeApiDestination` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DeleteApiDestination` | — | not yet | tests/control/test_eventbridge_operations.py |
| `UpdateApiDestination` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListApiDestinations` | — | not yet | tests/control/test_eventbridge_operations.py |
| `StartReplay` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DescribeReplay` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListReplays` | — | not yet | tests/control/test_eventbridge_operations.py |
| `CancelReplay` | — | not yet | tests/control/test_eventbridge_operations.py |
| `CreateEndpoint` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DeleteEndpoint` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DescribeEndpoint` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListEndpoints` | — | not yet | tests/control/test_eventbridge_operations.py |
| `UpdateEndpoint` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ActivateEventSource` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DeactivateEventSource` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DescribeEventSource` | — | not yet | tests/control/test_eventbridge_operations.py |
| `CreatePartnerEventSource` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DeletePartnerEventSource` | — | not yet | tests/control/test_eventbridge_operations.py |
| `DescribePartnerEventSource` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListPartnerEventSources` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListPartnerEventSourceAccounts` | — | not yet | tests/control/test_eventbridge_operations.py |
| `ListEventSources` | — | not yet | tests/control/test_eventbridge_operations.py |
| `PutPartnerEvents` | — | not yet | tests/control/test_eventbridge_operations.py |

<!-- coverage:end -->
