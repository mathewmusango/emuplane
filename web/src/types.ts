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
  /** A listing is one page of up to 1000 keys; the rest is asked for with `next_token`. */
  truncated?: boolean
  next_token?: string
}

/** One version of one key, as ListObjectVersions lists it. */
export interface VersionRow {
  key: string
  /** The ID DeleteObject takes back; `null` is only for a bucket that never versioned. */
  version_id: string
  latest: boolean
  /** True for a marker: its bytes are gone, the position in the stack is not. */
  delete_marker: boolean
  size: string
  modified: string
  storage: string
}

export interface VersionsResult {
  ok: boolean
  bucket: string
  prefix?: string
  versions: VersionRow[]
  /** A listing is one page; the rest is asked for with the two markers. */
  truncated?: boolean
  next_key_marker?: string
  next_version_id_marker?: string
  account?: string
  region?: string
  error?: string
}

/** One multipart upload that was started and never completed. */
export interface UploadRow {
  key: string
  upload_id: string
  initiated: string
  storage: string
}

export interface UploadsResult {
  ok: boolean
  bucket: string
  uploads: UploadRow[]
  /** A listing is one page; the rest is asked for with the two markers. */
  truncated?: boolean
  next_key_marker?: string
  next_upload_id_marker?: string
  account?: string
  region?: string
  error?: string
}

/** One part an unfinished upload already holds. */
export interface UploadPartRow {
  part_number: string
  size: string
  etag: string
  modified: string
}

export interface UploadPartsResult {
  ok: boolean
  bucket: string
  key: string
  upload_id: string
  parts: UploadPartRow[]
  /** ListParts is paged too, by part number. */
  truncated?: boolean
  next_part_number_marker?: string
  account?: string
  region?: string
  error?: string
}

/** One grant on an object, as GetObjectAcl reports it. */
export interface ObjectAclGrant {
  /** CanonicalUser, Group or AmazonCustomerByEmail. */
  type: string
  id: string
  display_name: string
  uri: string
  permission: string
}

export interface ObjectAclResult {
  ok: boolean
  status?: number
  bucket: string
  key: string
  /** Empty is the version the key resolves to. */
  version_id?: string
  owner: { id: string; display_name: string }
  grants: ObjectAclGrant[]
  /** True when a grant names the AllUsers group. */
  public: boolean
  /** The ACL document as S3 answers it. */
  acl: string
  account?: string
  region?: string
  error?: string
}

/** One bucket's settings, shaped like the create form (copy-settings). */
export interface BucketSettings {
  ok: boolean
  bucket: string
  settings: {
    ownership: string
    block_public_access: Record<string, boolean>
    public_access_block_configured: boolean
    versioning: boolean
    /** S3's own three answers: `Disabled` was never on, and `Enabled` can only ever become `Suspended`. */
    versioning_status: 'Disabled' | 'Enabled' | 'Suspended'
    /** Empty when the endpoint omits the element, which is not the same as `Disabled`. */
    mfa_delete: string
    /** `endpoint` when S3 answered it, `control` when Emuplane keeps and enforces it. */
    mfa_delete_source: 'endpoint' | 'control'
    /** When the bucket was made, as `ListBuckets` reports it; empty when the listing did not name it. */
    created: string
    tags: BucketTag[]
    encryption: string
    bucket_key: boolean
    object_lock: boolean
  }
  account?: string
  region?: string
}

/** One object read back: its text, or why it is a download instead. */
export interface ObjectContent {
  ok: boolean
  key: string
  /** null when the object is binary: there is no text to show. */
  body: string | null
  binary: boolean
  size: number
  content_type: string
  /** From HeadObject: a GET's bytes cannot carry them. */
  etag: string
  last_modified: string
  /** True when the text shown is the first 20 000 characters. */
  truncated: boolean
  account?: string
  region?: string
  error?: string
}

/** One of an object's annotations, as ListObjectAnnotations lists it. */
export interface ObjectAnnotationRow {
  name: string
  size: string
  modified: string
  etag: string
}

/** The reads beside an object: tags, annotations and the two Object Lock states; `errors` carries only what genuinely failed. */
export interface ObjectMeta {
  ok: boolean
  bucket: string
  key: string
  tags: BucketTag[]
  annotations: ObjectAnnotationRow[]
  /** The retention and legal-hold documents as S3 answers them; null when unset. */
  retention: string | null
  legal_hold: string | null
  errors: Record<string, string>
  account?: string
  region?: string
  error?: string
}

/** GetObjectAnnotation: one annotation's own content, which is text. */
export interface ObjectAnnotation {
  ok: boolean
  name: string
  body: string
  error?: string
}

/** HeadBucket: whether a name exists, and the region it lives in. */
export interface BucketHead {
  ok: boolean
  exists: boolean
  status?: number
  /** The bucket's own region, from `x-amz-bucket-region`. */
  region: string
  /** The region the page asked with, which may not be the right one. */
  requested_region?: string
  account?: string
  error?: string
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

/** One access point read in full, from the section that owns it. */
export interface AccessPointDetail {
  ok: boolean
  status?: number
  section: string
  name: string
  alias: string
  arn?: string
  /** The resource's own state (READY), not the HTTP status. */
  state?: string
  created?: string
  region?: string
  /** Multi-Region: the member buckets and how much traffic each takes. */
  buckets?: { bucket: string; region: string }[]
  routes?: { bucket: string; region: string; traffic: string }[]
  /** Object Lambda: the configuration document S3 answers with. */
  configuration?: string | null
  /** null is an access point without a policy, which is a real state. */
  policy?: string | null
  /** Only what genuinely failed: a missing policy is not an error. */
  errors?: Record<string, string>
  account?: string
  error?: string
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

/** One asynchronous Multi-Region operation: what was asked for, what came back, and the token that names it. */
export interface MultiRegionOperation {
  token: string
  /** CreateMultiRegionAccessPoint, and the other operations that answer with a token. */
  operation: string
  /** SUCCEEDED, FAILED, INPROGRESS — the operation's own status, not the HTTP one. */
  status: string
  created: string
  name: string
  /** The members the request named. */
  buckets: string[]
  /** One row per Region the operation touched. */
  results: { region: string; status: string }[]
  error: { code: string; message: string } | null
}

/** CreateMultiRegionAccessPoint: `ok` means the request was made and its operation read; `created` means it ended SUCCEEDED. */
export interface MultiRegionResult {
  ok: boolean
  status?: number
  name: string
  created: boolean
  operation?: MultiRegionOperation
  error?: string
  account?: string
  region?: string
}

/** SubmitMultiRegionAccessPointRoutes: a dial per member, answered with no token. */
export interface MultiRegionRoutesResult {
  ok: boolean
  status?: number
  arn: string
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

// The answer to POST /api/auth/login; `mfa_required` decides whether the code screen appears.
export interface MfaDevice {
  serial: string
  user: string
  enabled: boolean
}

export interface MfaStatus {
  enabled: boolean
  serial: string
  devices: MfaDevice[]
}

export interface SignInResult {
  ok: boolean
  mfa_required: boolean
  user: string
  account: string
  alias: string
  role: string
  /** Present only when the caller asked for multi-session. */
  token?: string
  /** Present only when the password was right and a TOTP code is still owed. */
  mfa_token?: string
}
