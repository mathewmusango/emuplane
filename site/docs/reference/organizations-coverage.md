---
sidebar_position: 39
title: Organizations coverage
---

Every Organizations operation the emulator advertises, and what Emuplane does with
it. The service speaks JSON (`AWSOrganizationsV20161128`), is signed with the
`organizations` credential scope, and has no console action.

A single-master-account organization is initialised on the first call. Its root
has `SERVICE_CONTROL_POLICY` enabled and the AWS-managed `p-FullAWSAccess`
attached. Accounts and organizational units are records; nested units carry a
`Path`, and `CreateAccount` answers a `CreateAccountStatus` that
`DescribeCreateAccountStatus` reads back.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **28**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **28**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **14**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **28** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `DescribeOrganization` | — | not yet | tests/control/test_organizations_operations.py |
| `ListRoots` | — | not yet | tests/control/test_organizations_operations.py |
| `ListAccounts` | — | not yet | tests/control/test_organizations_operations.py |
| `ListAccountsForParent` | — | not yet | tests/control/test_organizations_operations.py |
| `DescribeAccount` | — | not yet | tests/control/test_organizations_operations.py |
| `CreateAccount` | — | not yet | tests/control/test_organizations_operations.py |
| `DescribeCreateAccountStatus` | — | not yet | tests/control/test_organizations_operations.py |
| `MoveAccount` | — | not yet | tests/control/test_organizations_operations.py |
| `CloseAccount` | — | not yet | tests/control/test_organizations_operations.py |
| `CreateOrganizationalUnit` | — | not yet | tests/control/test_organizations_operations.py |
| `DescribeOrganizationalUnit` | — | not yet | tests/control/test_organizations_operations.py |
| `DeleteOrganizationalUnit` | — | not yet | tests/control/test_organizations_operations.py |
| `ListOrganizationalUnitsForParent` | — | not yet | tests/control/test_organizations_operations.py |
| `ListParents` | — | not yet | tests/control/test_organizations_operations.py |
| `CreatePolicy` | — | not yet | tests/control/test_organizations_operations.py |
| `DescribePolicy` | — | not yet | tests/control/test_organizations_operations.py |
| `UpdatePolicy` | — | not yet | tests/control/test_organizations_operations.py |
| `DeletePolicy` | — | not yet | tests/control/test_organizations_operations.py |
| `ListPolicies` | — | not yet | tests/control/test_organizations_operations.py |
| `AttachPolicy` | — | not yet | tests/control/test_organizations_operations.py |
| `DetachPolicy` | — | not yet | tests/control/test_organizations_operations.py |
| `ListPoliciesForTarget` | — | not yet | tests/control/test_organizations_operations.py |
| `ListTargetsForPolicy` | — | not yet | tests/control/test_organizations_operations.py |
| `EnablePolicyType` | — | not yet | tests/control/test_organizations_operations.py |
| `DisablePolicyType` | — | not yet | tests/control/test_organizations_operations.py |
| `TagResource` | — | not yet | tests/control/test_organizations_operations.py |
| `UntagResource` | — | not yet | tests/control/test_organizations_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_organizations_operations.py |

<!-- coverage:end -->
