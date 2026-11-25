---
sidebar_position: 25
title: WAF v2 coverage
---

Every WAF v2 operation the emulator advertises, and what Emuplane does with it.
There is no console action: WebACLs, IP sets, regex pattern sets, rule groups,
associations and tags are managed over the wire. LockToken rotation is enforced
on the operations that check it and is always sent as a real client would.

The table is generated from the operation list; every row names the test that
exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **29**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **29**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **12**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **29** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateWebACL` | — | not yet | tests/control/test_wafv2_operations.py |
| `GetWebACL` | — | not yet | tests/control/test_wafv2_operations.py |
| `UpdateWebACL` | — | not yet | tests/control/test_wafv2_operations.py |
| `DeleteWebACL` | — | not yet | tests/control/test_wafv2_operations.py |
| `ListWebACLs` | — | not yet | tests/control/test_wafv2_operations.py |
| `AssociateWebACL` | — | not yet | tests/control/test_wafv2_operations.py |
| `DisassociateWebACL` | — | not yet | tests/control/test_wafv2_operations.py |
| `GetWebACLForResource` | — | not yet | tests/control/test_wafv2_operations.py |
| `ListResourcesForWebACL` | — | not yet | tests/control/test_wafv2_operations.py |
| `CreateIPSet` | — | not yet | tests/control/test_wafv2_operations.py |
| `GetIPSet` | — | not yet | tests/control/test_wafv2_operations.py |
| `UpdateIPSet` | — | not yet | tests/control/test_wafv2_operations.py |
| `DeleteIPSet` | — | not yet | tests/control/test_wafv2_operations.py |
| `ListIPSets` | — | not yet | tests/control/test_wafv2_operations.py |
| `CreateRegexPatternSet` | — | not yet | tests/control/test_wafv2_operations.py |
| `GetRegexPatternSet` | — | not yet | tests/control/test_wafv2_operations.py |
| `UpdateRegexPatternSet` | — | not yet | tests/control/test_wafv2_operations.py |
| `DeleteRegexPatternSet` | — | not yet | tests/control/test_wafv2_operations.py |
| `ListRegexPatternSets` | — | not yet | tests/control/test_wafv2_operations.py |
| `CreateRuleGroup` | — | not yet | tests/control/test_wafv2_operations.py |
| `GetRuleGroup` | — | not yet | tests/control/test_wafv2_operations.py |
| `UpdateRuleGroup` | — | not yet | tests/control/test_wafv2_operations.py |
| `DeleteRuleGroup` | — | not yet | tests/control/test_wafv2_operations.py |
| `ListRuleGroups` | — | not yet | tests/control/test_wafv2_operations.py |
| `TagResource` | — | not yet | tests/control/test_wafv2_operations.py |
| `UntagResource` | — | not yet | tests/control/test_wafv2_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_wafv2_operations.py |
| `CheckCapacity` | — | not yet | tests/control/test_wafv2_operations.py |
| `DescribeManagedRuleGroup` | — | not yet | tests/control/test_wafv2_operations.py |

<!-- coverage:end -->
