---
sidebar_position: 32
title: S3 Tables coverage
---

Every S3 Tables control-plane operation the emulator advertises, and what Emuplane
does with it. Tables are Iceberg-format; table buckets, namespaces and tables are
managed over REST/JSON, signed with the `s3tables` credential scope, and there is
no console action.

An unset encryption, storage class or maintenance configuration reads back as the
documented default rather than an empty answer, so a GET never has to be guarded.
The emulator also serves an Iceberg REST catalog at `/iceberg` so a Spark job can
create, load and commit tables; that is a data plane and is not counted here.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **39**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **39**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **18**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **39** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateTableBucket` | — | not yet | tests/control/test_s3tables_operations.py |
| `ListTableBuckets` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTableBucket` | — | not yet | tests/control/test_s3tables_operations.py |
| `DeleteTableBucket` | — | not yet | tests/control/test_s3tables_operations.py |
| `CreateNamespace` | — | not yet | tests/control/test_s3tables_operations.py |
| `ListNamespaces` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetNamespace` | — | not yet | tests/control/test_s3tables_operations.py |
| `DeleteNamespace` | — | not yet | tests/control/test_s3tables_operations.py |
| `CreateTable` | — | not yet | tests/control/test_s3tables_operations.py |
| `ListTables` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTable` | — | not yet | tests/control/test_s3tables_operations.py |
| `DeleteTable` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTableMetadataLocation` | — | not yet | tests/control/test_s3tables_operations.py |
| `UpdateTableMetadataLocation` | — | not yet | tests/control/test_s3tables_operations.py |
| `RenameTable` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTableBucketEncryption` | — | not yet | tests/control/test_s3tables_operations.py |
| `PutTableBucketEncryption` | — | not yet | tests/control/test_s3tables_operations.py |
| `DeleteTableBucketEncryption` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTableBucketMaintenanceConfiguration` | — | not yet | tests/control/test_s3tables_operations.py |
| `PutTableBucketMaintenanceConfiguration` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTableBucketPolicy` | — | not yet | tests/control/test_s3tables_operations.py |
| `PutTableBucketPolicy` | — | not yet | tests/control/test_s3tables_operations.py |
| `DeleteTableBucketPolicy` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTableBucketStorageClass` | — | not yet | tests/control/test_s3tables_operations.py |
| `PutTableBucketStorageClass` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTableBucketMetricsConfiguration` | — | not yet | tests/control/test_s3tables_operations.py |
| `PutTableBucketMetricsConfiguration` | — | not yet | tests/control/test_s3tables_operations.py |
| `DeleteTableBucketMetricsConfiguration` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTableEncryption` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTableStorageClass` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTableMaintenanceConfiguration` | — | not yet | tests/control/test_s3tables_operations.py |
| `PutTableMaintenanceConfiguration` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTableMaintenanceJobStatus` | — | not yet | tests/control/test_s3tables_operations.py |
| `GetTablePolicy` | — | not yet | tests/control/test_s3tables_operations.py |
| `PutTablePolicy` | — | not yet | tests/control/test_s3tables_operations.py |
| `DeleteTablePolicy` | — | not yet | tests/control/test_s3tables_operations.py |
| `TagResource` | — | not yet | tests/control/test_s3tables_operations.py |
| `UntagResource` | — | not yet | tests/control/test_s3tables_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_s3tables_operations.py |

<!-- coverage:end -->
