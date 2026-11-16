// The AWS-style service taxonomy the console navigates by; anything it has not been taught falls back to "Other".

import { serviceLabel } from './serviceLabels'

export const CATEGORY_ORDER = [
  'Analytics',
  'Application Integration',
  'Business Applications',
  'Compute',
  'Containers',
  'Database',
  'Developer Tools',
  'Front-end Web & Mobile',
  'Internet of Things',
  'Machine Learning',
  'Management & Governance',
  'Media Services',
  'Migration & Transfer',
  'Networking & Content Delivery',
  'Security, Identity & Compliance',
  'Storage',
  'Other',
]

const CATEGORY = {
  // Analytics
  athena: 'Analytics',
  kinesis: 'Analytics',
  kinesisanalyticsv2: 'Analytics',
  firehose: 'Analytics',
  glue: 'Analytics',
  elasticmapreduce: 'Analytics',
  opensearch: 'Analytics',
  opensearchserverless: 'Analytics',
  s3tables: 'Analytics',
  dataexchange: 'Analytics',
  quicksight: 'Analytics',

  // Application Integration
  sqs: 'Application Integration',
  sns: 'Application Integration',
  events: 'Application Integration',
  apigateway: 'Application Integration',
  appsync: 'Application Integration',
  'appsync-events': 'Application Integration',
  states: 'Application Integration',
  mq: 'Application Integration',
  pipes: 'Application Integration',
  scheduler: 'Application Integration',

  // Compute
  lambda: 'Compute',
  'lambda-core': 'Compute',
  'lambda-microvms': 'Compute',
  ec2: 'Compute',
  batch: 'Compute',
  autoscaling: 'Compute',
  lightsail: 'Compute',

  // Containers
  ecs: 'Containers',
  'ecs-metadata': 'Containers',
  eks: 'Containers',
  ecr: 'Containers',
  'ecr-public': 'Containers',

  // Database
  dynamodb: 'Database',
  dynamodbstreams: 'Database',
  rds: 'Database',
  'rds-data': 'Database',
  documentdb: 'Database',
  dsql: 'Database',
  elasticache: 'Database',
  neptune: 'Database',

  // Developer Tools
  codebuild: 'Developer Tools',
  cloudcontrol: 'Developer Tools',
  signer: 'Developer Tools',
  appconfig: 'Developer Tools',
  appconfigdata: 'Developer Tools',
  'resource-groups': 'Developer Tools',

  // Front-end Web & Mobile
  'cognito-identity': 'Front-end Web & Mobile',
  amplify: 'Front-end Web & Mobile',

  // Internet of Things
  iot: 'Internet of Things',
  'iot-data': 'Internet of Things',
  'iot-jobs-data': 'Internet of Things',
  iotwireless: 'Internet of Things',

  // Machine Learning
  bedrock: 'Machine Learning',
  'bedrock-runtime': 'Machine Learning',
  'bedrock-agent': 'Machine Learning',
  'bedrock-agent-runtime': 'Machine Learning',
  'bedrock-agentcore': 'Machine Learning',
  transcribe: 'Machine Learning',
  translate: 'Machine Learning',
  sagemaker: 'Machine Learning',

  // Management & Governance
  cloudformation: 'Management & Governance',
  monitoring: 'Management & Governance',
  logs: 'Management & Governance',
  cloudtrail: 'Management & Governance',
  config: 'Management & Governance',
  cloudcontrolapi: 'Management & Governance',
  organizations: 'Management & Governance',
  account: 'Management & Governance',
  cur: 'Management & Governance',
  budgets: 'Management & Governance',
  tagging: 'Management & Governance',
  inspector2: 'Management & Governance',
  'service-quotas': 'Management & Governance',
  'servicecatalog': 'Management & Governance',

  // Media Services
  mediaconnect: 'Media Services',
  medialive: 'Media Services',
  mediastore: 'Media Services',

  // Migration & Transfer
  transfer: 'Migration & Transfer',
  s3files: 'Migration & Transfer',
  datasync: 'Migration & Transfer',
  dms: 'Migration & Transfer',

  // Networking & Content Delivery
  cloudfront: 'Networking & Content Delivery',
  'cloudfront-keyvaluestore': 'Networking & Content Delivery',
  route53: 'Networking & Content Delivery',
  elasticloadbalancing: 'Networking & Content Delivery',
  location: 'Networking & Content Delivery',
  servicediscovery: 'Networking & Content Delivery',
  imds: 'Networking & Content Delivery',
  vpc: 'Networking & Content Delivery',

  // Security, Identity & Compliance
  iam: 'Security, Identity & Compliance',
  sts: 'Security, Identity & Compliance',
  kms: 'Security, Identity & Compliance',
  secretsmanager: 'Security, Identity & Compliance',
  acm: 'Security, Identity & Compliance',
  'cognito-idp': 'Security, Identity & Compliance',
  waf: 'Security, Identity & Compliance',
  'waf-regional': 'Security, Identity & Compliance',
  wafv2: 'Security, Identity & Compliance',
  guardduty: 'Security, Identity & Compliance',

  // Storage
  s3: 'Storage',
  elasticfilesystem: 'Storage',
  backup: 'Storage',
  glacier: 'Storage',
}

