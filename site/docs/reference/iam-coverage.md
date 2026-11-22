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
- Operations with an emuplane test: **98**
- Operations shown in the console: **5**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **2** of **34**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **98** · Console actions: **5**





## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateUser` | create-user | IAM page › API explorer, sign-up | tests/control/test_iam_operations.py (users round trip); lab matrix in test_iam_policies.py, tests/control/test_signup_naming.py |
| `GetUser` | — | not yet | tests/control/test_iam_operations.py (users round trip) |
| `ListUsers` | list-users | IAM page › API explorer | tests/control/test_iam_operations.py (users round trip, listings page on MaxItems) |
| `DeleteUser` | delete-user | IAM page › API explorer | tests/control/test_iam_operations.py (delete refuses while it carries state) |
| `CreateRole` | — | not yet | tests/control/test_iam_operations.py (roles round trip) |
| `GetRole` | — | not yet | tests/control/test_iam_operations.py (roles round trip) |
| `ListRoles` | — | not yet | tests/control/test_iam_operations.py (roles round trip) |
| `DeleteRole` | — | not yet | tests/control/test_iam_operations.py (roles round trip) |
| `UpdateRoleDescription` | — | not yet | tests/control/test_iam_operations.py (role description and boundary are updated) |
| `PutRolePermissionsBoundary` | — | not yet | tests/control/test_iam_operations.py (role description and boundary are updated) |
| `DeleteRolePermissionsBoundary` | — | not yet | tests/control/test_iam_operations.py (role description and boundary are updated) |
| `PutUserPermissionsBoundary` | — | not yet | tests/control/test_iam_operations.py (permissions boundaries on a user) |
| `DeleteUserPermissionsBoundary` | — | not yet | tests/control/test_iam_operations.py (permissions boundaries on a user) |
| `CreatePolicy` | — | not yet | tests/control/test_iam_operations.py (managed policies round trip) |
| `GetPolicy` | — | not yet | tests/control/test_iam_operations.py (managed policies round trip) |
| `DeletePolicy` | — | not yet | tests/control/test_iam_operations.py (managed policies round trip) |
| `AttachRolePolicy` | — | not yet | tests/control/test_iam_operations.py (managed policies attach and detach on a role) |
| `DetachRolePolicy` | — | not yet | tests/control/test_iam_operations.py (managed policies attach and detach on a role) |
| `PutRolePolicy` | — | not yet | tests/control/test_iam_operations.py (role inline policies) |
| `GetRolePolicy` | — | not yet | tests/control/test_iam_operations.py (role inline policies) |
| `DeleteRolePolicy` | — | not yet | tests/control/test_iam_operations.py (role inline policies) |
| `ListRolePolicies` | — | not yet | tests/control/test_iam_operations.py (role inline policies) |
| `ListAttachedRolePolicies` | — | not yet | tests/control/test_iam_operations.py (managed policies attach and detach on a role) |
| `CreateAccessKey` | create-access-key | Security credentials page › Access keys › Create access key | tests/control/test_iam_operations.py (access key lifecycle); lab matrix in test_iam_policies.py |
| `ListAccessKeys` | — | Security credentials page › Access keys | tests/control/test_iam_operations.py (access key lifecycle) |
| `DeleteAccessKey` | — | not yet | tests/control/test_iam_operations.py (access key lifecycle) |
| `UpdateAccessKey` | — | not yet | tests/control/test_iam_operations.py (access key lifecycle); lab matrix in test_iam_policies.py |
| `GetAccessKeyLastUsed` | — | not yet | tests/control/test_iam_operations.py (access key lifecycle) |
| `CreateInstanceProfile` | — | not yet | tests/control/test_iam_operations.py (instance profiles round trip) |
| `GetInstanceProfile` | — | not yet | tests/control/test_iam_operations.py (instance profiles round trip) |
| `DeleteInstanceProfile` | — | not yet | tests/control/test_iam_operations.py (instance profiles round trip) |
| `AddRoleToInstanceProfile` | — | not yet | tests/control/test_iam_operations.py (instance profiles round trip) |
| `RemoveRoleFromInstanceProfile` | — | not yet | tests/control/test_iam_operations.py (instance profiles round trip) |
| `ListInstanceProfiles` | — | not yet | tests/control/test_iam_operations.py (instance profiles round trip) |
| `TagInstanceProfile` | — | not yet | tests/control/test_iam_operations.py (instance profile tags) |
| `UntagInstanceProfile` | — | not yet | tests/control/test_iam_operations.py (instance profile tags) |
| `ListInstanceProfileTags` | — | not yet | tests/control/test_iam_operations.py (instance profile tags) |
| `CreateGroup` | — | not yet | tests/control/test_iam_operations.py (groups and membership); lab matrix in test_iam_policies.py |
| `GetGroup` | — | not yet | tests/control/test_iam_operations.py (groups and membership) |
| `AddUserToGroup` | — | not yet | tests/control/test_iam_operations.py (groups and membership); lab matrix in test_iam_policies.py |
| `RemoveUserFromGroup` | — | not yet | tests/control/test_iam_operations.py (groups and membership) |
| `AttachGroupPolicy` | — | not yet | tests/control/test_iam_operations.py (group managed policies) |
| `DetachGroupPolicy` | — | not yet | tests/control/test_iam_operations.py (group managed policies) |
| `ListAttachedGroupPolicies` | — | not yet | tests/control/test_iam_operations.py (group managed policies) |
| `PutGroupPolicy` | — | not yet | tests/control/test_iam_operations.py (group inline policies); lab matrix in test_iam_policies.py |
| `GetGroupPolicy` | — | not yet | tests/control/test_iam_operations.py (group inline policies) |
| `DeleteGroupPolicy` | — | not yet | tests/control/test_iam_operations.py (group inline policies) |
| `ListGroupPolicies` | — | not yet | tests/control/test_iam_operations.py (group inline policies) |
| `CreateServiceLinkedRole` | — | not yet | tests/control/test_iam_operations.py (service-linked role lifecycle) |
| `DeleteServiceLinkedRole` | — | not yet | tests/control/test_iam_operations.py (service-linked role lifecycle) |
| `GetServiceLinkedRoleDeletionStatus` | — | not yet | tests/control/test_iam_operations.py (service-linked role lifecycle) |
| `CreateOpenIDConnectProvider` | — | not yet | tests/control/test_iam_operations.py (OIDC provider is created and listed) |
| `ListOpenIDConnectProviders` | — | not yet | tests/control/test_iam_operations.py (OIDC provider is created and listed) |
| `CreateSAMLProvider` | — | not yet | tests/control/test_iam_operations.py (SAML provider round trip) |
| `GetSAMLProvider` | — | not yet | tests/control/test_iam_operations.py (SAML provider round trip) |
| `ListSAMLProviders` | — | not yet | tests/control/test_iam_operations.py (SAML provider round trip) |
| `UpdateSAMLProvider` | — | not yet | tests/control/test_iam_operations.py (SAML provider round trip) |
| `DeleteSAMLProvider` | — | not yet | tests/control/test_iam_operations.py (SAML provider round trip) |
| `CreateLoginProfile` | — | not yet | tests/control/test_iam_operations.py (login profile lifecycle) |
| `GetLoginProfile` | — | not yet | tests/control/test_iam_operations.py (login profile lifecycle) |
| `UpdateLoginProfile` | — | not yet | tests/control/test_iam_operations.py (login profile lifecycle) |
| `DeleteLoginProfile` | — | not yet | tests/control/test_iam_operations.py (login profile lifecycle) |
| `CreateVirtualMFADevice` | — | not yet | tests/control/test_iam_operations.py (virtual MFA devices) |
| `EnableMFADevice` | — | not yet | tests/control/test_iam_operations.py (virtual MFA devices) |
| `DeactivateMFADevice` | — | not yet | tests/control/test_iam_operations.py (virtual MFA devices) |
| `ResyncMFADevice` | — | not yet | tests/control/test_iam_operations.py (virtual MFA devices) |
| `ListMFADevices` | — | not yet | tests/control/test_iam_operations.py (virtual MFA devices) |
| `ListVirtualMFADevices` | — | not yet | tests/control/test_iam_operations.py (virtual MFA devices) |
| `DeleteVirtualMFADevice` | — | not yet | tests/control/test_iam_operations.py (virtual MFA devices) |
| `GetAccountAuthorizationDetails` | — | not yet | tests/control/test_iam_operations.py (account authorization details reports every entity) |
| `GenerateServiceLastAccessedDetails` | — | not yet | tests/control/test_iam_operations.py (service last accessed details) |
| `GetServiceLastAccessedDetails` | — | not yet | tests/control/test_iam_operations.py (service last accessed details) |
| `TagRole` | — | not yet | tests/control/test_iam_operations.py (role tags) |
| `UntagRole` | — | not yet | tests/control/test_iam_operations.py (role tags) |
| `TagUser` | — | not yet | tests/control/test_iam_operations.py (users are tagged and untagged) |
| `UntagUser` | — | not yet | tests/control/test_iam_operations.py (users are tagged and untagged) |
| `TagPolicy` | — | not yet | tests/control/test_iam_operations.py (policy tags) |
| `UntagPolicy` | — | not yet | tests/control/test_iam_operations.py (policy tags) |
| `GenerateCredentialReport` | — | not yet | tests/control/test_iam_operations.py (credential report lists the account and its users) |
| `GetCredentialReport` | — | not yet | tests/control/test_iam_operations.py (credential report lists the account and its users) |
| `GetAccountSummary` | — | not yet | tests/control/test_iam_operations.py (account summary reports counts) |
| `GetAccountPasswordPolicy` | — | not yet | tests/control/test_iam_operations.py (account password policy is read, updated and deleted) |
| `UpdateAccountPasswordPolicy` | — | not yet | tests/control/test_iam_operations.py (account password policy is read, updated and deleted) |
| `DeleteAccountPasswordPolicy` | — | not yet | tests/control/test_iam_operations.py (account password policy is read, updated and deleted) |
| `ListAccountAliases` | — | not yet | tests/control/test_iam_operations.py (account aliases) |
| `CreateAccountAlias` | — | not yet | tests/control/test_iam_operations.py (account aliases) |
| `DeleteAccountAlias` | — | not yet | tests/control/test_iam_operations.py (account aliases) |
| `CreateServiceSpecificCredential` | — | not yet | tests/control/test_iam_operations.py (service-specific credentials) |
| `ListServiceSpecificCredentials` | — | not yet | tests/control/test_iam_operations.py (service-specific credentials) |
| `UpdateServiceSpecificCredential` | — | not yet | tests/control/test_iam_operations.py (service-specific credentials) |
| `ResetServiceSpecificCredential` | — | not yet | tests/control/test_iam_operations.py (service-specific credentials) |
| `DeleteServiceSpecificCredential` | — | not yet | tests/control/test_iam_operations.py (service-specific credentials) |
| `UploadServerCertificate` | — | not yet | tests/control/test_iam_operations.py (server certificates round trip) |
| `ListServerCertificates` | — | not yet | tests/control/test_iam_operations.py (server certificates round trip) |
| `GetServerCertificate` | — | not yet | tests/control/test_iam_operations.py (server certificates round trip) |
| `UpdateServerCertificate` | — | not yet | tests/control/test_iam_operations.py (server certificates round trip) |
| `DeleteServerCertificate` | — | not yet | tests/control/test_iam_operations.py (server certificates round trip) |
| `ListServerCertificateTags` | — | not yet | tests/control/test_iam_operations.py (server certificate tags) |

<!-- coverage:end -->
