// Official AWS architecture-service icons (MIT package `aws-icons`, derived from
// the AWS icon set). Imported as URLs so Vite fingerprints and serves them.
import acm from './assets/aws/acm.svg'
import apigateway from './assets/aws/apigateway.svg'
import athena from './assets/aws/athena.svg'
import backup from './assets/aws/backup.svg'
import cloudformation from './assets/aws/cloudformation.svg'
import cloudfront from './assets/aws/cloudfront.svg'
import cloudtrail from './assets/aws/cloudtrail.svg'
import cognito from './assets/aws/cognito.svg'
import config from './assets/aws/config.svg'
import dynamodb from './assets/aws/dynamodb.svg'
import ec2 from './assets/aws/ec2.svg'
import ecr from './assets/aws/ecr.svg'
import ecs from './assets/aws/ecs.svg'
import eks from './assets/aws/eks.svg'
import elasticache from './assets/aws/elasticache.svg'
import events from './assets/aws/events.svg'
import glue from './assets/aws/glue.svg'
import iam from './assets/aws/iam.svg'
import kinesis from './assets/aws/kinesis.svg'
import kms from './assets/aws/kms.svg'
import lambda from './assets/aws/lambda.svg'
import logs from './assets/aws/logs.svg'
import organizations from './assets/aws/organizations.svg'
import rds from './assets/aws/rds.svg'
import route53 from './assets/aws/route53.svg'
import s3 from './assets/aws/s3.svg'
import scheduler from './assets/aws/scheduler.svg'
import secretsmanager from './assets/aws/secretsmanager.svg'
import ses from './assets/aws/ses.svg'
import sns from './assets/aws/sns.svg'
import sqs from './assets/aws/sqs.svg'
import ssm from './assets/aws/ssm.svg'
import stepfunctions from './assets/aws/stepfunctions.svg'
import sts from './assets/aws/sts.svg'
import waf from './assets/aws/waf.svg'
import { Box as BoxIcon } from 'lucide-react'

const ICONS = {
  s3,
  's3tables': s3,
  's3files': s3,
  ec2,
  dynamodb,
  sqs,
  sns,
  lambda,
  'lambda-core': lambda,
  'lambda-microvms': lambda,
  iam,
  sts,
  logs,
  monitoring: logs,
  cloudwatch: logs,
  secretsmanager,
  ssm,
  kinesis,
  stepfunctions,
  states: stepfunctions,
  cloudformation,
  apigateway,
  cloudfront,
  route53,
  ecs,
  eks,
  ecr,
  rds,
  'rds-data': rds,
  dsql: rds,
  elasticache,
  glue,
  athena,
  kms,
  cloudtrail,
  events,
  scheduler,
  waf,
  wafv2: waf,
  acm,
  backup,
  config,
  organizations,
  'cognito-idp': cognito,
  'cognito-identity': cognito,
  ses,
  'elasticloadbalancing': ec2,
  elb: ec2,
  autoscaling: ec2,
}

export function ServiceIcon({ name, size = 18, className }) {
  const src = ICONS[name]
  if (!src) {
    return <BoxIcon size={size} className={className} aria-hidden="true" />
  }
  return (
    <img
      src={src}
      alt=""
      width={size}
      height={size}
      className={className}
      style={{ display: 'inline-block', flexShrink: 0 }}
      aria-hidden="true"
    />
  )
}

export const hasServiceIcon = (name) => Boolean(ICONS[name])

/** The icon's URL, for Cloudscape `iconUrl` slots (buttons, cards). */
export const serviceIconUrl = (name) => ICONS[name]