const DESCRIPTION = {
  s3: 'Scalable storage in the cloud',
  sqs: 'Managed message queues',
  sns: 'Managed pub/sub messaging and notifications',
  dynamodb: 'Managed NoSQL database',
  lambda: 'Run code without thinking about servers',
  iam: 'Manage access to resources',
  sts: 'Temporary security credentials',
  kms: 'Create and manage encryption keys',
  secretsmanager: 'Rotate, manage and retrieve secrets',
  ssm: 'Systems management and parameters',
  logs: 'Monitor, store and access log files',
  monitoring: 'Metrics, alarms and dashboards',
  cloudformation: 'Model and provision resources as code',
  cloudtrail: 'Track user activity and API usage',
  events: 'Serverless event bus',
  apigateway: 'Build, deploy and manage APIs',
  appsync: 'Managed GraphQL APIs',
  states: 'Coordinate distributed workflows',
  ses: 'Email sending and receiving',
  acm: 'Provision and manage TLS certificates',
  ec2: 'Virtual servers in the cloud',
  ecs: 'Run and manage containers',
  eks: 'Managed Kubernetes service',
  ecr: 'Container image registry',
  rds: 'Managed relational databases',
  elasticache: 'In-memory cache in the cloud',
  documentdb: 'Managed document database',
  glue: 'Prepare and transform data for analytics',
  athena: 'Query data in place with SQL',
  firehose: 'Deliver streaming data to destinations',
  kinesis: 'Real-time streaming data',
  opensearch: 'Search and analytics engine',
  cloudfront: 'Global content delivery network',
  route53: 'Scalable DNS and domain registration',
  elasticloadbalancing: 'Distribute incoming traffic',
  efs: 'Managed file storage for compute',
  elasticfilesystem: 'Managed file storage for compute',
  backup: 'Centralised backup across services',
  transfer: 'Managed file transfers over SFTP and FTP',
  cognito: 'Identity for your applications',
  'cognito-idp': 'User sign-up, sign-in and access control',
  'cognito-identity': 'Federated identities for applications',
  waf: 'Protect against web exploits',
  wafv2: 'Protect against web exploits',
  iot: 'Connect and manage devices',
  bedrock: 'Build with foundation models',
  transcribe: 'Speech to text',
  translate: 'Translation between languages',
  mq: 'Managed message broker for Apache ActiveMQ',
  scheduler: 'Schedule tasks on a managed service',
  pipes: 'Connect sources to targets without servers',
  batch: 'Run batch computing jobs at scale',
  codebuild: 'Build and test code',
  organizations: 'Centrally manage accounts',
  config: 'Assess, audit and evaluate resource configurations',
  inspector2: 'Automated vulnerability management',
  signer: 'Sign code artifacts',
  appconfig: 'Manage application configuration and feature flags',
  location: 'Maps, places and routing',
  servicediscovery: 'Service registry and discovery',
  budgets: 'Track cost and usage against budgets',
  cur: 'Detailed cost and usage reports',
}

export const categoryOf = (name) => CATEGORY[name] || 'Other'

/** A short line under a service name, AWS-menu style. */
export const describeService = (name) =>
  DESCRIPTION[name] || `Manage ${serviceLabel(name)} resources`

/** Services grouped for the menu, alphabetical inside each category. */
export function groupByCategory(names) {
  const groups = new Map()
  for (const name of [...names].sort()) {
    const category = categoryOf(name)
    if (!groups.has(category)) groups.set(category, [])
    groups.get(category).push(name)
  }
  return CATEGORY_ORDER.filter((category) => groups.has(category)).map(
    (category) => ({ category, services: groups.get(category) }),
  )
}
