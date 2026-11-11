import type {
  ActionCatalogue,
  ActionResult,

  BrowseResult,
  CountsResult,
  CredentialsResult,
  DeleteAccountResult,
  Meta,
  MeResult,
  NewAccessKeyResult,
  NodeRow,
  ObjectsResult,
  ProvisionResult,
  RegionResult,
  SettingsResult,
  UpdateMeResult,
  UserAccount,
} from './types'

interface RequestOptions {
  method?: string
  body?: unknown
  headers?: Record<string, string>
}

// A 401 means the session expired: the server-rendered login page is still the
// only login surface, so bounce there.
async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: 'same-origin',
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(options.headers || {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  })

  if (response.status === 401) {
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
  setGlobalAdmin: (accountId: string, enabled: boolean) =>
    request<{ account: string; global_admin: boolean }>(
      `/api/accounts/${accountId}/admin`,
      { method: 'POST', body: { enabled } },
    ),
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
