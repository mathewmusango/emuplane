---
sidebar_position: 4
title: IAM coverage
---

Every IAM operation the emulator advertises, and what Emuplane does with it. IAM is
the identity layer the gateway resolves an access key against, so this page is
about more than a UI: an identity policy decides what S3 answers a key.

The table is generated from the emulator's own operation list. The console column
names the page or API explorer entry that reaches an operation; a dash under
*Emuplane test* means nothing in this repository exercises it yet.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

- Operations upstream advertises: **98**
- Console actions (`/api/exec`, the create page): **5**
- Operations with an emuplane test: **6**
- Operations shown in the console: **5**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **2** of **34**
- Operations with no emuplane test: **92**

- Group: **Core** · operations: **98** · Console actions: **5**





## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateUser` | create-user | IAM page › API explorer, sign-up | tests/control/test_iam_policies.py (lab matrix), tests/control/test_signup_naming.py |
| `GetUser` | — | not yet | — |
| `ListUsers` | list-users | IAM page › API explorer | — |
| `DeleteUser` | delete-user | IAM page › API explorer | — |
| `CreateRole` | — | not yet | — |
| `GetRole` | — | not yet | — |
| `ListRoles` | — | not yet | — |
| `DeleteRole` | — | not yet | — |
| `UpdateRoleDescription` | — | not yet | — |
| `PutRolePermissionsBoundary` | — | not yet | — |
| `DeleteRolePermissionsBoundary` | — | not yet | — |
| `PutUserPermissionsBoundary` | — | not yet | — |
| `DeleteUserPermissionsBoundary` | — | not yet | — |
| `CreatePolicy` | — | not yet | — |
| `GetPolicy` | — | not yet | — |
| `DeletePolicy` | — | not yet | — |
| `AttachRolePolicy` | — | not yet | — |
| `DetachRolePolicy` | — | not yet | — |
| `PutRolePolicy` | — | not yet | — |
| `GetRolePolicy` | — | not yet | — |
| `DeleteRolePolicy` | — | not yet | — |
| `ListRolePolicies` | — | not yet | — |
| `ListAttachedRolePolicies` | — | not yet | — |
| `CreateAccessKey` | create-access-key | Security credentials page › Access keys › Create access key | tests/control/test_iam_policies.py (lab matrix) |
| `ListAccessKeys` | — | Security credentials page › Access keys | — |
| `DeleteAccessKey` | — | not yet | — |
| `UpdateAccessKey` | — | not yet | tests/control/test_iam_policies.py (inactive key) |
| `GetAccessKeyLastUsed` | — | not yet | — |
| `CreateInstanceProfile` | — | not yet | — |
| `GetInstanceProfile` | — | not yet | — |
| `DeleteInstanceProfile` | — | not yet | — |
| `AddRoleToInstanceProfile` | — | not yet | — |
| `RemoveRoleFromInstanceProfile` | — | not yet | — |
| `ListInstanceProfiles` | — | not yet | — |
| `TagInstanceProfile` | — | not yet | — |
| `UntagInstanceProfile` | — | not yet | — |
| `ListInstanceProfileTags` | — | not yet | — |
| `CreateGroup` | — | not yet | tests/control/test_iam_policies.py (group policy) |
| `GetGroup` | — | not yet | — |
| `AddUserToGroup` | — | not yet | tests/control/test_iam_policies.py (group policy) |
| `RemoveUserFromGroup` | — | not yet | — |
| `AttachGroupPolicy` | — | not yet | — |
| `DetachGroupPolicy` | — | not yet | — |
| `ListAttachedGroupPolicies` | — | not yet | — |
| `PutGroupPolicy` | — | not yet | tests/control/test_iam_policies.py (group policy) |
| `GetGroupPolicy` | — | not yet | — |
| `DeleteGroupPolicy` | — | not yet | — |
| `ListGroupPolicies` | — | not yet | — |
| `CreateServiceLinkedRole` | — | not yet | — |
| `DeleteServiceLinkedRole` | — | not yet | — |
| `GetServiceLinkedRoleDeletionStatus` | — | not yet | — |
| `CreateOpenIDConnectProvider` | — | not yet | — |
| `ListOpenIDConnectProviders` | — | not yet | — |
| `CreateSAMLProvider` | — | not yet | — |
| `GetSAMLProvider` | — | not yet | — |
| `ListSAMLProviders` | — | not yet | — |
| `UpdateSAMLProvider` | — | not yet | — |
| `DeleteSAMLProvider` | — | not yet | — |
| `CreateLoginProfile` | — | not yet | — |
| `GetLoginProfile` | — | not yet | — |
| `UpdateLoginProfile` | — | not yet | — |
| `DeleteLoginProfile` | — | not yet | — |
| `CreateVirtualMFADevice` | — | not yet | — |
| `EnableMFADevice` | — | not yet | — |
| `DeactivateMFADevice` | — | not yet | — |
| `ResyncMFADevice` | — | not yet | — |
| `ListMFADevices` | — | not yet | — |
| `ListVirtualMFADevices` | — | not yet | — |
| `DeleteVirtualMFADevice` | — | not yet | — |
| `GetAccountAuthorizationDetails` | — | not yet | — |
| `GenerateServiceLastAccessedDetails` | — | not yet | — |
| `GetServiceLastAccessedDetails` | — | not yet | — |
| `TagRole` | — | not yet | — |
| `UntagRole` | — | not yet | — |
| `TagUser` | — | not yet | — |
| `UntagUser` | — | not yet | — |
| `TagPolicy` | — | not yet | — |
| `UntagPolicy` | — | not yet | — |
| `GenerateCredentialReport` | — | not yet | — |
| `GetCredentialReport` | — | not yet | — |
| `GetAccountSummary` | — | not yet | — |
| `GetAccountPasswordPolicy` | — | not yet | — |
| `UpdateAccountPasswordPolicy` | — | not yet | — |
| `DeleteAccountPasswordPolicy` | — | not yet | — |
| `ListAccountAliases` | — | not yet | — |
| `CreateAccountAlias` | — | not yet | — |
| `DeleteAccountAlias` | — | not yet | — |
| `CreateServiceSpecificCredential` | — | not yet | — |
| `ListServiceSpecificCredentials` | — | not yet | — |
| `UpdateServiceSpecificCredential` | — | not yet | — |
| `ResetServiceSpecificCredential` | — | not yet | — |
| `DeleteServiceSpecificCredential` | — | not yet | — |
| `UploadServerCertificate` | — | not yet | — |
| `ListServerCertificates` | — | not yet | — |
| `GetServerCertificate` | — | not yet | — |
| `UpdateServerCertificate` | — | not yet | — |
| `DeleteServerCertificate` | — | not yet | — |
| `ListServerCertificateTags` | — | not yet | — |

<!-- coverage:end -->
