---
sidebar_position: 2
title: S3 coverage
---

Every S3 operation the emulator advertises, and what Emuplane does with it. The
rule is simple and it is enforced on every test run: **an operation with no test
fails the build**, and an operation the console cannot reach is marked as such
rather than quietly omitted.

Two columns matter:

- **Shown in the console** — a page performs or displays it. An em dash means the
  operation works over the wire and nowhere in the UI.
- **Emuplane test** — the test that exercises it, in this version.

The table is generated in the implementation repository and copied here, so what
you read is what the ledger says:

```bash
npm run s3:coverage   # reads <control>/S3.md
```

<!-- coverage:begin -->

- Operations upstream advertises: **84**
- Console actions (`/api/exec`, the create page): **5**
- Operations with an emuplane test: **84**
- Operations shown in the console: **63**
- GET operations (Get/List/Head/Describe) shown in the console: **35** of **35**
- Operations with no emuplane test: **0**

## Buckets and objects

| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateBucket` | create-bucket | Buckets page › Create bucket | tests/s3/test_create.py, tests/control/test_gateway.py, tests/control/test_parity.py |
| `DeleteBucket` | delete-bucket | Buckets page › Delete | tests/control/test_gateway.py, tests/control/test_parity.py |
| `ListBuckets` | Buckets page | Buckets page › table | tests/control/test_api.py (via /api/browse), tests/control/test_parity.py |
| `HeadBucket` | Bucket page (region check) | Bucket page (HeadBucket decides the region) | tests/control/test_gateway.py (301 path), tests/s3/test_objects.py, tests/control/test_api.py |
| `PutObject` | put-object | Bucket page › Objects › Upload | tests/control/test_api.py, tests/s3/test_objects.py, tests/control/test_parity.py, tests/control/test_object_upload.py |
| `GetObject` | Bucket page (Objects) | Bucket page › Objects › open | tests/s3/test_objects.py, tests/control/test_parity.py, tests/control/test_object_upload.py |
| `DeleteObject` | delete-object | Bucket page › Objects › open › Delete | tests/web/s3.test.jsx (object view), tests/s3/test_catalogue.py, tests/control/test_parity.py |
| `HeadObject` | Bucket page (Objects) | Bucket page › Objects › open (size, ETag, last modified) | tests/control/test_gateway.py (301 path), tests/s3/test_objects.py (HEAD first), tests/control/test_api.py |
| `CopyObject` | Bucket page (Objects) | Bucket page › Objects › open › Copy | tests/s3/test_objects.py, tests/control/test_api.py, tests/web/s3.test.jsx |
| `ListObjects v1/v2` | list-objects | Bucket page › Objects | tests/control/test_api.py (v2), tests/control/test_parity.py, tests/s3/test_objects.py (v1) |
| `DeleteObjects` | delete-object | Buckets page › Empty | tests/s3/test_objects.py (Empty) |

## Bucket configuration

| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `GetBucketVersioning` | Bucket page (Properties) | Bucket page › Properties | tests/s3/test_create.py |
| `PutBucketVersioning` | Bucket page (Properties, Edit) | Bucket page › Properties › Edit | tests/s3/test_create.py, tests/control/test_api.py, tests/web/s3.test.jsx |
| `GetBucketEncryption` | Bucket page (Properties) | Bucket page › Properties | tests/s3/test_create.py, tests/control/test_api.py |
| `PutBucketEncryption` | Bucket page (Properties, Edit) | Bucket page › Properties › Edit | tests/s3/test_create.py, tests/s3/test_objects.py, tests/control/test_api.py, tests/web/s3.test.jsx |
| `DeleteBucketEncryption` | — | Bucket page › Properties › Remove default encryption | tests/s3/test_objects.py, tests/control/test_api.py, tests/web/s3.test.jsx |
| `GetBucketLifecycleConfiguration` | Bucket page (Configuration documents) | Bucket page › Configuration documents | tests/s3/test_objects.py (documents) |
| `PutBucketLifecycleConfiguration` | Bucket page (Configuration documents, Edit) | Bucket page › Configuration documents › Edit | tests/s3/test_objects.py (lifecycle round trip), tests/control/test_api.py (cors), tests/web/s3.test.jsx |
| `DeleteBucketLifecycle` | Bucket page (Configuration documents, Remove) | Bucket page › Configuration documents › Remove | tests/s3/test_objects.py (lifecycle round trip) |
| `GetBucketCors` | Bucket page (Configuration documents) | Bucket page › Configuration documents | tests/s3/test_objects.py (documents) |
| `PutBucketCors` | Bucket page (Configuration documents, Edit) | Bucket page › Configuration documents › Edit | tests/s3/test_objects.py (cors round trip), tests/control/test_api.py, tests/web/s3.test.jsx |
| `DeleteBucketCors` | Bucket page (Configuration documents, Remove) | Bucket page › Configuration documents › Remove | tests/s3/test_objects.py (cors round trip), tests/control/test_api.py |
| `GetBucketAcl` | Bucket page (Configuration documents) | Bucket page › Configuration documents | tests/s3/test_objects.py (documents), tests/control/test_api.py |
| `PutBucketAcl` | Bucket page (Configuration documents, Edit) | Bucket page › Configuration documents › Edit (ACL-enabled buckets) | tests/s3/test_objects.py (ACL enabled/disabled), tests/web/s3.test.jsx |
| `GetBucketTagging` | Bucket page (Properties) | Bucket page › Properties | tests/s3/test_create.py, tests/control/test_api.py |
| `PutBucketTagging` | Create page (tags) | Bucket page › Properties › Tags › Edit | tests/s3/test_create.py, tests/s3/test_objects.py, tests/control/test_api.py, tests/web/s3.test.jsx |
| `DeleteBucketTagging` | Bucket page (Properties, Remove tags) | Bucket page › Properties › Tags › Remove tags | tests/s3/test_objects.py, tests/control/test_api.py, tests/web/s3.test.jsx |
| `GetBucketPolicy` | Bucket page (Configuration documents) | Bucket page › Configuration documents | tests/s3/test_objects.py (documents), tests/control/test_api.py |
| `PutBucketPolicy` | Bucket page (Configuration documents, Edit) | Bucket page › Configuration documents › Edit | tests/s3/test_objects.py (policy round trip), tests/control/test_api.py, tests/web/s3.test.jsx |
| `DeleteBucketPolicy` | Bucket page (Configuration documents, Remove) | Bucket page › Configuration documents › Remove | tests/s3/test_objects.py (policy round trip), tests/control/test_api.py |
| `GetBucketNotificationConfiguration` | Bucket page (Configuration documents) | Bucket page › Configuration documents | tests/s3/test_objects.py (documents) |
| `PutBucketNotificationConfiguration` | — | — | tests/s3/test_operations.py (EventBridge rule) |
| `GetBucketLogging` | Bucket page (Configuration documents) | Bucket page › Configuration documents | tests/s3/test_objects.py (documents) |
| `PutBucketLogging` | — | — | tests/s3/test_operations.py (logging written and read) |
| `PutPublicAccessBlock` | Bucket page (Permissions, Save) | Bucket page › Permissions › Save | tests/s3/test_create.py |
| `GetPublicAccessBlock` | Bucket page (Permissions) | Bucket page › Permissions | tests/s3/test_create.py |
| `DeletePublicAccessBlock` | — | — | tests/s3/test_operations.py (access block removed) |

## Objects in depth

| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `ListObjectVersions` | Bucket page (Configuration documents) | Bucket page › Configuration documents | tests/s3/test_objects.py |
| `CreateMultipartUpload` | — | — | tests/s3/test_operations.py (multipart) |
| `UploadPart` | — | — | tests/s3/test_operations.py (multipart) |
| `CompleteMultipartUpload` | — | — | tests/s3/test_operations.py (multipart) |
| `AbortMultipartUpload` | — | — | tests/s3/test_operations.py (multipart aborted) |
| `GetObjectTagging` | — | Bucket page › Objects › open › Tags | tests/s3/test_operations.py (object tags) |
| `PutObjectTagging` | — | — | tests/s3/test_operations.py (object tags) |
| `DeleteObjectTagging` | — | — | tests/s3/test_operations.py (object tags) |
| `PutObjectAnnotation` | — | — | tests/s3/test_operations.py (annotations) |
| `GetObjectAnnotation` | — | Bucket page › Objects › open › Annotations › name | tests/s3/test_operations.py (annotations) |
| `ListObjectAnnotations` | — | Bucket page › Objects › open › Annotations | tests/s3/test_operations.py (annotations) |
| `DeleteObjectAnnotation` | — | — | tests/s3/test_operations.py (annotations) |

## Object Lock

| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `PutObjectLockConfiguration` | Create page (Object Lock) | Create bucket page › Object Lock | tests/s3/test_create.py (at create) |
| `GetObjectLockConfiguration` | Create page (Copy settings) | Create bucket page › Copy settings | tests/s3/test_create.py |
| `PutObjectRetention` | — | — | tests/s3/test_operations.py (retention) |
| `GetObjectRetention` | — | Bucket page › Objects › open › Object Lock | tests/s3/test_operations.py (retention) |
| `PutObjectLegalHold` | — | — | tests/s3/test_operations.py (legal hold) |
| `GetObjectLegalHold` | — | Bucket page › Objects › open › Object Lock | tests/s3/test_operations.py (legal hold) |

## Replication and access points

| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `PutBucketReplication` | — | — | tests/s3/test_operations.py (replication config) |
| `GetBucketReplication` | Bucket page (Configuration documents) | Bucket page › Configuration documents | tests/s3/test_objects.py (documents) |
| `DeleteBucketReplication` | — | — | tests/s3/test_operations.py (replication removed) |
| `CreateAccessPoint` | Access Points page | Access Points page › Create access point | tests/s3/test_access_points.py, tests/control/test_access_point_api.py |
| `GetAccessPoint` | Access Points page | Access Points page › row details | tests/s3/test_access_points.py (row details) |
| `ListAccessPoints` | Access Points page | Access Points page › General purpose buckets | tests/s3/test_access_points.py, tests/control/test_access_point_api.py |
| `DeleteAccessPoint` | Access Points page | Access Points page › Delete | tests/s3/test_access_points.py, tests/control/test_access_point_api.py |
| `PutAccessPointPolicy` | Access Points page (Edit policy) | Access Points page › Edit policy | tests/s3/test_access_points.py, tests/control/test_access_point_api.py |
| `GetAccessPointPolicy` | Access Points page (Edit policy) | Access Points page › Edit policy | tests/s3/test_access_points.py, tests/control/test_access_point_api.py |
| `DeleteAccessPointPolicy` | Access Points page (Remove policy) | Access Points page › Remove policy | tests/s3/test_access_points.py, tests/control/test_access_point_api.py |

## Multi-Region Access Points and Object Lambda

| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateMultiRegionAccessPoint` | Access Points page (Multi-Region create) | Access Points page › Multi-Region › Create | tests/s3/test_operations.py (MRAP create + describe), tests/control/test_mrap_create_api.py |
| `DeleteMultiRegionAccessPoint` | Access Points page (Multi-Region delete) | Access Points page › Multi-Region › Delete | tests/s3/test_operations.py (MRAP deleted), tests/control/test_mrap_actions_api.py |
| `PutMultiRegionAccessPointPolicy` | Access Points page (Multi-Region edit policy) | Access Points page › Multi-Region › Edit policy | tests/s3/test_operations.py (MRAP read + policy), tests/control/test_mrap_actions_api.py |
| `DescribeMultiRegionAccessPointOperation` | Access Points page (Multi-Region create) | Access Points page › Multi-Region › Create (operation status) | tests/s3/test_operations.py (MRAP create + describe), tests/control/test_mrap_create_api.py |
| `GetMultiRegionAccessPoint` | — | Access Points page › Multi-Region › View details | tests/s3/test_operations.py (MRAP read + policy) |
| `GetMultiRegionAccessPointPolicy` | — | Access Points page › Multi-Region › View details | tests/s3/test_operations.py (MRAP read + policy) |
| `ListMultiRegionAccessPoints` | Access Points page (Multi-Region tab) | Access Points page › Multi-Region | tests/s3/test_access_points.py, tests/control/test_access_point_api.py |
| `GetMultiRegionAccessPointRoutes` | — | Access Points page › Multi-Region › View details | tests/s3/test_operations.py (MRAP routes) |
| `SubmitMultiRegionAccessPointRoutes` | Access Points page (Multi-Region traffic dials) | Access Points page › Multi-Region › View details › Routes › Edit traffic dials | tests/s3/test_operations.py (MRAP routes), tests/control/test_mrap_actions_api.py |
| `CreateAccessPointForObjectLambda` | — | — | tests/s3/test_operations.py (Object Lambda create + read) |
| `GetAccessPointForObjectLambda` | — | Access Points page › Object Lambda › View details | tests/s3/test_operations.py (Object Lambda create + read) |
| `ListAccessPointsForObjectLambda` | Access Points page (Object Lambda tab) | Access Points page › Object Lambda | tests/s3/test_access_points.py, tests/control/test_access_point_api.py |
| `DeleteAccessPointForObjectLambda` | — | — | tests/s3/test_operations.py (Object Lambda deleted) |
| `GetAccessPointConfigurationForObjectLambda` | — | Access Points page › Object Lambda › View details | tests/s3/test_operations.py (Object Lambda configuration) |
| `PutAccessPointConfigurationForObjectLambda` | — | — | tests/s3/test_operations.py (Object Lambda configuration) |
| `PutAccessPointPolicyForObjectLambda` | — | — | tests/s3/test_operations.py (Object Lambda policy) |
| `GetAccessPointPolicyForObjectLambda` | — | Access Points page › Object Lambda › View details | tests/s3/test_operations.py (Object Lambda policy) |
| `DeleteAccessPointPolicyForObjectLambda` | — | — | tests/s3/test_operations.py (Object Lambda policy) |
| `WriteGetObjectResponse` | — | — | tests/s3/test_operations.py (unknown route refused) |

