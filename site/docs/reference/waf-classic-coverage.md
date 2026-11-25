---
sidebar_position: 24
title: WAF (Classic + Regional) coverage
---

WAF Classic and Regional are a minimal v1 stub. The emulator README summarises
this row rather than listing it, so the universe here is the 20 operations the
module implements explicitly: the 17 `List*` calls and `GetChangeToken` /
`GetChangeTokenStatus` / `GetPermissionPolicy`. The generic `Create*` /
`Update*` / `Delete*` / `Associate*` / `Put*` / tag families are stubs that mint
a ChangeToken; the tests pin them, but they have no enumerated operation names
and are not counted.

The table is generated from the operation list; every row names the test that
exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **20**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **20**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **20**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **20** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `ListActivatedRulesInRuleGroup` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListByteMatchSets` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListGeoMatchSets` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListIPSets` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListLoggingConfigurations` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListRateBasedRules` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListRegexMatchSets` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListRegexPatternSets` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListResourcesForWebACL` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListRuleGroups` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListRules` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListSizeConstraintSets` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListSqlInjectionMatchSets` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListSubscribedRuleGroups` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListWebACLs` | — | not yet | tests/control/test_waf_classic_operations.py |
| `ListXssMatchSets` | — | not yet | tests/control/test_waf_classic_operations.py |
| `GetChangeToken` | — | not yet | tests/control/test_waf_classic_operations.py |
| `GetChangeTokenStatus` | — | not yet | tests/control/test_waf_classic_operations.py |
| `GetPermissionPolicy` | — | not yet | tests/control/test_waf_classic_operations.py |

<!-- coverage:end -->
