---
sidebar_position: 1
title: Reference
---

What the console can do, operation by operation; the settings it reads; and what it
deliberately does not do. Every coverage page is generated from the emulator's own
operation list, so a service that answers APIs gets a page here rather than a promise.

**This index is the map.** One row per service, grouped the way the emulator groups
them, and one page behind each row. The sidebar does not list the services: a list
that grows a line per service is a list nobody reads at 90 entries, and a table with
counts answers the same question better. Jump to a group: [Core](#core) ·
[Extended](#extended) · [Infrastructure](#infrastructure) ·
[CloudFormation](#cloudformation).

Two rules shape the pages. A page counts only what the emulator **advertises**, and
every operation it counts names the test behind it — a service with an operation and
no test shows up as untested here rather than being quietly omitted. A new service is
a `coverage/<service>.json` ledger, a page with `coverage:begin`/`coverage:end`
markers, and the tests the ledger names.

This index is generated from `coverage/*.json` by the same script that renders the
pages, so adding a service never means editing it by hand.

```bash
npm run coverage   # regenerates the index and every service page
```

<!-- coverage-index:begin -->

**86 services** · 2533 operations · 2531 tested · 2 blocked. Each page names the test behind every operation it counts.

### Core {#core}

| Service | Operations | Tested | Blocked | Page |
| --- | ---: | ---: | ---: | --- |
| ACM | 12 | 12 | 0 | [acm-coverage](acm-coverage.md) |
| Amazon Location (trackers) | 9 | 9 | 0 | [location-coverage](location-coverage.md) |
| AmazonMQ | 16 | 16 | 0 | [amazonmq-coverage](amazonmq-coverage.md) |
| API Gateway v1 | 87 | 87 | 0 | [apigateway-v1-coverage](apigateway-v1-coverage.md) |
| API Gateway v2 | 55 | 55 | 0 | [apigateway-v2-coverage](apigateway-v2-coverage.md) |
| AWS Budgets | 16 | 16 | 0 | [aws-budgets-coverage](aws-budgets-coverage.md) |
| AWS Config | 14 | 14 | 0 | [aws-config-coverage](aws-config-coverage.md) |
| Backup | 21 | 21 | 0 | [backup-coverage](backup-coverage.md) |
| Bedrock | 66 | 66 | 0 | [bedrock-coverage](bedrock-coverage.md) |
| Bedrock Agent | 72 | 72 | 0 | [bedrock-agent-coverage](bedrock-agent-coverage.md) |
| Bedrock Agent Runtime | 27 | 27 | 0 | [bedrock-agent-runtime-coverage](bedrock-agent-runtime-coverage.md) |
| Bedrock AgentCore | 35 | 35 | 0 | [bedrock-agentcore-coverage](bedrock-agentcore-coverage.md) |
| Bedrock Runtime | 8 | 8 | 0 | [bedrock-runtime-coverage](bedrock-runtime-coverage.md) |
| Cloud Control API | 8 | 8 | 0 | [cloud-control-coverage](cloud-control-coverage.md) |
| CloudFront | 93 | 93 | 0 | [cloudfront-coverage](cloudfront-coverage.md) |
| CloudFront KeyValueStore (data plane) | 6 | 6 | 0 | [cloudfront-kvs-coverage](cloudfront-kvs-coverage.md) |
| CloudTrail | 15 | 15 | 0 | [cloudtrail-coverage](cloudtrail-coverage.md) |
| CloudWatch Logs | 51 | 51 | 0 | [logs-coverage](logs-coverage.md) |
| CloudWatch Metrics | 20 | 20 | 0 | [cloudwatch-metrics-coverage](cloudwatch-metrics-coverage.md) |
| Cost & Usage Reports | 7 | 7 | 0 | [cost-usage-reports-coverage](cost-usage-reports-coverage.md) |
| DynamoDB | 27 | 27 | 0 | [dynamodb-coverage](dynamodb-coverage.md) |
| DynamoDB Streams | 4 | 4 | 0 | [dynamodb-streams-coverage](dynamodb-streams-coverage.md) |
| ECS Container Credentials | 1 | 1 | 0 | [ecs-container-credentials-coverage](ecs-container-credentials-coverage.md) |
| ECS Task Metadata V4 | 4 | 4 | 0 | [ecs-task-metadata-coverage](ecs-task-metadata-coverage.md) |
| ELBv2 / ALB | 32 | 32 | 0 | [alb-coverage](alb-coverage.md) |
| IAM | 98 | 98 | 0 | [iam-coverage](iam-coverage.md) |
| Inspector2 | 14 | 14 | 0 | [inspector2-coverage](inspector2-coverage.md) |
| KMS | 41 | 41 | 0 | [kms-coverage](kms-coverage.md) |
| Lambda | 55 | 55 | 0 | [lambda-coverage](lambda-coverage.md) |
| Managed Service for Apache Flink | 15 | 15 | 0 | [flink-coverage](flink-coverage.md) |
| MSK | 17 | 17 | 0 | [msk-coverage](msk-coverage.md) |
| S3 | 84 | 84 | 0 | [s3-coverage](s3-coverage.md) |
| SecretsManager | 21 | 21 | 0 | [secretsmanager-coverage](secretsmanager-coverage.md) |
| SES | 35 | 35 | 0 | [ses-coverage](ses-coverage.md) |
| SES v2 | 46 | 46 | 0 | [sesv2-coverage](sesv2-coverage.md) |
| SNS | 28 | 28 | 0 | [sns-coverage](sns-coverage.md) |
| SQS | 17 | 17 | 0 | [sqs-coverage](sqs-coverage.md) |
| Step Functions | 24 | 24 | 0 | [stepfunctions-coverage](stepfunctions-coverage.md) |
| STS | 5 | 5 | 0 | [sts-coverage](sts-coverage.md) |
| Transcribe | 4 | 4 | 0 | [transcribe-coverage](transcribe-coverage.md) |
| Translate | 4 | 4 | 0 | [translate-coverage](translate-coverage.md) |
| WAF (Classic + Regional) | 20 | 20 | 0 | [waf-classic-coverage](waf-classic-coverage.md) |
| WAF v2 | 29 | 29 | 0 | [wafv2-coverage](wafv2-coverage.md) |

### Extended {#extended}

| Service | Operations | Tested | Blocked | Page |
| --- | ---: | ---: | ---: | --- |
| AppSync | 55 | 55 | 0 | [appsync-coverage](appsync-coverage.md) |
| EventBridge | 57 | 57 | 0 | [eventbridge-coverage](eventbridge-coverage.md) |
| Kinesis | 30 | 30 | 0 | [kinesis-coverage](kinesis-coverage.md) |
| SSM Parameter Store | 24 | 24 | 0 | [ssm-coverage](ssm-coverage.md) |

### Infrastructure {#infrastructure}

| Service | Operations | Tested | Blocked | Page |
| --- | ---: | ---: | ---: | --- |
| Account | 4 | 4 | 0 | [account-coverage](account-coverage.md) |
| AppConfig | 33 | 33 | 0 | [appconfig-coverage](appconfig-coverage.md) |
| Athena | 32 | 32 | 0 | [athena-coverage](athena-coverage.md) |
| Aurora DSQL | 16 | 16 | 0 | [dsql-coverage](dsql-coverage.md) |
| AutoScaling | 23 | 23 | 0 | [autoscaling-coverage](autoscaling-coverage.md) |
| Batch | 10 | 10 | 0 | [batch-coverage](batch-coverage.md) |
| Cloud Map | 29 | 29 | 0 | [cloud-map-coverage](cloud-map-coverage.md) |
| CodeBuild | 11 | 11 | 0 | [codebuild-coverage](codebuild-coverage.md) |
| Cognito | 101 | 101 | 0 | [cognito-coverage](cognito-coverage.md) |
| DocumentDB | 15 | 15 | 0 | [documentdb-coverage](documentdb-coverage.md) |
| EBS | 17 | 17 | 0 | [ebs-coverage](ebs-coverage.md) |
| EC2 | 157 | 155 | 2 | [ec2-coverage](ec2-coverage.md) |
| ECR | 26 | 26 | 0 | [ecr-coverage](ecr-coverage.md) |
| ECS | 47 | 47 | 0 | [ecs-coverage](ecs-coverage.md) |
| EFS | 28 | 28 | 0 | [efs-coverage](efs-coverage.md) |
| EKS | 34 | 34 | 0 | [eks-coverage](eks-coverage.md) |
| ElastiCache | 41 | 41 | 0 | [elasticache-coverage](elasticache-coverage.md) |
| EMR | 22 | 22 | 0 | [emr-coverage](emr-coverage.md) |
| EventBridge Scheduler | 12 | 12 | 0 | [eventbridge-scheduler-coverage](eventbridge-scheduler-coverage.md) |
| Firehose | 12 | 12 | 0 | [firehose-coverage](firehose-coverage.md) |
| Glue | 83 | 83 | 0 | [glue-coverage](glue-coverage.md) |
| IoT Core | 75 | 75 | 0 | [iot-coverage](iot-coverage.md) |
| IoT Jobs | 20 | 20 | 0 | [iot-jobs-coverage](iot-jobs-coverage.md) |
| IoT Wireless | 1 | 1 | 0 | [iot-wireless-coverage](iot-wireless-coverage.md) |
| OpenSearch Serverless | 19 | 19 | 0 | [opensearch-serverless-coverage](opensearch-serverless-coverage.md) |
| OpenSearch Service | 13 | 13 | 0 | [opensearch-coverage](opensearch-coverage.md) |
| Organizations | 28 | 28 | 0 | [organizations-coverage](organizations-coverage.md) |
| RDS | 66 | 66 | 0 | [rds-coverage](rds-coverage.md) |
| RDS Data API | 5 | 5 | 0 | [rds-data-api-coverage](rds-data-api-coverage.md) |
| Route53 | 19 | 19 | 0 | [route53-coverage](route53-coverage.md) |
| S3 Files | 21 | 21 | 0 | [s3-files-coverage](s3-files-coverage.md) |
| S3 Tables | 39 | 39 | 0 | [s3tables-coverage](s3tables-coverage.md) |
| Signer | 9 | 9 | 0 | [signer-coverage](signer-coverage.md) |
| Transfer Family | 12 | 12 | 0 | [transfer-coverage](transfer-coverage.md) |

### CloudFormation {#cloudformation}

| Service | Operations | Tested | Blocked | Page |
| --- | ---: | ---: | ---: | --- |
| Change Sets | 5 | 5 | 0 | [change-sets-coverage](change-sets-coverage.md) |
| Drift Detection | 4 | 4 | 0 | [drift-detection-coverage](drift-detection-coverage.md) |
| Exports | 1 | 1 | 0 | [exports-coverage](exports-coverage.md) |
| Stack Operations | 12 | 12 | 0 | [stack-operations-coverage](stack-operations-coverage.md) |
| StackSets | 2 | 2 | 0 | [stacksets-coverage](stacksets-coverage.md) |

<!-- coverage-index:end -->

The control API's own route table is generated from its dispatcher and sits under
**API** rather than here: it is a reference for callers, not a description of the
console.
