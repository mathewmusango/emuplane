---
sidebar_position: 3
title: Beyond the emulator
---

The emulator answers AWS APIs. Emuplane adds what an emulator has no opinion
about: who is calling, which account a key belongs to, and which rules survive a
restart. This page lists those additions — its counterpart is
[Limits](../reference/limits.md), which lists what is deliberately *not* done.

Every entry names **where the rule lives**. When it says *control*, the emulator
knows nothing about it, so the rule is Emuplane's to keep and to document.

| What | Where | How it shows |
| --- | --- | --- |
| Accounts, users, sessions | control | sign-in, and the `emuplane-accounts` / `-users` / `-sessions` tables |
| Access key → account | gateway | an issued `AKIA…` key resolves through IAM; a 12-digit key *is* the account |
| Anonymous requests | gateway | `ListBuckets` with no resolvable key is `403 AccessDenied`, not the emulator's default-principal list |
| Tenancy isolation | control API | a session cannot read or act on another account's resources |
| Region opt-in | gateway | a region the account has not enabled is `403 AccessDenied` before the emulator is asked |
| Bucket-name uniqueness | gateway | one `409 BucketAlreadyExists`, whichever account or region asks |
| Name provenance | control | `emuplane-owners` records the principal behind a resource |
| **MFA delete** | control + gateway | a version delete or a versioning change needs `x-amz-mfa`; the bucket cannot be deleted while it is on — **not on the console yet** |
| Control API and bearer token | control | the console and automation share one API; the token is minted inside the container |
| Bootstrap stack | control | `bootstrap/` applies the `emuplane` CloudFormation stack that creates the tables |

## MFA delete, worked through

MFA delete is the clearest example of the split, because the emulator implements
the *field* and not the *rule*.

1. `PutBucketVersioning` accepts `<MfaDelete>` and answers `200`.
2. `GetBucketVersioning` never returns it, and no delete is ever refused.
3. So the control keeps the flag on the bucket's own record, and the API answers it
   as `mfa_delete_source: control`.
4. The **gateway** is what enforces it: a version delete or a versioning change
   without `x-amz-mfa` is `403`, and `DeleteBucket` is refused outright while the
   flag is on.
5. Enabling it **enables versioning in the same call**, because MFA delete only
   exists on a versioned bucket.
6. The console does not surface it yet — the control and the gateway stand ready
   for the day it is wanted as a page control again.

The two caveats — the code is not verified, and the gateway is the only place it
is enforced — are on the [Limits](../reference/limits.md#mfa-delete) page.

A test in `tests/control/test_parity.py` pins step 1 and 2 against the emulator
itself. If MiniStack ever returns `MfaDelete`, that test fails: the right move is
then to delete the control's flag, not to keep two answers.

## The rule for adding one

An addition is only worth keeping if it is **stated where it is enforced** and
**documented where a user will look**:

- the rule lives in exactly one component (gateway or control), never duplicated
  in both;
- the console labels the answer's source when it is not the emulator's;
- a page here says what it adds, and a line in [Limits](../reference/limits.md)
  says what it costs;
- a parity test pins the emulator behaviour the addition stands on.

Everything else the console shows is the emulator's own answer, read back rather
than cached — including the parts that look like convenience, such as folder
listings, `Load more objects` paging, creation dates and versioning state.
