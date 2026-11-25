---
sidebar_position: 78
title: Amazon EKS coverage
---

Every EKS operation the emulator advertises, and what Emuplane does with it. The
service is REST/JSON under `/clusters`, signed with the `eks` credential scope.
There is no console action: clusters and their children are driven over the wire.

A cluster is a record and settles `ACTIVE` whether or not a k3s container came up,
so the tests read and write the control plane rather than a Kubernetes API.
Nodegroups, addons, access entries, access-policy associations, OIDC identity
provider configurations and pod identity associations are records too, and a
cluster delete takes its children with it. The API allows one encryption
configuration and one OIDC identity provider per cluster, which is why the tests
use a separate cluster for each.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **34**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **34**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **14**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **34** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateCluster` | — | not yet | tests/control/test_eks_operations.py |
| `DescribeCluster` | — | not yet | tests/control/test_eks_operations.py |
| `ListClusters` | — | not yet | tests/control/test_eks_operations.py |
| `DeleteCluster` | — | not yet | tests/control/test_eks_operations.py |
| `CreateNodegroup` | — | not yet | tests/control/test_eks_operations.py |
| `DescribeNodegroup` | — | not yet | tests/control/test_eks_operations.py |
| `ListNodegroups` | — | not yet | tests/control/test_eks_operations.py |
| `DeleteNodegroup` | — | not yet | tests/control/test_eks_operations.py |
| `CreateAddon` | — | not yet | tests/control/test_eks_operations.py |
| `DescribeAddon` | — | not yet | tests/control/test_eks_operations.py |
| `ListAddons` | — | not yet | tests/control/test_eks_operations.py |
| `UpdateAddon` | — | not yet | tests/control/test_eks_operations.py |
| `DeleteAddon` | — | not yet | tests/control/test_eks_operations.py |
| `AssociateEncryptionConfig` | — | not yet | tests/control/test_eks_operations.py |
| `CreateAccessEntry` | — | not yet | tests/control/test_eks_operations.py |
| `DescribeAccessEntry` | — | not yet | tests/control/test_eks_operations.py |
| `ListAccessEntries` | — | not yet | tests/control/test_eks_operations.py |
| `UpdateAccessEntry` | — | not yet | tests/control/test_eks_operations.py |
| `DeleteAccessEntry` | — | not yet | tests/control/test_eks_operations.py |
| `AssociateAccessPolicy` | — | not yet | tests/control/test_eks_operations.py |
| `DisassociateAccessPolicy` | — | not yet | tests/control/test_eks_operations.py |
| `ListAssociatedAccessPolicies` | — | not yet | tests/control/test_eks_operations.py |
| `AssociateIdentityProviderConfig` | — | not yet | tests/control/test_eks_operations.py |
| `DescribeIdentityProviderConfig` | — | not yet | tests/control/test_eks_operations.py |
| `DisassociateIdentityProviderConfig` | — | not yet | tests/control/test_eks_operations.py |
| `ListIdentityProviderConfigs` | — | not yet | tests/control/test_eks_operations.py |
| `CreatePodIdentityAssociation` | — | not yet | tests/control/test_eks_operations.py |
| `DescribePodIdentityAssociation` | — | not yet | tests/control/test_eks_operations.py |
| `ListPodIdentityAssociations` | — | not yet | tests/control/test_eks_operations.py |
| `UpdatePodIdentityAssociation` | — | not yet | tests/control/test_eks_operations.py |
| `DeletePodIdentityAssociation` | — | not yet | tests/control/test_eks_operations.py |
| `TagResource` | — | not yet | tests/control/test_eks_operations.py |
| `UntagResource` | — | not yet | tests/control/test_eks_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_eks_operations.py |

<!-- coverage:end -->
