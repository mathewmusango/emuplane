export interface AccountSummary {
  account_id: string
  alias: string
  users: number
  regions: string[]
  global_admin: boolean
  default_admin: boolean
  disabled: boolean
}

export interface SessionUser {
  user?: string
  account?: string
  alias?: string
  role?: string
}

export interface MeResult extends SessionUser {
  expires?: number
  name?: string
  email?: string
}

export interface UpdateMeResult {
  user: string
  account: string
  name: string
  email: string
}

export interface Meta {
  product: string
  api_version: string
  recent_limit?: number
  emulator_version: string
  me: SessionUser
  accounts: AccountSummary[]
  regions: string[]
  auto_regions?: string[]
  all_regions: string[]
  platform_admin: boolean
  default_admin: boolean
  other_global_admins: number
  total_accounts: number
  global_admins: number
  gateway: string
  console: string
  uptime_seconds: number
  /** The backend profile the console fronts (control/backends.py). */
  backend_id?: string
  backend?: string
  backend_logo?: string
}

export interface NodeHealth {
  reachable?: boolean
  version?: string
  edition?: string
  auth?: string
  checked_at?: string
  joined?: string
  error?: string
}

export interface NodeRow {
  name: string
  region: string
  endpoint?: string
  static?: boolean
  health?: NodeHealth
}

export interface ResourceDetail {
  [key: string]: string | number | boolean | null | undefined
}

export interface ResourceOwner {
  account?: string
  user?: string
  at?: string
}

export interface ResourceRow {
  name: string
  kind: string
  region?: string
  owner?: ResourceOwner
  detail: ResourceDetail
}

export interface Identity {
  arn?: string
  account?: string
  error?: string
}

export interface BrowseResult {
  account: string
  region: string
  regions?: string[]
  service: string
  identity: Identity
  resources: ResourceRow[]
}

export interface CountsResult {
  account: string
  region: string
  counts: Record<string, number>
}

export interface ObjectRow {
  key: string
  size: string
  modified: string
  storage?: string
}

export interface ObjectsResult {
  account: string
  region: string
  bucket: string
  prefix: string
  objects: ObjectRow[]
}

/** One bucket's settings, shaped like the create form (copy-settings). */
export interface BucketSettings {
  ok: boolean
  bucket: string
  settings: {
    ownership: string
    block_public_access: Record<string, boolean>
    versioning: boolean
    tags: BucketTag[]
    encryption: string
    bucket_key: boolean
    object_lock: boolean
  }
  account?: string
  region?: string
}

/** A listing from one of S3's child APIs (S3 Tables, S3 Files). */
export interface S3ChildListing {
  ok: boolean
  status?: number
  items: Record<string, unknown>[]
  error?: string
  account?: string
  region?: string
  service?: string
}

/** One row of the Access Points page, whichever section it came from. */
export interface AccessPoint {
  name: string
  alias: string
  arn: string
  network_origin: string
  vpc_id: string
  created: string
  status: string
  bucket: string
  buckets: { bucket: string; region: string }[]
  region: string
}

/** POST access points are read from S3 Control, not from the bucket API. */
export interface AccessPointListing {
  ok: boolean
  status?: number
  section?: string
  region?: string
  access_points: AccessPoint[]
  error?: string
  account?: string
}

export interface AccessPointResult {
  ok: boolean
  status?: number
  name: string
  arn?: string
  alias?: string
  /** False when the policy failed after the access point itself was made. */
  created?: boolean
  error?: string
  account?: string
  region?: string
}

export interface AccessPointPolicy {
  ok: boolean
  status?: number
  name: string
  /** null is an access point without a policy, which is a real state. */
  policy: string | null
  error?: string
  account?: string
  region?: string
}

export interface BucketTag {
  Key: string
  Value: string
}

/** The console's create page, as POST /api/s3/buckets takes it. */
export interface CreateBucketOptions {
  account: string
  region: string
  /** The name as typed; the Account Regional namespace suffix is added server-side. */
  bucket: string
  /** `global` or `regional` (AWS's Account Regional namespace). */
  namespace: string
  ownership: string
  block_public_access: Record<string, boolean>
  versioning: boolean
  tags: BucketTag[]
  encryption: string
  bucket_key: boolean
  object_lock: boolean
}

export interface CreateBucketResult {
  ok: boolean
  status?: number
  bucket: string
  /** False when a follow-up setting failed after the bucket itself was made. */
  created?: boolean
  error?: string
  account?: string
  region?: string
  service?: string
}

export interface ActionParam {
  name: string
  label: string
  required?: boolean
  type?: string
  placeholder?: string
  default?: string
}

export interface ActionOperation {
  id: string
  label: string
  cli?: string
  destructive?: boolean
  params: ActionParam[]
}

export interface ActionService {
  description: string
  operations: ActionOperation[]
}

export interface ActionCatalogue {
  services: Record<string, ActionService>
  groups: { label: string; services: string[] }[]
}

export interface ActionResult {
  ok: boolean
  status?: number
  cli?: string
  body?: string
  error?: string
  account?: string
  region?: string
  service?: string
  operation?: string
}

export interface ProvisionResult {
  username: string
  account_id: string
  alias: string
  iam_user?: string
  aws_access_key_id?: string
  aws_secret_access_key?: string
  region: string
  regions: string[]
}

export interface UserRow {
  username: string
  role?: string
  access_key_id?: string
}

export interface UserAccount {
  account_id: string
  alias: string
  name?: string
  regions: string[]
  global_admin: boolean
  users: UserRow[]
}

export interface AccessKeyRow {
  name: string
  access_key_id: string
  masked: string
  masked_secret: string
  created_at: string
}

export interface CredentialsResult {
  account: string
  user: string
  iam_user?: string
  max_keys: number
  keys: AccessKeyRow[]
}

export interface NewAccessKeyResult extends CredentialsResult {
  key?: {
    name: string
    access_key_id: string
    secret_access_key: string
    created_at: string
  } | null
  aws_access_key_id?: string
  aws_secret_access_key?: string
  region?: string
  regions?: string[]
}

export interface RegionResult {
  account: string
  regions: string[]
}

export interface DeleteAccountResult {
  deleted: string
  alias: string
}

export interface SettingsResult {
  signup_enabled: boolean
  instance_regions: string[]
}

// The answer to POST /api/auth/login. `mfa_required` is what decides whether the
// code screen appears; it is false for every account until enrolment exists.
export interface SignInResult {
  ok: boolean
  mfa_required: boolean
  user: string
  account: string
  alias: string
  role: string
  /** Present only when the caller asked for multi-session. */
  token?: string
}
