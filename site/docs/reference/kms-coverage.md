---
sidebar_position: 40
title: KMS coverage
---

Every KMS operation the emulator advertises, and what Emuplane does with it. The
service speaks JSON (`TrentService`), is signed with the `kms` credential scope,
and has no console action.

Symmetric encryption is an emulation — a key-derived pad, not AES — while
asymmetric signing, MACs and data key pairs use the real `cryptography`
primitives. Imported key material follows AWS's own wrap-and-import flow.
Multi-Region keys share their material between regions, grants are stored and
listed but not evaluated, and tags, policies, rotation and scheduled deletion are
key records.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **41**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **41**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **10**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **41** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateKey` | — | not yet | tests/control/test_kms_operations.py |
| `ReplicateKey` | — | not yet | tests/control/test_kms_operations.py |
| `ListKeys` | — | not yet | tests/control/test_kms_operations.py |
| `DescribeKey` | — | not yet | tests/control/test_kms_operations.py |
| `GetPublicKey` | — | not yet | tests/control/test_kms_operations.py |
| `Sign` | — | not yet | tests/control/test_kms_operations.py |
| `Verify` | — | not yet | tests/control/test_kms_operations.py |
| `Encrypt` | — | not yet | tests/control/test_kms_operations.py |
| `Decrypt` | — | not yet | tests/control/test_kms_operations.py |
| `GenerateMac` | — | not yet | tests/control/test_kms_operations.py |
| `VerifyMac` | — | not yet | tests/control/test_kms_operations.py |
| `GenerateDataKey` | — | not yet | tests/control/test_kms_operations.py |
| `GenerateDataKeyWithoutPlaintext` | — | not yet | tests/control/test_kms_operations.py |
| `GenerateDataKeyPair` | — | not yet | tests/control/test_kms_operations.py |
| `GenerateDataKeyPairWithoutPlaintext` | — | not yet | tests/control/test_kms_operations.py |
| `GenerateRandom` | — | not yet | tests/control/test_kms_operations.py |
| `CreateAlias` | — | not yet | tests/control/test_kms_operations.py |
| `DeleteAlias` | — | not yet | tests/control/test_kms_operations.py |
| `ListAliases` | — | not yet | tests/control/test_kms_operations.py |
| `UpdateAlias` | — | not yet | tests/control/test_kms_operations.py |
| `UpdateKeyDescription` | — | not yet | tests/control/test_kms_operations.py |
| `EnableKeyRotation` | — | not yet | tests/control/test_kms_operations.py |
| `DisableKeyRotation` | — | not yet | tests/control/test_kms_operations.py |
| `GetKeyRotationStatus` | — | not yet | tests/control/test_kms_operations.py |
| `GetKeyPolicy` | — | not yet | tests/control/test_kms_operations.py |
| `PutKeyPolicy` | — | not yet | tests/control/test_kms_operations.py |
| `ListKeyPolicies` | — | not yet | tests/control/test_kms_operations.py |
| `EnableKey` | — | not yet | tests/control/test_kms_operations.py |
| `DisableKey` | — | not yet | tests/control/test_kms_operations.py |
| `ScheduleKeyDeletion` | — | not yet | tests/control/test_kms_operations.py |
| `CancelKeyDeletion` | — | not yet | tests/control/test_kms_operations.py |
| `TagResource` | — | not yet | tests/control/test_kms_operations.py |
| `UntagResource` | — | not yet | tests/control/test_kms_operations.py |
| `ListResourceTags` | — | not yet | tests/control/test_kms_operations.py |
| `GetParametersForImport` | — | not yet | tests/control/test_kms_operations.py |
| `ImportKeyMaterial` | — | not yet | tests/control/test_kms_operations.py |
| `DeleteImportedKeyMaterial` | — | not yet | tests/control/test_kms_operations.py |
| `CreateGrant` | — | not yet | tests/control/test_kms_operations.py |
| `ListGrants` | — | not yet | tests/control/test_kms_operations.py |
| `RevokeGrant` | — | not yet | tests/control/test_kms_operations.py |
| `RetireGrant` | — | not yet | tests/control/test_kms_operations.py |

<!-- coverage:end -->
