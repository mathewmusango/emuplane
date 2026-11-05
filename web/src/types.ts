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

export interface Meta {
  product: string
  api_version: string
  mode: string
  auth: string
  audit_enabled: boolean
  login?: string
  recent_limit?: number
  version: string
  me: SessionUser
  accounts: AccountSummary[]
  accounts_scope: string
  regions: string[]
  all_regions: string[]
  node_regions: string[]
  active_regions: string[]
  platform_admin: boolean
  signup_enabled: boolean
  default_admin: boolean
  other_global_admins: number
  total_accounts: number
  global_admins: number
  gateway: string
  console: string
  uptime_seconds: number
  checked_at: string
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
  last_seen?: number
  health?: NodeHealth
}

export interface ResourceDetail {
  [key: string]: string | number | boolean | null | undefined
}

export interface ResourceRow {
  name: string
  kind: string
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
  subject_bound?: boolean
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

export interface AuditEntry {
  at: string
  actor: string
  action: string
  target: string
  detail?: Record<string, unknown>
}
