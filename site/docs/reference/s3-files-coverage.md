---
sidebar_position: 3
title: S3 Files coverage
---

Every S3 Files operation the emulator advertises, and what Emuplane does with it.
This is a separate service from S3 — file systems, mount targets, access points and
policies — so it gets its own page rather than being folded into the S3 ledger.

The table is generated from the emulator's own operation list; the console column
says what the UI does today, and a dash under *Emuplane test* means nothing in this
repository exercises the operation yet.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **21**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **21**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **1**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **1** of **9**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **21** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateFileSystem` | — | not yet | tests/s3/test_s3files_operations.py (create file system is read back by get and list) |
| `GetFileSystem` | — | not yet | tests/s3/test_s3files_operations.py (create file system is read back by get and list) |
| `ListFileSystems` | — | Files page › table, bucket page › File systems | tests/s3/test_children.py (listing parsed) |
| `DeleteFileSystem` | — | not yet | tests/s3/test_s3files_operations.py (delete file system removes the file system it created) |
| `CreateMountTarget` | — | not yet | tests/s3/test_s3files_operations.py (mount target lifecycle) |
| `GetMountTarget` | — | not yet | tests/s3/test_s3files_operations.py (mount target lifecycle) |
| `ListMountTargets` | — | not yet | tests/s3/test_s3files_operations.py (mount target lifecycle) |
| `UpdateMountTarget` | — | not yet | tests/s3/test_s3files_operations.py (mount target lifecycle) |
| `DeleteMountTarget` | — | not yet | tests/s3/test_s3files_operations.py (mount target lifecycle) |
| `CreateAccessPoint` | — | not yet | tests/s3/test_s3files_operations.py (access point lifecycle) |
| `GetAccessPoint` | — | not yet | tests/s3/test_s3files_operations.py (access point lifecycle) |
| `ListAccessPoints` | — | not yet | tests/s3/test_s3files_operations.py (access point lifecycle) |
| `DeleteAccessPoint` | — | not yet | tests/s3/test_s3files_operations.py (access point lifecycle) |
| `GetFileSystemPolicy` | — | not yet | tests/s3/test_s3files_operations.py (file system policy is put read and deleted) |
| `PutFileSystemPolicy` | — | not yet | tests/s3/test_s3files_operations.py (file system policy is put read and deleted) |
| `DeleteFileSystemPolicy` | — | not yet | tests/s3/test_s3files_operations.py (file system policy is put read and deleted) |
| `GetSynchronizationConfiguration` | — | not yet | tests/s3/test_s3files_operations.py (synchronization configuration is put and read) |
| `PutSynchronizationConfiguration` | — | not yet | tests/s3/test_s3files_operations.py (synchronization configuration is put and read) |
| `TagResource` | — | not yet | tests/s3/test_s3files_operations.py (tags are tagged listed and untagged) |
| `UntagResource` | — | not yet | tests/s3/test_s3files_operations.py (tags are tagged listed and untagged) |
| `ListTagsForResource` | — | not yet | tests/s3/test_s3files_operations.py (tags are tagged listed and untagged) |

<!-- coverage:end -->
