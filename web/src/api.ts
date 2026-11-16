import type {
  AccessPointListing,
  AccessPointPolicy,
  AccessPointResult,
  ActionCatalogue,
  ActionResult,
  BucketHead,

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
  ObjectContent,
  ObjectsResult,
  ProvisionResult,
  RegionResult,
  S3ChildListing,
  SettingsResult,
  SignInResult,
  UpdateMeResult,
  UserAccount,
} from './types'

interface RequestOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
  /** Send `body` as it is: a File, not JSON. */
  raw?: boolean
}

// A 401 usually means the session expired: bounce to the login screens. Two cases
// are the exception and keep the server's own sentence — a sign-in call (401 is
// the answer to a wrong password) and the sign-in screens themselves (there is no
// session to lose, and replacing the reason with "session expired" hides it).
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
  s3Objects: (account: string, region: string, bucket: string, prefix = '') =>
    request<ObjectsResult>(
      `/api/s3/objects?${query({ account, region, bucket, prefix })}`,
    ),
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
  ) => `/api/s3/object-download?${query({ account, region, bucket, key })}`,
  emptyBucket: (payload: { account: string; region: string; bucket: string }) =>
    request<ActionResult>('/api/s3/empty', { method: 'POST', body: payload }),
  editBucketSettings: (payload: {
    account: string
    region: string
    bucket: string
    versioning?: boolean
    block_public_access?: Record<string, boolean>
    tags?: { Key: string; Value: string }[]
    encryption?: string
    bucket_key?: boolean
  }) => request<ActionResult>('/api/s3/bucket-settings-edit', { method: 'POST', body: payload }),
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
  accessPointPolicy: (account: string, region: string, name: string) =>
    request<AccessPointPolicy>(
      `/api/s3/access-point-policy?${query({ account, region, name })}`,
    ),
  editAccessPointPolicy: (payload: {
    account: string
    region: string
    name: string
    policy: string | null
  }) =>
    request<AccessPointPolicy>('/api/s3/access-point-policy-edit', {
      method: 'POST',
      body: payload,
    }),
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
