---
sidebar_position: 41
title: EBS coverage
---

Every EBS operation the emulator advertises, and what Emuplane does with it. EBS
is part of the EC2 Query/XML service, so it is signed with the `ec2` credential
scope. There is no console action.

Volumes are records; attach and detach move a volume between `available` and
`in-use`, a modification completes synchronously, and a snapshot is stored
`completed` immediately.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **17**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **17**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **6**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **17** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateVolume` | — | not yet | tests/control/test_ebs_operations.py |
| `DeleteVolume` | — | not yet | tests/control/test_ebs_operations.py |
| `DescribeVolumes` | — | not yet | tests/control/test_ebs_operations.py |
| `DescribeVolumeStatus` | — | not yet | tests/control/test_ebs_operations.py |
| `AttachVolume` | — | not yet | tests/control/test_ebs_operations.py |
| `DetachVolume` | — | not yet | tests/control/test_ebs_operations.py |
| `ModifyVolume` | — | not yet | tests/control/test_ebs_operations.py |
| `DescribeVolumesModifications` | — | not yet | tests/control/test_ebs_operations.py |
| `EnableVolumeIO` | — | not yet | tests/control/test_ebs_operations.py |
| `ModifyVolumeAttribute` | — | not yet | tests/control/test_ebs_operations.py |
| `DescribeVolumeAttribute` | — | not yet | tests/control/test_ebs_operations.py |
| `CreateSnapshot` | — | not yet | tests/control/test_ebs_operations.py |
| `DeleteSnapshot` | — | not yet | tests/control/test_ebs_operations.py |
| `DescribeSnapshots` | — | not yet | tests/control/test_ebs_operations.py |
| `CopySnapshot` | — | not yet | tests/control/test_ebs_operations.py |
| `ModifySnapshotAttribute` | — | not yet | tests/control/test_ebs_operations.py |
| `DescribeSnapshotAttribute` | — | not yet | tests/control/test_ebs_operations.py |

<!-- coverage:end -->
