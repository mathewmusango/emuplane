---
sidebar_position: 82
title: CloudFront coverage
---

Every CloudFront operation the emulator advertises, and what Emuplane does with it.
REST/XML under the `cloudfront` scope; an update or delete sends the `ETag` the
previous read answered as `If-Match`, and a stale one is refused. There is no console
action.

Distribution tenants can only attach to a `tenant-only` distribution, so the suite
keeps one of those beside the ordinary distribution; a VPC origin must name an EC2
instance or load balancer that exists, so the suite launches an instance through the
`ec2` query protocol; and a tenant's managed certificate is minted from its
`ManagedCertificateRequest`. Delete tests create their own resource and disable it
first, and update tests restore the stable record. The key value store's data plane
has its own page and test module.

The table is generated from the emulator's own operation list; every row names
the test that exercises it.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage map](../coverage/index.md).*

- Operations upstream advertises: **93**
- Console actions (`/api/exec`, the create page): **0**
- Operations with an emuplane test: **93**
- Operations blocked on a dependant: **0**
- Operations shown in the console: **0**
- Operations that are not console actions: **0**
- GET operations (Get/List/Head/Describe) shown in the console: **0** of **44**
- Operations with no emuplane test: **0**

- Group: **Core** · operations: **93** · Console actions: **0**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `CreateDistribution` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetDistribution` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetDistributionConfig` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListDistributions` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdateDistribution` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeleteDistribution` | — | not yet | tests/control/test_cloudfront_operations.py |
| `AssociateDistributionWebACL` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DisassociateDistributionWebACL` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateInvalidation` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListInvalidations` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetInvalidation` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateOriginAccessControl` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetOriginAccessControl` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetOriginAccessControlConfig` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListOriginAccessControls` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdateOriginAccessControl` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeleteOriginAccessControl` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateMonitoringSubscription` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetMonitoringSubscription` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeleteMonitoringSubscription` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateFunction` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeleteFunction` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DescribeFunction` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetFunction` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListFunctions` | — | not yet | tests/control/test_cloudfront_operations.py |
| `PublishFunction` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdateFunction` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateKeyValueStore` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DescribeKeyValueStore` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListKeyValueStores` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdateKeyValueStore` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeleteKeyValueStore` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateCachePolicy` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetCachePolicy` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetCachePolicyConfig` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdateCachePolicy` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeleteCachePolicy` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListDistributionsByCachePolicyId` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateOriginRequestPolicy` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetOriginRequestPolicy` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetOriginRequestPolicyConfig` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdateOriginRequestPolicy` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeleteOriginRequestPolicy` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListDistributionsByOriginRequestPolicyId` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateResponseHeadersPolicy` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetResponseHeadersPolicy` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetResponseHeadersPolicyConfig` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdateResponseHeadersPolicy` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeleteResponseHeadersPolicy` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListDistributionsByResponseHeadersPolicyId` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreatePublicKey` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetPublicKey` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetPublicKeyConfig` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdatePublicKey` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeletePublicKey` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListPublicKeys` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateKeyGroup` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetKeyGroup` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetKeyGroupConfig` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdateKeyGroup` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeleteKeyGroup` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListKeyGroups` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateVpcOrigin` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetVpcOrigin` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdateVpcOrigin` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeleteVpcOrigin` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListVpcOrigins` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateConnectionGroup` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetConnectionGroup` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetConnectionGroupByRoutingEndpoint` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdateConnectionGroup` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeleteConnectionGroup` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListConnectionGroups` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateDistributionTenant` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetDistributionTenant` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetDistributionTenantByDomain` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdateDistributionTenant` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DeleteDistributionTenant` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListDistributionTenants` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListDistributionTenantsByCustomization` | — | not yet | tests/control/test_cloudfront_operations.py |
| `AssociateDistributionTenantWebACL` | — | not yet | tests/control/test_cloudfront_operations.py |
| `DisassociateDistributionTenantWebACL` | — | not yet | tests/control/test_cloudfront_operations.py |
| `CreateInvalidationForDistributionTenant` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetInvalidationForDistributionTenant` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListInvalidationsForDistributionTenant` | — | not yet | tests/control/test_cloudfront_operations.py |
| `VerifyDnsConfiguration` | — | not yet | tests/control/test_cloudfront_operations.py |
| `GetManagedCertificateDetails` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListDomainConflicts` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UpdateDomainAssociation` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListDistributionsByConnectionMode` | — | not yet | tests/control/test_cloudfront_operations.py |
| `TagResource` | — | not yet | tests/control/test_cloudfront_operations.py |
| `UntagResource` | — | not yet | tests/control/test_cloudfront_operations.py |
| `ListTagsForResource` | — | not yet | tests/control/test_cloudfront_operations.py |

<!-- coverage:end -->
