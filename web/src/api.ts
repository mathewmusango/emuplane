import type {
  AccessPointListing,
  AccessPointDetail,
  AccessPointPolicy,
  AccessPointResult,
  ActionCatalogue,
  ActionResult,
  BucketHead,
  MultiRegionResult,
  MultiRegionRoutesResult,

  BrowseResult,
  BucketSettings,
  CountsResult,
  CreateBucketOptions,
  CreateBucketResult,
  CredentialsResult,
  DeleteAccountResult,
  Meta,
  MeResult,
  NewAccessKeyResult,
  NodeRow,
  ObjectAnnotation,
  ObjectAclResult,
  ObjectContent,
  ObjectMeta,
  ObjectsResult,
  ProvisionResult,
  RegionResult,
  S3ChildListing,
  SettingsResult,
  SignInResult,
  UpdateMeResult,
  UploadPartsResult,
  UploadsResult,
  UserAccount,
  VersionsResult,
} from './types'

interface RequestOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
  /** Send `body` as it is: a File, not JSON. */
  raw?: boolean
}

// A 401 usually means the session expired: bounce to the login screens, except sign-in calls and the sign-in screens, which keep the server's sentence.
const SIGNED_OUT_ROUTES = ['/login', '/signin', '/forgot']

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { raw, ...init } = options
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: {
      ...(options.body && !raw ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
    body: options.body
      ? raw
        ? (options.body as BodyInit)
        : JSON.stringify(options.body)
      : undefined,
  })

  const onSignIn = SIGNED_OUT_ROUTES.includes(window.location.pathname)
  if (response.status === 401 && !path.startsWith('/api/auth/') && !onSignIn) {
    const next = encodeURIComponent(window.location.pathname + window.location.search)
    window.location.assign(`/login?next=${next}`)
    throw new Error('Your session expired. Sign in again.')
  }

  const text = await response.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { raw: text }
    }
  }

  if (!response.ok) {
    const payload = data as { error?: string; message?: string } | null
    throw new Error(payload?.error || payload?.message || `HTTP ${response.status}`)
  }
  return data as T
}

const query = (params: Record<string, string>): string =>
  Object.entries(params)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join('&')