## GET operations

- [x] `ListBuckets` — Buckets page › table
- [x] `HeadBucket` — Bucket page (HeadBucket decides the region)
- [x] `GetObject` — Bucket page › Objects › open
- [x] `HeadObject` — Bucket page › Objects › open (size, ETag, last modified)
- [x] `ListObjects v1/v2` — Bucket page › Objects
- [x] `GetBucketVersioning` — Bucket page › Properties
- [x] `GetBucketEncryption` — Bucket page › Properties
- [x] `GetBucketLifecycleConfiguration` — Bucket page › Configuration documents
- [x] `GetBucketCors` — Bucket page › Configuration documents
- [x] `GetBucketAcl` — Bucket page › Configuration documents
- [x] `GetBucketTagging` — Bucket page › Properties
- [x] `GetBucketPolicy` — Bucket page › Configuration documents
- [x] `GetBucketNotificationConfiguration` — Bucket page › Configuration documents
- [x] `GetBucketLogging` — Bucket page › Configuration documents
- [x] `ListObjectVersions` — Bucket page › Configuration documents
- [x] `GetObjectLockConfiguration` — Create bucket page › Copy settings
- [x] `GetObjectRetention` — Bucket page › Objects › open › Object Lock
- [x] `GetObjectLegalHold` — Bucket page › Objects › open › Object Lock
- [x] `GetBucketReplication` — Bucket page › Configuration documents
- [x] `GetObjectTagging` — Bucket page › Objects › open › Tags
- [x] `GetObjectAnnotation` — Bucket page › Objects › open › Annotations › name
- [x] `ListObjectAnnotations` — Bucket page › Objects › open › Annotations
- [x] `DescribeMultiRegionAccessPointOperation` — Access Points page › Multi-Region › Create (operation status)
- [x] `GetMultiRegionAccessPoint` — Access Points page › Multi-Region › View details
- [x] `GetMultiRegionAccessPointPolicy` — Access Points page › Multi-Region › View details
- [x] `ListMultiRegionAccessPoints` — Access Points page › Multi-Region
- [x] `GetMultiRegionAccessPointRoutes` — Access Points page › Multi-Region › View details
- [x] `GetAccessPoint` — Access Points page › row details
- [x] `ListAccessPoints` — Access Points page › General purpose buckets
- [x] `GetAccessPointPolicy` — Access Points page › Edit policy
- [x] `GetAccessPointForObjectLambda` — Access Points page › Object Lambda › View details
- [x] `ListAccessPointsForObjectLambda` — Access Points page › Object Lambda
- [x] `GetAccessPointConfigurationForObjectLambda` — Access Points page › Object Lambda › View details
- [x] `GetAccessPointPolicyForObjectLambda` — Access Points page › Object Lambda › View details
- [x] `GetPublicAccessBlock` — Bucket page › Permissions

<!-- coverage:end -->
