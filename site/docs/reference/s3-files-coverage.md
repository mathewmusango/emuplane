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
- Operations with an emuplane test: **1**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **1**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **1** of **9**
- Operations with no emuplane test: **20**

- Group: **Infrastructure** · operations: **21** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateFileSystem` | — | not yet | — |
| `GetFileSystem` | — | not yet | — |
| `ListFileSystems` | — | Files page › table, bucket page › File systems | tests/s3/test_children.py (listing parsed) |
| `DeleteFileSystem` | — | not yet | — |
| `CreateMountTarget` | — | not yet | — |
| `GetMountTarget` | — | not yet | — |
| `ListMountTargets` | — | not yet | — |
| `UpdateMountTarget` | — | not yet | — |
| `DeleteMountTarget` | — | not yet | — |
| `CreateAccessPoint` | — | not yet | — |
| `GetAccessPoint` | — | not yet | — |
| `ListAccessPoints` | — | not yet | — |
| `DeleteAccessPoint` | — | not yet | — |
| `GetFileSystemPolicy` | — | not yet | — |
| `PutFileSystemPolicy` | — | not yet | — |
| `DeleteFileSystemPolicy` | — | not yet | — |
| `GetSynchronizationConfiguration` | — | not yet | — |
| `PutSynchronizationConfiguration` | — | not yet | — |
| `TagResource` | — | not yet | — |
| `UntagResource` | — | not yet | — |
| `ListTagsForResource` | — | not yet | — |

<!-- coverage:end -->
