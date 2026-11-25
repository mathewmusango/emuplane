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

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **98**
- Console actions (`/api/exec`, the create page): **121**
- Operations with an emuplane test: **98**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **98**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **34** of **34**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **98** · Console actions: **121**






## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateUser` | create-user | IAM users page › Create user | tests/control/test_iam_operations.py (users round trip); lab matrix in test_iam_policies.py, tests/control/test_signup_naming.py |
| `GetUser` | get-user | IAM API explorer | tests/control/test_iam_operations.py (users round trip) |
| `ListUsers` | list-users | IAM users page | tests/control/test_iam_operations.py (users round trip, listings page on MaxItems) |
| `DeleteUser` | delete-user | IAM users page › Delete user | tests/control/test_iam_operations.py (delete refuses while it carries state) |
| `CreateRole` | create-role | Roles page › Create role | tests/control/test_iam_operations.py (roles round trip) |
| `GetRole` | get-role | Roles page | tests/control/test_iam_operations.py (roles round trip) |
| `ListRoles` | list-roles | Roles page | tests/control/test_iam_operations.py (roles round trip) |
| `DeleteRole` | delete-role | Roles page › Delete | tests/control/test_iam_operations.py (roles round trip) |
| `UpdateRoleDescription` | update-role-description | IAM API explorer | tests/control/test_iam_operations.py (role description and boundary are updated) |
| `PutRolePermissionsBoundary` | put-role-permissions-boundary | IAM API explorer | tests/control/test_iam_operations.py (role description and boundary are updated) |
| `DeleteRolePermissionsBoundary` | delete-role-permissions-boundary | IAM API explorer | tests/control/test_iam_operations.py (role description and boundary are updated) |
| `PutUserPermissionsBoundary` | put-user-permissions-boundary | IAM API explorer | tests/control/test_iam_operations.py (permissions boundaries on a user) |
| `DeleteUserPermissionsBoundary` | delete-user-permissions-boundary | IAM API explorer | tests/control/test_iam_operations.py (permissions boundaries on a user) |
| `CreatePolicy` | create-policy | Policies page › Create policy | tests/control/test_iam_operations.py (managed policies round trip) |
| `GetPolicy` | get-policy | Policies page | tests/control/test_iam_operations.py (managed policies round trip) |
| `DeletePolicy` | delete-policy | Policies page › Delete | tests/control/test_iam_operations.py (managed policies round trip) |
| `AttachRolePolicy` | attach-role-policy | IAM API explorer | tests/control/test_iam_operations.py (managed policies attach and detach on a role) |
| `DetachRolePolicy` | detach-role-policy | IAM API explorer | tests/control/test_iam_operations.py (managed policies attach and detach on a role) |
| `PutRolePolicy` | put-role-policy | IAM API explorer | tests/control/test_iam_operations.py (role inline policies) |
| `GetRolePolicy` | get-role-policy | IAM API explorer | tests/control/test_iam_operations.py (role inline policies) |
| `DeleteRolePolicy` | delete-role-policy | IAM API explorer | tests/control/test_iam_operations.py (role inline policies) |
| `ListRolePolicies` | list-role-policies | IAM API explorer | tests/control/test_iam_operations.py (role inline policies) |
| `ListAttachedRolePolicies` | list-attached-role-policies | IAM API explorer | tests/control/test_iam_operations.py (managed policies attach and detach on a role) |
| `CreateAccessKey` | create-access-key | Security credentials page › Access keys › Create access key | tests/control/test_iam_operations.py (access key lifecycle); lab matrix in test_iam_policies.py |
| `ListAccessKeys` | list-access-keys | Security credentials page › Access keys; IAM users page › user details | tests/control/test_iam_operations.py (access key lifecycle) |
| `DeleteAccessKey` | delete-access-key | IAM API explorer | tests/control/test_iam_operations.py (access key lifecycle) |
| `UpdateAccessKey` | update-access-key | IAM API explorer | tests/control/test_iam_operations.py (access key lifecycle); lab matrix in test_iam_policies.py |
| `GetAccessKeyLastUsed` | get-access-key-last-used | IAM API explorer | tests/control/test_iam_operations.py (access key lifecycle) |
| `CreateInstanceProfile` | create-instance-profile | IAM API explorer | tests/control/test_iam_operations.py (instance profiles round trip) |
| `GetInstanceProfile` | get-instance-profile | IAM API explorer | tests/control/test_iam_operations.py (instance profiles round trip) |
| `DeleteInstanceProfile` | delete-instance-profile | IAM API explorer | tests/control/test_iam_operations.py (instance profiles round trip) |
| `AddRoleToInstanceProfile` | add-role-to-instance-profile | IAM API explorer | tests/control/test_iam_operations.py (instance profiles round trip) |
| `RemoveRoleFromInstanceProfile` | remove-role-from-instance-profile | IAM API explorer | tests/control/test_iam_operations.py (instance profiles round trip) |
| `ListInstanceProfiles` | list-instance-profiles | IAM API explorer | tests/control/test_iam_operations.py (instance profiles round trip) |
| `TagInstanceProfile` | tag-instance-profile | IAM API explorer | tests/control/test_iam_operations.py (instance profile tags) |
| `UntagInstanceProfile` | untag-instance-profile | IAM API explorer | tests/control/test_iam_operations.py (instance profile tags) |
| `ListInstanceProfileTags` | list-instance-profile-tags | IAM API explorer | tests/control/test_iam_operations.py (instance profile tags) |
| `CreateGroup` | create-group | IAM user groups page › Create group | tests/control/test_iam_operations.py (groups and membership); lab matrix in test_iam_policies.py |
| `GetGroup` | get-group | IAM user groups page | tests/control/test_iam_operations.py (groups and membership) |
| `AddUserToGroup` | add-user-to-group | IAM API explorer | tests/control/test_iam_operations.py (groups and membership); lab matrix in test_iam_policies.py |
| `RemoveUserFromGroup` | remove-user-from-group | IAM API explorer | tests/control/test_iam_operations.py (groups and membership) |
| `AttachGroupPolicy` | attach-group-policy | IAM API explorer | tests/control/test_iam_operations.py (group managed policies) |
| `DetachGroupPolicy` | detach-group-policy | IAM API explorer | tests/control/test_iam_operations.py (group managed policies) |
| `ListAttachedGroupPolicies` | list-attached-group-policies | IAM user groups page | tests/control/test_iam_operations.py (group managed policies) |
| `PutGroupPolicy` | put-group-policy | IAM API explorer | tests/control/test_iam_operations.py (group inline policies); lab matrix in test_iam_policies.py |
| `GetGroupPolicy` | get-group-policy | IAM API explorer | tests/control/test_iam_operations.py (group inline policies) |
| `DeleteGroupPolicy` | delete-group-policy | IAM API explorer | tests/control/test_iam_operations.py (group inline policies) |
| `ListGroupPolicies` | list-group-policies | IAM user groups page | tests/control/test_iam_operations.py (group inline policies) |
| `CreateServiceLinkedRole` | create-service-linked-role | IAM API explorer | tests/control/test_iam_operations.py (service-linked role lifecycle) |
| `DeleteServiceLinkedRole` | delete-service-linked-role | IAM API explorer | tests/control/test_iam_operations.py (service-linked role lifecycle) |
| `GetServiceLinkedRoleDeletionStatus` | get-service-linked-role-deletion-status | IAM API explorer | tests/control/test_iam_operations.py (service-linked role lifecycle) |
| `CreateOpenIDConnectProvider` | create-open-id-connect-provider | Identity providers page › Add provider | tests/control/test_iam_operations.py (OIDC provider is created and listed) |
| `ListOpenIDConnectProviders` | list-open-id-connect-providers | Identity providers page | tests/control/test_iam_operations.py (OIDC provider is created and listed) |
| `CreateSAMLProvider` | create-saml-provider | Identity providers page › Add provider | tests/control/test_iam_operations.py (SAML provider round trip) |
| `GetSAMLProvider` | get-saml-provider | IAM API explorer | tests/control/test_iam_operations.py (SAML provider round trip) |
| `ListSAMLProviders` | list-saml-providers | Identity providers page | tests/control/test_iam_operations.py (SAML provider round trip) |
| `UpdateSAMLProvider` | update-s-a-m-l-provider | IAM API explorer | tests/control/test_iam_operations.py (SAML provider round trip) |
| `DeleteSAMLProvider` | delete-saml-provider | Identity providers page › Delete | tests/control/test_iam_operations.py (SAML provider round trip) |
| `CreateLoginProfile` | create-login-profile | IAM API explorer | tests/control/test_iam_operations.py (login profile lifecycle) |
| `GetLoginProfile` | get-login-profile | IAM API explorer | tests/control/test_iam_operations.py (login profile lifecycle) |
| `UpdateLoginProfile` | update-login-profile | IAM API explorer | tests/control/test_iam_operations.py (login profile lifecycle) |
| `DeleteLoginProfile` | delete-login-profile | IAM API explorer | tests/control/test_iam_operations.py (login profile lifecycle) |
| `CreateVirtualMFADevice` | create-virtual-mfa-device | IAM Dashboard › Add MFA | tests/control/test_iam_operations.py (virtual MFA devices) |
| `EnableMFADevice` | enable-mfa-device | IAM Dashboard › Add MFA | tests/control/test_iam_operations.py (virtual MFA devices) |
| `DeactivateMFADevice` | deactivate-m-f-a-device | IAM API explorer | tests/control/test_iam_operations.py (virtual MFA devices) |
| `ResyncMFADevice` | resync-m-f-a-device | IAM API explorer | tests/control/test_iam_operations.py (virtual MFA devices) |
| `ListMFADevices` | list-mfa-devices | IAM users page; IAM Dashboard | tests/control/test_iam_operations.py (virtual MFA devices) |
| `ListVirtualMFADevices` | list-virtual-m-f-a-devices | IAM API explorer | tests/control/test_iam_operations.py (virtual MFA devices) |
| `DeleteVirtualMFADevice` | delete-virtual-m-f-a-device | IAM API explorer | tests/control/test_iam_operations.py (virtual MFA devices) |
| `GetAccountAuthorizationDetails` | get-account-authorization-details | IAM API explorer | tests/control/test_iam_operations.py (account authorization details reports every entity) |
| `GenerateServiceLastAccessedDetails` | generate-service-last-accessed-details | IAM API explorer | tests/control/test_iam_operations.py (service last accessed details) |
| `GetServiceLastAccessedDetails` | get-service-last-accessed-details | IAM API explorer | tests/control/test_iam_operations.py (service last accessed details) |
| `TagRole` | tag-role | IAM API explorer | tests/control/test_iam_operations.py (role tags) |
| `UntagRole` | untag-role | IAM API explorer | tests/control/test_iam_operations.py (role tags) |
| `TagUser` | tag-user | IAM API explorer | tests/control/test_iam_operations.py (users are tagged and untagged) |
| `UntagUser` | untag-user | IAM API explorer | tests/control/test_iam_operations.py (users are tagged and untagged) |
| `TagPolicy` | tag-policy | IAM API explorer | tests/control/test_iam_operations.py (policy tags) |
| `UntagPolicy` | untag-policy | IAM API explorer | tests/control/test_iam_operations.py (policy tags) |
| `GenerateCredentialReport` | generate-credential-report | Credential report page › Generate and download report | tests/control/test_iam_operations.py (credential report lists the account and its users) |
| `GetCredentialReport` | get-credential-report | Credential report page › Generate and download report | tests/control/test_iam_operations.py (credential report lists the account and its users) |
| `GetAccountSummary` | get-account-summary | IAM Dashboard › Security recommendations | tests/control/test_iam_operations.py (account summary reports counts) |
| `GetAccountPasswordPolicy` | get-account-password-policy | Account settings page › Password policy | tests/control/test_iam_operations.py (account password policy is read, updated and deleted) |
| `UpdateAccountPasswordPolicy` | update-account-password-policy | Account settings page › Password policy › Edit | tests/control/test_iam_operations.py (account password policy is read, updated and deleted) |
| `DeleteAccountPasswordPolicy` | delete-account-password-policy | Account settings page › Password policy › Delete policy | tests/control/test_iam_operations.py (account password policy is read, updated and deleted) |
| `ListAccountAliases` | list-account-aliases | IAM Dashboard › AWS account; Account settings › Account alias | tests/control/test_iam_operations.py (account aliases) |
| `CreateAccountAlias` | create-account-alias | Account settings page › Account alias | tests/control/test_iam_operations.py (account aliases) |
| `DeleteAccountAlias` | delete-account-alias | Account settings page › Account alias › Delete | tests/control/test_iam_operations.py (account aliases) |
| `CreateServiceSpecificCredential` | create-service-specific-credential | IAM API explorer | tests/control/test_iam_operations.py (service-specific credentials) |
| `ListServiceSpecificCredentials` | list-service-specific-credentials | IAM API explorer | tests/control/test_iam_operations.py (service-specific credentials) |
| `UpdateServiceSpecificCredential` | update-service-specific-credential | IAM API explorer | tests/control/test_iam_operations.py (service-specific credentials) |
| `ResetServiceSpecificCredential` | reset-service-specific-credential | IAM API explorer | tests/control/test_iam_operations.py (service-specific credentials) |
| `DeleteServiceSpecificCredential` | delete-service-specific-credential | IAM API explorer | tests/control/test_iam_operations.py (service-specific credentials) |
| `UploadServerCertificate` | upload-server-certificate | IAM API explorer | tests/control/test_iam_operations.py (server certificates round trip) |
| `ListServerCertificates` | list-server-certificates | IAM API explorer | tests/control/test_iam_operations.py (server certificates round trip) |
| `GetServerCertificate` | get-server-certificate | IAM API explorer | tests/control/test_iam_operations.py (server certificates round trip) |
| `UpdateServerCertificate` | update-server-certificate | IAM API explorer | tests/control/test_iam_operations.py (server certificates round trip) |
| `DeleteServerCertificate` | delete-server-certificate | IAM API explorer | tests/control/test_iam_operations.py (server certificates round trip) |
| `ListServerCertificateTags` | list-server-certificate-tags | IAM API explorer | tests/control/test_iam_operations.py (server certificate tags) |

<!-- coverage:end -->
