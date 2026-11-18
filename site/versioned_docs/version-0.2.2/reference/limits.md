---
sidebar_position: 4
title: Limits
---

What this control plane does not do, stated so it is not discovered at the worst
moment. Every entry here was measured, not guessed. The counterpart page is
[Beyond the emulator](../concepts/extensions.md): what Emuplane adds on top of the
emulator, and where each of those rules lives.

## The gateway

- **Request and response bodies are buffered** — no streaming. Fine for state
  files and API payloads, not for multi-gigabyte object transfers.
- **Responses that embed a node's own endpoint** (an API Gateway `execute-api`
  URL, for example) point at that node directly and bypass the gateway.
- **Account root keys are accepted with any secret, by design.** A 12-digit
  access key is that account's root; only issued `AKIA…` keys are verified by IAM.
  The control's own tokens authenticate the console, not AWS.
- **An anonymous `ListBuckets` is refused.** The gateway answers `403 AccessDenied`
  when no access key resolves: `ListBuckets` is account-scoped, so the emulator's
  anonymous gate — which is bucket-scoped — never sees it, and would answer with
  the default principal's list.
- **Anything the gateway enforces, it enforces only there** — tenancy, region
  enablement and MFA delete are not enforced for a client that reaches the
  emulator directly. The shipped composition publishes no emulator port for that
  reason; a lab that publishes `4566` reopens the hole.

## The S3 console

- **Uploads take one file at a time, up to 200 MiB.** A file of 8 MiB or less is
  a single request; above that it is a multipart upload in 5 MiB parts, and one
  request body over 25 MiB is refused with `413`.
- **No S3 Metrics, Storage Lens or directory buckets** — the emulator has no
  backend for them, so there is no page to show.
- **`WriteGetObjectResponse` is not a console action.** It is the Lambda runtime's
  callback, and needs an in-flight Object Lambda request's route token.
- **Versioning can be suspended, never disabled.** That is S3's rule, not this
  console's: the card says *Suspended* because that is the state S3 reports.
- **Bucket ABAC is not shown at all.** The endpoint answers no ABAC status
  (`GetBucketAbac`/`PutBucketAbac` do not exist in its S3 router) and evaluates
  `aws:ResourceTag/…` conditions directly, so there is nothing to read and nothing
  to turn on. The console draws no panel rather than a card that explains its own
  uselessness; the control returns as a switch on the Properties tab once the
  endpoint answers an ABAC status.
- **The object ACL dialog acts on one version at a time.** `GetObjectAcl` and
  `PutObjectAcl` accept a `versionId`, and the dialog offers the key's older
  versions beside *Current version*. It does not show every grant on every version
  at once, and a delete marker's own ACL is not reachable.
- **Accelerate, request payment and bucket location have no page.** All three
  answer on the endpoint (measured on the lab), but none would change anything a
  user can see: there is no accelerated endpoint to point at, request payment
  bills nobody in an emulator, and the region is already read from `HeadBucket`.
- **The Versions card lists the subtree, not one level.** `ListObjectVersions` is
  asked with the folder's prefix and no delimiter, so every version beneath the
  folder is listed; the Objects tab beside it still shows one level at a time.
- **An Object Lambda configuration that declares a DTD is refused.** The control
  parses that document with `defusedxml`, which rejects a `<!DOCTYPE` or an
  `<!ENTITY` instead of expanding it, and the console says *the configuration is
  not XML*. S3 Control's own documents never carry a DTD.
- **An incomplete upload can be aborted here, not completed.** Completing it is the
  job of the client that opened it and holds the part list it will send; the console
  shows the parts S3 lists and offers only the abort.
- Coverage is the [S3 coverage](s3-coverage.md) page: an operation that is not
  listed there is not claimed. Nine operations the console drives are absent from
  the emulator's advertised S3 row although it answers them —
  `ListMultipartUploads`, `ListParts`, `GetObjectAcl`, `PutObjectAcl`, the three
  website operations and the two ownership-controls operations — so they are named
  on that page instead of as rows, and `tests/control/test_api.py` pins each
  against the emulator.

## MFA delete

MFA delete is implemented in the control and enforced at the gateway, but it is
**not surfaced on the console**: the Properties tab shows versioning without an MFA
delete row, and the create page does not offer it. The mechanism stays, so turning
it back on is a UI change rather than a rebuild.

It exists in Emuplane at all because the emulator accepts `MfaDelete` on
`PutBucketVersioning` and never answers it on `GetBucketVersioning`; the control
holds the flag on the bucket's own record and the gateway enforces it.

