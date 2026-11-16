// Shared fixtures for the console suite: one API picture, one fetch stub.
//
// Both `smoke.test.jsx` (console-wide behaviour) and `s3.test.jsx` (the S3 page)
// read from here, so the two files describe the same instance.

import { vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { SessionProvider } from '../../web/src/context'

export const META = {
  product: 'Emuplane',
  backend: 'MiniStack',
  backend_id: 'ministack',
  backend_logo: '/backends/ministack.png',
  api_version: 'v1',
  emulator_version: '1.5.37',
  me: { user: 'mathewmusango', account: '111111111111', alias: 'mathewmusango', role: 'root' },
  accounts: [
    { account_id: '111111111111', alias: 'mathewmusango', users: 1 },
    { account_id: '161418427515', alias: 'musangomathew', users: 1 },
  ],
  platform_admin: true,
  regions: ['us-east-1', 'us-west-2'],
  all_regions: ['us-east-1', 'us-west-2'],
  gateway: 'https://ministack.example.com',
  console: 'https://ministack-control.example.com',
  uptime_seconds: 60,
}

export const ACTIONS = {
  services: {
    s3: {
      description: 'Buckets and objects.',
      operations: [
        {
          id: 'create-bucket',
          label: 'Create bucket',
          cli: 'aws s3 mb s3://<bucket>',
          params: [{ name: 'Bucket', label: 'Bucket name', required: true, type: 'text' }],
        },
      ],
    },
  },
  groups: [{ label: 'Core', services: ['s3'] }],
}

export const RESPONSES = {
  '/api/meta': META,
  '/api/auth/login': {
    ok: true,
    token: 'login-token',
    mfa_required: false,
    user: 'root@example.com',
    account: '111111111111',
    alias: 'mathewmusango',
    role: 'root',
  },
  '/api/auth/mfa': { ok: true },
  '/api/auth/remember': {
    ok: true,
    token: 'test-token',
    user: 'mathewmusango',
    account: '111111111111',
    alias: 'mathewmusango',
    role: 'root',
  },
  '/api/services': { s3: { emuplane: true } },
  '/api/actions': ACTIONS,
  '/api/users': [
    {
      account_id: '111111111111',
      alias: 'mathewmusango',
      name: 'Mathew Musango',
      regions: ['us-east-1'],
      global_admin: true,
      default_admin: false,
      disabled: false,
      users: [{ username: 'mathewmusango', role: 'root' }],
    },
  ],
  '/api/nodes': [],
  '/api/settings': { signup_enabled: true },
  '/api/accounts/me': {
    user: 'mathewmusango',
    account: '111111111111',
    alias: 'mathewmusango',
    role: 'root',
    name: 'Mathew Musango',
    email: 'mathew@example.com',
  },
  '/api/credentials': {
    account: '111111111111',
    user: 'mathewmusango',
    max_keys: 2,
    keys: [
      {
        name: 'laptop-cli',
        access_key_id: 'AKIDEXAMPLE00000001',
        masked: 'AKIA••••••••MPLE',
        masked_secret: '••••••••••••',
        created_at: '2026-11-05 09:00:00Z',
      },
      {
        name: 'ci-pipeline',
        access_key_id: 'AKIDEXAMPLE00000002',
        masked: 'AKIA••••••••MPLE',
        masked_secret: '••••••••••••',
        created_at: '2026-11-05 10:00:00Z',
      },
    ],
  },
  '/api/browse': {
    account: '111111111111',
    region: 'us-east-1',
    regions: ['us-east-1', 'us-west-2'],
    service: 's3',
    resources: [
      {
        name: 'logs-bucket',
        kind: 'bucket',
        region: 'us-east-1',
        owner: { account: '111111111111', user: 'mathewmusango' },
        detail: {},
      },
    ],
  },
  '/api/s3/objects': {
    bucket: 'logs-bucket',
    objects: [
      { key: 'reports/2026.csv', size: '12', modified: '2026-11-04T00:00:00Z' },
    ],
  },
  '/api/s3/object': {
    ok: true,
    key: 'reports/2026.csv',
    body: 'date,total\n2026-01-01,10',
    binary: false,
    size: 24,
    content_type: 'text/csv',
    etag: 'd41d8cd98f00b204e9800998ecf8427e',
    last_modified: 'Mon, 16 Nov 2026 13:06:12 GMT',
    truncated: false,
    region: 'us-east-1',
  },
  // HeadBucket: the bucket's own region, which may not be the one asked with.
  '/api/s3/bucket-head': (url) => {
    const bucket = new URL(url, 'http://console').searchParams.get('bucket') || ''
    return {
      ok: true,
      exists: true,
      status: 200,
      region: bucket.startsWith('west') ? 'us-west-2' : 'us-east-1',
    }
  },
  '/api/s3/bucket-documents': {
    ok: true,
    bucket: 'logs-bucket',
    documents: {
      lifecycle: null,
      cors: null,
      policy: '<Policy><Statement><Effect>Allow</Effect></Statement></Policy>',
      acl: null,
      logging: null,
      notifications: null,
      replication: null,
      versions: '<ListVersionsResult><Name>logs-bucket</Name></ListVersionsResult>',
    },
  },
  '/api/s3/table-buckets': {
    ok: true,
    status: 200,
    items: [
      {
        arn: 'arn:aws:s3tables:us-east-1:111111111111:bucket/analytics-tables',
        name: 'analytics-tables',
        createdAt: '2026-11-16T09:00:00Z',
      },
    ],
  },
  '/api/s3/file-systems': {
    ok: true,
    status: 200,
    items: [
      {
        fileSystemId: 'fs-0123456789abcdef',
        name: '',
        bucket: 'logs-bucket',
        status: 'available',
        creationTime: 1794822084,
      },
    ],
  },
  // The Access Points page reads three sections from one path, so its fixture is
  // a function of the query: an answer per section, as S3 Control would give.
  '/api/s3/access-points': (url) => {
    const section = new URL(url, 'http://console').searchParams.get('section') || 'general'
    if (section === 'multi-region') {
      return {
        ok: true,
        status: 200,
        section,
        region: 'us-west-2',
        access_points: [
          {
            name: 'world-point',
            alias: 'world-point.mrap',
            arn: 'arn:aws:s3::111111111111:accesspoint/world-point.mrap',
            network_origin: 'Internet',
            vpc_id: '',
            created: '2026-11-16T09:00:00Z',
            status: 'READY',
            bucket: '',
            buckets: [
              { bucket: 'logs-bucket', region: 'us-east-1' },
              { bucket: 'west-bucket', region: 'us-west-2' },
            ],
            region: 'us-west-2',
          },
        ],
      }
    }
    if (section === 'object-lambda') {
      return { ok: true, status: 200, section, region: 'us-east-1', access_points: [] }
    }
    return {
      ok: true,
      status: 200,
      section,
      region: 'us-east-1',
      access_points: [
        {
          name: 'reports-point',
          alias: 'reports-point-4ud6rlwts3alias',
          arn: 'arn:aws:s3:us-east-1:111111111111:accesspoint/reports-point',
          network_origin: 'Internet',
          vpc_id: '',
          created: '2026-11-16T09:00:00Z',
          status: 'READY',
          bucket: 'logs-bucket',
          buckets: [],
          region: 'us-east-1',
        },
      ],
    }
  },
  '/api/s3/access-point-policy': {
    ok: true,
    status: 200,
    name: 'reports-point',
    policy: null,
  },
  '/api/s3/access-point-delete': { ok: true, status: 204, name: 'reports-point' },
  '/api/s3/access-point-policy-edit': {
    ok: true,
    status: 200,
    name: 'reports-point',
    policy: null,
  },
  '/api/s3/bucket-settings': {
    ok: true,
    bucket: 'logs-bucket',
    settings: {
      ownership: 'BucketOwnerPreferred',
      block_public_access: {
        BlockPublicAcls: false,
        IgnorePublicAcls: true,
        BlockPublicPolicy: true,
        RestrictPublicBuckets: true,
      },
      versioning: true,
      tags: [{ Key: 'team', Value: 'platform' }],
      encryption: 'aws:kms',
      bucket_key: true,
      object_lock: false,
    },
  },
}

/** Install the fetch stub the console talks to. A fixture is either the answer or
 *  a function of the request URL, for a path that answers differently per query. */
export const installFetch = () =>
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      const path = String(url).split('?')[0]
      const answer = RESPONSES[path] ?? {}
      return {
        ok: true,
        status: 200,
        text: async () =>
          JSON.stringify(typeof answer === 'function' ? answer(String(url)) : answer),
      }
    }),
  )

export const renderAt = (element, entries = ['/']) =>
  render(
    <MemoryRouter initialEntries={entries}>
      <SessionProvider>{element}</SessionProvider>
    </MemoryRouter>,
  )