export const api = {
  meta: () => request<Meta>('/api/meta'),
  signIn: (payload: {
    mode: 'root' | 'iam'
    email?: string
    account?: string
    username?: string
    password: string
    multi?: boolean
  }) => request<SignInResult>('/api/auth/login', { method: 'POST', body: payload }),
  remember: () => request<SignInResult>('/api/auth/remember', { method: 'POST' }),
  switchIdentity: (token: string) =>
    request<SignInResult>('/api/auth/switch', { method: 'POST', body: { token } }),
  verifyMfa: (payload: { code: string }) =>
    request<{ ok: boolean }>('/api/auth/mfa', { method: 'POST', body: payload }),
  actions: () => request<ActionCatalogue>('/api/actions'),
  services: () => request<Record<string, Record<string, unknown>>>('/api/services'),
  users: () => request<UserAccount[]>('/api/users'),
  nodes: () => request<NodeRow[]>('/api/nodes'),
  browse: (account: string, region: string, service: string) =>
    request<BrowseResult>(`/api/browse?${query({ account, region, service })}`),
  counts: (account: string, region: string) =>
    request<CountsResult>(`/api/counts?${query({ account, region })}`),
  s3Objects: (
    account: string,
    region: string,
    bucket: string,
    prefix = '',
    continuation_token = '',
  ) =>
    request<ObjectsResult>(
      `/api/s3/objects?${query({ account, region, bucket, prefix, continuation_token })}`,
    ),
  /** ListObjectVersions: every version and delete marker under the prefix. */
  versions: (
    account: string,
    region: string,
    bucket: string,
    prefix = '',
    key_marker = '',
    version_id_marker = '',
  ) =>
    request<VersionsResult>(
      `/api/s3/versions?${query({
        account,
        region,
        bucket,
        prefix,
        key_marker,
        version_id_marker,
      })}`,
    ),
  /** ListMultipartUploads: the uploads that were started and never finished. */
  uploads: (
    account: string,
    region: string,
    bucket: string,
    prefix = '',
    key_marker = '',
    upload_id_marker = '',
  ) =>
    request<UploadsResult>(
      `/api/s3/uploads?${query({
        account,
        region,
        bucket,
        prefix,
        key_marker,
        upload_id_marker,
      })}`,
    ),
  /** ListParts: what one unfinished upload already holds. */
  uploadParts: (
    account: string,
    region: string,
    bucket: string,
    key: string,
    upload_id: string,
    part_number_marker = '',
  ) =>
    request<UploadPartsResult>(
      `/api/s3/upload-parts?${query({
        account,
        region,
        bucket,
        key,
        upload_id,
        part_number_marker,
      })}`,
    ),
  /** DeleteObject with a versionId: one version goes, the rest of the key stays. */
  deleteVersion: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    version_id: string
  }) => request<ActionResult>('/api/s3/object-version-delete', { method: 'POST', body: payload }),
  createBucket: (payload: CreateBucketOptions) =>
    request<CreateBucketResult>('/api/s3/buckets', { method: 'POST', body: payload }),
  putObject: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    body: string
  }) => request<ActionResult>('/api/s3/object', { method: 'POST', body: payload }),
  /** A file from the operator's machine: its bytes as the body, its type as sent. */
  uploadObjectFile: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    file: File
  }) =>
    request<ActionResult>(
      `/api/s3/object-upload?${query({
        account: payload.account,
        region: payload.region,
        bucket: payload.bucket,
        key: payload.key,
      })}`,
      {
        method: 'POST',
        raw: true,
        body: payload.file,
        headers: { 'Content-Type': payload.file.type || 'application/octet-stream' },
      },
    ),
  objectDownloadUrl: (
    account: string,
    region: string,
    bucket: string,
    key: string,
    version_id = '',
  ) =>
    `/api/s3/object-download?${query({ account, region, bucket, key, version_id })}`,
  emptyBucket: (payload: { account: string; region: string; bucket: string }) =>
    request<ActionResult>('/api/s3/empty', { method: 'POST', body: payload }),
  editBucketSettings: (payload: {
    account: string
    region: string
    bucket: string
    versioning?: boolean
    versioning_status?: string
    mfa_delete?: string
    ownership?: string
    block_public_access?: Record<string, boolean>
    remove_public_access_block?: boolean
    tags?: { Key: string; Value: string }[]
    remove_tags?: boolean
    encryption?: string
    bucket_key?: boolean
    remove_encryption?: boolean
  }) => request<ActionResult>('/api/s3/bucket-settings-edit', { method: 'POST', body: payload }),
  /** Storage class or per-object encryption: a CopyObject onto the object itself. */
  rewriteObject: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    storage_class?: string
    encryption?: string
  }) => request<ActionResult>('/api/s3/object-rewrite', { method: 'POST', body: payload }),
  /** PutObjectAcl with a canned grant; a bucket that disables ACLs refuses it. */
  setObjectAcl: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    canned_acl: string
    /** An ACL belongs to a version; empty is the one the key resolves to. */
    version_id?: string
  }) => request<ActionResult>('/api/s3/object-acl', { method: 'POST', body: payload }),
  /** GetObjectAcl: the owner and the grants, read back after a grant was written. */
  objectAcl: (
    account: string,
    region: string,
    bucket: string,
    key: string,
    version_id = '',
  ) =>
    request<ObjectAclResult>(
      `/api/s3/object-acl?${query({ account, region, bucket, key, version_id })}`,
    ),
  /** CopyObject: a PUT to the destination, with the source named in a header. */
  copyObject: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    destination: string
    destination_region?: string
    destination_key?: string
  }) => request<ActionResult>('/api/s3/object-copy', { method: 'POST', body: payload }),
  bucketDocuments: (account: string, region: string, bucket: string) =>
    request<{
      ok: boolean
      documents: Record<string, string | null>
      editable: Record<
        string,
        { delete: boolean; kind: 'xml' | 'json'; root: string }
      >
    }>(`/api/s3/bucket-documents?${query({ account, region, bucket })}`),
  /** PutBucket<X> for one configuration document. */
  writeBucketDocument: (payload: {
    account: string
    region: string
    bucket: string
    document: string
    body: string
  }) =>
    request<ActionResult>('/api/s3/bucket-document', {
      method: 'POST',
      body: { ...payload, action: 'save' },
    }),
  /** DeleteBucket<X>, or an empty document where S3 has no DELETE. */
  clearBucketDocument: (payload: {
    account: string
    region: string
    bucket: string
    document: string
  }) =>
    request<ActionResult>('/api/s3/bucket-document', {
      method: 'POST',
      body: { ...payload, action: 'clear' },
    }),
  readObject: (account: string, region: string, bucket: string, key: string) =>
    request<ObjectContent>(
      `/api/s3/object?${query({ account, region, bucket, key })}`,
    ),
  /** The reads beside an object: tags, annotations, retention, legal hold. */
  objectMeta: (account: string, region: string, bucket: string, key: string) =>
    request<ObjectMeta>(
      `/api/s3/object-meta?${query({ account, region, bucket, key })}`,
    ),
  /** GetObjectAnnotation: one annotation's own content. */
  objectAnnotation: (
    account: string,
    region: string,
    bucket: string,
    key: string,
    name: string,
  ) =>
    request<ObjectAnnotation>(
      `/api/s3/object-annotation?${query({ account, region, bucket, key, name })}`,
    ),
  /** PutObjectTagging, or DeleteObjectTagging when the list is empty. */
  editObjectTags: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    tags: { Key: string; Value: string }[]
  }) => request<ActionResult>('/api/s3/object-tags', { method: 'POST', body: payload }),
  /** PutObjectAnnotation: the annotation's own content is text. */
  writeObjectAnnotation: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    name: string
    body: string
  }) => request<ActionResult>('/api/s3/object-annotation', { method: 'POST', body: payload }),
  removeObjectAnnotation: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    name: string
  }) =>
    request<ActionResult>('/api/s3/object-annotation', {
      method: 'POST',
      body: { ...payload, remove: true },
    }),
  setObjectRetention: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    mode: string
    until: string
  }) => request<ActionResult>('/api/s3/object-retention', { method: 'POST', body: payload }),
  setObjectLegalHold: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    status: 'ON' | 'OFF'
  }) => request<ActionResult>('/api/s3/object-legal-hold', { method: 'POST', body: payload }),
  createMultipartUpload: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    content_type?: string
  }) =>
    request<{ ok: boolean; upload_id: string; error?: string }>('/api/s3/multipart-create', {
      method: 'POST',
      body: payload,
    }),
  uploadObjectPart: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    upload_id: string
    part_number: number
    data: Blob
  }) =>
    request<{ ok: boolean; etag: string; error?: string }>(
      `/api/s3/multipart-part?${query({
        account: payload.account,
        region: payload.region,
        bucket: payload.bucket,
        key: payload.key,
        upload_id: payload.upload_id,
        part_number: String(payload.part_number),
      })}`,
      {
        method: 'POST',
        raw: true,
        body: payload.data,
        headers: { 'Content-Type': 'application/octet-stream' },
      },
    ),
  completeMultipartUpload: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    upload_id: string
    parts: { part_number: number; etag: string }[]
  }) =>
    request<ActionResult>('/api/s3/multipart-complete', { method: 'POST', body: payload }),
  abortMultipartUpload: (payload: {
    account: string
    region: string
    bucket: string
    key: string
    upload_id: string
  }) => request<ActionResult>('/api/s3/multipart-abort', { method: 'POST', body: payload }),
  bucketSettings: (account: string, region: string, bucket: string) =>
    request<BucketSettings>(
      `/api/s3/bucket-settings?${query({ account, region, bucket })}`,
    ),
  /** HeadBucket: does it exist, and where does it really live? */
  headBucket: (account: string, region: string, bucket: string) =>
    request<BucketHead>(
      `/api/s3/bucket-head?${query({ account, region, bucket })}`,
    ),
  // S3's other tabs are other APIs: S3 Tables and S3 Files.
  s3TableBuckets: (account: string, region: string) =>
    request<S3ChildListing>(`/api/s3/table-buckets?${query({ account, region })}`),
  s3FileSystems: (account: string, region: string) =>
    request<S3ChildListing>(`/api/s3/file-systems?${query({ account, region })}`),
  // Access points are S3 Control, and each section is read from its own region.
  accessPoints: (
    account: string,
    region: string,
    section: 'general' | 'multi-region' | 'object-lambda',
  ) =>
    request<AccessPointListing>(
      `/api/s3/access-points?${query({ account, region, section })}`,
    ),
  createAccessPoint: (payload: {
    account: string
    region: string
    name: string
    bucket: string
    vpc_id?: string
    block_public_access?: Record<string, boolean>
    policy?: string
  }) => request<AccessPointResult>('/api/s3/access-points', { method: 'POST', body: payload }),
  deleteAccessPoint: (payload: { account: string; region: string; name: string }) =>
    request<AccessPointResult>('/api/s3/access-point-delete', { method: 'POST', body: payload }),
  /** CreateAccessPointForObjectLambda: the configuration PUT creates the access point. */
  createObjectLambdaAccessPoint: (payload: {
    account: string
    region: string
    name: string
    supporting_access_point: string
    function_arn: string
    actions: string[]
    cloudwatch_metrics?: boolean
  }) => request<AccessPointResult>('/api/s3/object-lambda', { method: 'POST', body: payload }),
  deleteObjectLambdaAccessPoint: (payload: { account: string; region: string; name: string }) =>
    request<AccessPointResult>('/api/s3/object-lambda-delete', {
      method: 'POST',
      body: payload,
    }),
  /** PutAccessPointConfigurationForObjectLambda: the document the details view shows. */
  editObjectLambdaConfiguration: (payload: {
    account: string
    region: string
    name: string
    configuration: string
  }) =>
    request<AccessPointResult>('/api/s3/object-lambda-configuration', {
      method: 'POST',
      body: payload,
    }),
  /** One access point in full: an MRAP's report, policy and routes, or an Object Lambda access point's configuration and policy. */
  accessPointDetail: (
    account: string,
    region: string,
    section: 'multi-region' | 'object-lambda',
    name: string,
  ) =>
    request<AccessPointDetail>(
      `/api/s3/access-point-detail?${query({ account, region, section, name })}`,
    ),
  accessPointPolicy: (
    account: string,
    region: string,
    name: string,
    section: 'general' | 'multi-region' | 'object-lambda' = 'general',
  ) =>
    request<AccessPointPolicy>(
      `/api/s3/access-point-policy?${query({ account, region, name, section })}`,
    ),
  editAccessPointPolicy: (payload: {
    account: string
    region: string
    name: string
    policy: string | null
    section?: 'general' | 'object-lambda'
  }) =>
    request<AccessPointPolicy>('/api/s3/access-point-policy-edit', {
      method: 'POST',
      body: payload,
    }),
  /** CreateMultiRegionAccessPoint: the operation it answers with, and the token that lives only in that answer. */
  createMultiRegionAccessPoint: (payload: {
    account: string
    region: string
    name: string
    buckets: string[]
  }) => request<MultiRegionResult>('/api/s3/mrap', { method: 'POST', body: payload }),
  deleteMultiRegionAccessPoint: (payload: { account: string; region: string; name: string }) =>
    request<MultiRegionResult>('/api/s3/mrap-delete', { method: 'POST', body: payload }),
  /** PutMultiRegionAccessPointPolicy: replaced, never removed — S3 Control has no delete for a Multi-Region policy. */
  editMultiRegionPolicy: (payload: {
    account: string
    region: string
    name: string
    policy: string
  }) => request<MultiRegionResult>('/api/s3/mrap-policy', { method: 'POST', body: payload }),
  /** SubmitMultiRegionAccessPointRoutes: 0 (Inactive) or 100 (Active) per member. */
  submitMultiRegionRoutes: (payload: {
    account: string
    region: string
    arn: string
    routes: { bucket: string; traffic: string }[]
  }) => request<MultiRegionRoutesResult>('/api/s3/mrap-routes', { method: 'POST', body: payload }),
  exec: (payload: {
    account: string
    region: string
    service: string
    operation: string
    params: Record<string, string | boolean>
  }) => request<ActionResult>('/api/exec', { method: 'POST', body: payload }),
  provision: (payload: { username: string; name?: string; email: string; password: string }) =>
    request<ProvisionResult>('/api/accounts', { method: 'POST', body: payload }),
  credentials: () => request<CredentialsResult>('/api/credentials'),
  createAccessKey: (name: string) =>
    request<NewAccessKeyResult>('/api/credentials', {
      method: 'POST',
      body: { action: 'create', name },
    }),
  deleteAccessKey: (accessKeyId: string) =>
    request<NewAccessKeyResult>('/api/credentials', {
      method: 'POST',
      body: { action: 'delete', access_key_id: accessKeyId },
    }),
  setRegion: (account: string, region: string, enabled: boolean) =>
    request<RegionResult>('/api/regions', {
      method: 'POST',
      body: { account, region, enabled },
    }),
  setAccountDisabled: (accountId: string, disabled: boolean) =>
    request<{ account: string; disabled: boolean }>(
      `/api/accounts/${accountId}/disabled`,
      { method: 'POST', body: { disabled } },
    ),
  deleteAccount: (accountId: string) =>
    request<DeleteAccountResult>(`/api/accounts/${accountId}`, { method: 'DELETE' }),
  settings: () => request<SettingsResult>('/api/settings'),
  setSettings: (payload: Partial<SettingsResult>) =>
    request<SettingsResult>('/api/settings', { method: 'POST', body: payload }),
  me: () => request<MeResult>('/api/accounts/me'),
  updateMe: (payload: {
    name?: string
    email?: string
    current_password?: string
    new_password?: string
  }) => request<UpdateMeResult>('/api/me', { method: 'POST', body: payload }),
}