- **The code is not verified.** The guard asks for the `x-amz-mfa` header, not for
  a valid one — no MFA device is enrolled in this control plane.
- **It is enforced at the gateway only**, so a client that reaches the emulator
  directly is not guarded (see above).
- **A version delete or a versioning change needs the header; a bucket delete is
  refused outright.** No standard tool can put a code on `DeleteBucket`, so a
  bucket under MFA delete has to have the flag turned off before it can be
  removed. That is stricter than AWS, which does not name `DeleteBucket` under MFA
  delete — it is deliberate, so the flag cannot be sidestepped by deleting the
  bucket.
- **It guards versions, not keys.** A plain `DeleteObject` still succeeds and
  writes a delete marker, exactly as S3 behaves.
- **The console does not ask for a code.** It acts as the account root, which is
  the credential AWS requires for this change anyway.

## Sign-in

- **MFA enrolment is not implemented.** The sign-in flow has the screen and the
  API has the route, but `POST /api/auth/mfa` answers `501`, and signing in a
  principal that already has MFA enabled is refused with the same message. The
  contract is deliberately in place; the enrolment flow is not built. That gap is
  also why the MFA delete guard above checks for the header's presence rather
  than its code: there is no enrolled device to check it against.

## The emulator

- **Only MiniStack is tested**, currently pinned to `1.5.40-full`. The backend
  profile table keeps `generic` and `ministack`; other emulators are unverified
  placeholders, not supported targets.
- **The emulator is a local lab.** Nothing here is a substitute for a real AWS
  account, and no credential leaves the host.

### Operations MiniStack 1.5.40 does not implement

Checked against its S3 dispatcher, not against its README. These have no handler:
most fall through to a plain bucket or object request, and the console therefore
has no page for them. They come back as console features the day the endpoint
answers them.

| Area | Missing |
| --- | --- |
| Bucket analytics, inventory, metrics, Intelligent-Tiering | the `…Configuration` family (`?analytics`, `?inventory`, `?metrics`, `?intelligent-tiering`) |
| Bucket policy status | `GetBucketPolicyStatus` (`?policyStatus`) |
| Bucket ABAC | `GetBucketAbac` / `PutBucketAbac` (`?abac`) |
| S3 Metadata | `Create`/`Get`/`DeleteBucketMetadataTableConfiguration` (`?metadataTable`) |
| S3 Express directory buckets | `CreateSession`, `ListDirectoryBuckets`, `RenameObject` |
| Object selection | `SelectObjectContent` (`?select`) |
| BitTorrent | `GetObjectTorrent` (`?torrent`) |
| Per-object encryption update | `UpdateObjectEncryption` (object-level `?encryption`) |
| S3 Control Batch Operations | `/v20180820/jobs` |
| S3 Storage Lens | no API surface at all |
| **MFA delete** | accepted on `PutBucketVersioning` and dropped — no read, no enforcement; Emuplane keeps it (see above) |

Everything else the console shows is answered by the emulator, including
`RestoreObject`, object attributes, object annotations, legal hold and retention,
replication, notifications, logging, website, accelerate, request payment,
ownership controls, access points, Multi-Region access points and Object Lambda.

**A missing operation rarely says so.** Only `SelectObjectContent` answers a clean
refusal (`405 MethodNotAllowed`). Every other unknown subresource **falls through
to the default operation**: a bucket GET is answered as a plain listing (`200`,
a `ListBucketResult`), and an object GET as the object's own bytes (`200`). So a
`200` is not evidence a feature exists — read the document, never the status. That
fall-through is why `?abac` and `?policyStatus` cannot be probed by asking once:
the console shows no panel for them because there is no document to read.

### How the emulator decides an S3 authorisation

Measured against a two-account lab (`qa/bucket-policy-matrix.md`); the cells are
re-run by `tests/control/test_bucket_policies.py`.

- **Cross-account access is granted to the account ARN, not the user ARN.** A bucket
  policy whose `Principal` names `arn:aws:iam::<other>:user/x` is not matched;
  naming `arn:aws:iam::<other>:root` is.
- **Cross-account needs both sides:** the bucket policy *and* the caller's identity
  policy must allow. In the owner's account either one is enough — but a statement
  naming only the account delegates to identity policies, while one naming the user
  does not.
- **An explicit `Deny` wins**, in either policy, including over a same-account
  identity `Allow`.

## Addressing

S3 buckets are region-scoped: `ListBuckets` answers per region, and a request
signed for the wrong region gets the `301` AWS returns.

Use **path-style** S3 addressing (`s3_use_path_style = true` in Terraform).
Virtual-hosted requests are parsed best-effort; presigned SigV4 credentials in the
query string are honoured.
