---
sidebar_position: 6
title: EC2 coverage
---

Every EC2 operation the emulator advertises, and what Emuplane does with it.
The console drives the instance lifecycle — describe, launch, start, stop and
terminate — while the rest of the surface (VPCs, security groups, key pairs,
addresses, route tables and Verified Access) is reachable over the wire and is
exercised by the API tests.

The table is generated from the emulator's own operation list; the console column
names the page or API explorer entry that reaches an operation, and a row under
*Emuplane test* names the test that exercises it. A blocked operation names the
dependant it is waiting on.

```bash
npm run coverage   # regenerates every service's coverage page from coverage/*.json
```

<!-- coverage:begin -->

*Part of the [coverage index](index.md).*

- Operations upstream advertises: **157**
- Console actions (`/api/exec`, the create page): **5**
- Operations with an emuplane test: **155**
- Operations blocked on a dependant: **2**
- Operations shown in the console: **5**
- Operations that are not console actions: **152**
- GET operations (Get/List/Head/Describe) shown in the console: **1** of **51**
- Operations with no emuplane test: **0**

- Group: **Infrastructure** · operations: **157** · Console actions: **5**




## Operations


| Operation | Console action | Shown in the console | Emuplane test |
| --- | --- | --- | --- |
| `RunInstances` | run-instances | EC2 page › Launch instance | tests/control/test_ec2_operations.py |
| `DescribeInstances` | describe-instances | EC2 page › Describe instances | tests/control/test_ec2_operations.py |
| `DescribeInstanceAttribute` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeInstanceTypes` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeVpcAttribute` | — | not a console action | tests/control/test_ec2_operations.py |
| `TerminateInstances` | terminate-instances | EC2 page › Terminate instance | tests/control/test_ec2_operations.py |
| `StopInstances` | stop-instances | EC2 page › Stop instance | tests/control/test_ec2_operations.py |
| `StartInstances` | start-instances | EC2 page › Start instance | tests/control/test_ec2_operations.py |
| `RebootInstances` | — | not a console action | tests/control/test_ec2_operations.py |
| `AssociateIamInstanceProfile` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeIamInstanceProfileAssociations` | — | not a console action | tests/control/test_ec2_operations.py |
| `DisassociateIamInstanceProfile` | — | not a console action | tests/control/test_ec2_operations.py |
| `ReplaceIamInstanceProfileAssociation` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeImages` | — | not a console action | tests/control/test_ec2_operations.py |
| `RegisterImage` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeregisterImage` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifyImageAttribute` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeImageAttribute` | — | not a console action | tests/control/test_ec2_operations.py |
| `ResetImageAttribute` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateSecurityGroup` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteSecurityGroup` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeSecurityGroups` | — | not a console action | tests/control/test_ec2_operations.py |
| `AuthorizeSecurityGroupIngress` | — | not a console action | tests/control/test_ec2_operations.py |
| `RevokeSecurityGroupIngress` | — | not a console action | tests/control/test_ec2_operations.py |
| `AuthorizeSecurityGroupEgress` | — | not a console action | tests/control/test_ec2_operations.py |
| `RevokeSecurityGroupEgress` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeSecurityGroupRules` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateKeyPair` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteKeyPair` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeKeyPairs` | — | not a console action | tests/control/test_ec2_operations.py |
| `ImportKeyPair` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreatePlacementGroup` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeletePlacementGroup` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribePlacementGroups` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateVpc` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteVpc` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeVpcs` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifyVpcAttribute` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateSubnet` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteSubnet` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeSubnets` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifySubnetAttribute` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateInternetGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteInternetGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeInternetGateways` | — | not a console action | tests/control/test_ec2_operations.py |
| `AttachInternetGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `DetachInternetGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateRouteTable` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteRouteTable` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeRouteTables` | — | not a console action | tests/control/test_ec2_operations.py |
| `AssociateRouteTable` | — | not a console action | tests/control/test_ec2_operations.py |
| `DisassociateRouteTable` | — | not a console action | tests/control/test_ec2_operations.py |
| `ReplaceRouteTableAssociation` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateRoute` | — | not a console action | tests/control/test_ec2_operations.py |
| `ReplaceRoute` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteRoute` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateNetworkInterface` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteNetworkInterface` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeNetworkInterfaces` | — | not a console action | tests/control/test_ec2_operations.py |
| `AttachNetworkInterface` | — | not a console action | tests/control/test_ec2_operations.py |
| `DetachNetworkInterface` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateVpcEndpoint` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteVpcEndpoints` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeVpcEndpoints` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifyVpcEndpoint` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribePrefixLists` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeAvailabilityZones` | — | not a console action | tests/control/test_ec2_operations.py |
| `AllocateAddress` | — | not a console action | tests/control/test_ec2_operations.py |
| `ReleaseAddress` | — | not a console action | tests/control/test_ec2_operations.py |
| `AssociateAddress` | — | not a console action | tests/control/test_ec2_operations.py |
| `DisassociateAddress` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeAddresses` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeAddressesAttribute` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateTags` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteTags` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeTags` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateNatGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeNatGateways` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteNatGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateNetworkAcl` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeNetworkAcls` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteNetworkAcl` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateNetworkAclEntry` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteNetworkAclEntry` | — | not a console action | tests/control/test_ec2_operations.py |
| `ReplaceNetworkAclEntry` | — | not a console action | tests/control/test_ec2_operations.py |
| `ReplaceNetworkAclAssociation` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateFlowLogs` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeFlowLogs` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteFlowLogs` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateVpcPeeringConnection` | — | not a console action | tests/control/test_ec2_operations.py |
| `AcceptVpcPeeringConnection` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeVpcPeeringConnections` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteVpcPeeringConnection` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateDhcpOptions` | — | not a console action | tests/control/test_ec2_operations.py |
| `AssociateDhcpOptions` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeDhcpOptions` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteDhcpOptions` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateEgressOnlyInternetGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeEgressOnlyInternetGateways` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteEgressOnlyInternetGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateManagedPrefixList` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeManagedPrefixLists` | — | not a console action | tests/control/test_ec2_operations.py |
| `GetManagedPrefixListEntries` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifyManagedPrefixList` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteManagedPrefixList` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateVpnGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeVpnGateways` | — | not a console action | tests/control/test_ec2_operations.py |
| `AttachVpnGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `DetachVpnGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteVpnGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `EnableVgwRoutePropagation` | — | not a console action | tests/control/test_ec2_operations.py |
| `DisableVgwRoutePropagation` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateCustomerGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeCustomerGateways` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteCustomerGateway` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeInstanceCreditSpecifications` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeInstanceMaintenanceOptions` | — | not a console action | blocked — advertised by v1.5.40, absent from its dispatcher (400 InvalidAction) |
| `DescribeInstanceAutoRecoveryAttribute` | — | not a console action | blocked — advertised by v1.5.40, absent from its dispatcher (400 InvalidAction) |
| `ModifyInstanceMaintenanceOptions` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeInstanceTopology` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeSpotInstanceRequests` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeCapacityReservations` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeInstanceStatus` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeVpcClassicLink` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeVpcClassicLinkDnsSupport` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateLaunchTemplate` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateLaunchTemplateVersion` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeLaunchTemplates` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeLaunchTemplateVersions` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifyLaunchTemplate` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteLaunchTemplate` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateFleet` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeFleets` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateVerifiedAccessInstance` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeVerifiedAccessInstances` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifyVerifiedAccessInstance` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteVerifiedAccessInstance` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateVerifiedAccessTrustProvider` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeVerifiedAccessTrustProviders` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifyVerifiedAccessTrustProvider` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteVerifiedAccessTrustProvider` | — | not a console action | tests/control/test_ec2_operations.py |
| `AttachVerifiedAccessTrustProvider` | — | not a console action | tests/control/test_ec2_operations.py |
| `DetachVerifiedAccessTrustProvider` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifyVerifiedAccessInstanceLoggingConfiguration` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeVerifiedAccessInstanceLoggingConfigurations` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateVerifiedAccessGroup` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeVerifiedAccessGroups` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifyVerifiedAccessGroup` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteVerifiedAccessGroup` | — | not a console action | tests/control/test_ec2_operations.py |
| `GetVerifiedAccessGroupPolicy` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifyVerifiedAccessGroupPolicy` | — | not a console action | tests/control/test_ec2_operations.py |
| `CreateVerifiedAccessEndpoint` | — | not a console action | tests/control/test_ec2_operations.py |
| `DescribeVerifiedAccessEndpoints` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifyVerifiedAccessEndpoint` | — | not a console action | tests/control/test_ec2_operations.py |
| `DeleteVerifiedAccessEndpoint` | — | not a console action | tests/control/test_ec2_operations.py |
| `GetVerifiedAccessEndpointPolicy` | — | not a console action | tests/control/test_ec2_operations.py |
| `ModifyVerifiedAccessEndpointPolicy` | — | not a console action | tests/control/test_ec2_operations.py |

<!-- coverage:end -->
