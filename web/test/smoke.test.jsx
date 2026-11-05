import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { SessionProvider } from '../src/context'
import App from '../src/App'
import Onboarding from '../src/pages/Onboarding'
import Resources from '../src/pages/Resources'
import Settings from '../src/pages/Settings'
import Accounts from '../src/pages/Accounts'
import About from '../src/pages/About'

const META = {
  product: 'MiniStack',
  api_version: 'v1',
  mode: 'central',
  auth: 'both',
  version: '1.5.37',
  me: { user: 'mathewmusango', account: '111111111111', alias: 'mathewmusango', role: 'root' },
  accounts: [
    { account_id: '111111111111', alias: 'mathewmusango', users: 1 },
    { account_id: '161418427515', alias: 'musangomathew', users: 1 },
  ],
  accounts_scope: 'global',
  platform_admin: true,
  regions: ['us-east-1', 'us-west-2'],
  active_regions: ['us-east-1'],
  gateway: 'https://ministack.mus.com',
  console: 'https://ministack-control.mus.com',
  checked_at: '',
}

const ACTIONS = {
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

const RESPONSES = {
  '/api/meta': META,
  '/api/services': { s3: { ministack: true } },
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
      users: [{ username: 'mathewmusango', role: 'root', subject_bound: false }],
    },
  ],
  '/api/nodes': [],
  '/api/settings': { signup_enabled: true },
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
  '/api/audit': [],
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
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url) => {
      const path = String(url).split('?')[0]
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify(RESPONSES[path] ?? {}),
      }
    }),
  )
})

const renderAt = (element) =>
  render(
    <MemoryRouter>
      <SessionProvider>{element}</SessionProvider>
    </MemoryRouter>,
  )

describe('console', () => {
  it('renders the dashboard shell with the account and region', async () => {
    renderAt(<App />)
    expect(await screen.findByText('Services answering')).toBeTruthy()
    expect(screen.getAllByText('Dashboard').length).toBeGreaterThan(0)
    expect(screen.getAllByText('111111111111', { exact: false }).length).toBeGreaterThan(0)
    expect(screen.getAllByText('us-east-1', { exact: false }).length).toBeGreaterThan(0)
  })

  it('renders the onboarding form', async () => {
    renderAt(<Onboarding />)
    expect(await screen.findByText('Onboard an account')).toBeTruthy()
    expect(screen.getByText('New account')).toBeTruthy()
    expect(screen.getByText('Provision account')).toBeTruthy()
  })

  it('renders the resource table and its action form', async () => {
    renderAt(<Resources />)
    expect(await screen.findByText('S3 resources')).toBeTruthy()
    expect(screen.getByText('Actions')).toBeTruthy()
    expect(await screen.findByText('aws s3 mb s3://<bucket>')).toBeTruthy()
  })

  it('opens a bucket and lists its objects', async () => {
    renderAt(<Resources />)
    await screen.findByText('S3 resources')
    fireEvent.click(await screen.findByRole('button', { name: 'Open' }))
    expect(await screen.findByText('reports/2026.csv')).toBeTruthy()
  })

  it('lists access keys masked and refuses a third key', async () => {
    renderAt(<Settings />)
    expect(await screen.findByText('laptop-cli')).toBeTruthy()
    expect(screen.getByText('ci-pipeline')).toBeTruthy()
    expect(screen.getAllByText('••••••••••••').length).toBe(2)
    const create = screen.getByRole('button', { name: 'Create access key' })
    expect(create.disabled).toBe(true)
    expect(screen.getByText('(2/2)')).toBeTruthy()
  })

  it('lists resources across every region when the toggle is on', async () => {
    renderAt(<Resources />)
    await screen.findByText('S3 resources')
    expect(screen.queryByText('Region')).toBeNull()
    fireEvent.click(
      await screen.findByRole('checkbox', { name: /View from all regions/i }),
    )
    expect(await screen.findByText('Region')).toBeTruthy()
    expect(screen.getByText(/created by mathewmusango/)).toBeTruthy()
    expect(screen.getByText('us-east-1, us-west-2', { exact: false })).toBeTruthy()
  })

  it('shows the stored account name next to the alias', async () => {
    renderAt(<Accounts />)
    expect(await screen.findByText('Mathew Musango')).toBeTruthy()
    expect(screen.getAllByText('mathewmusango').length).toBeGreaterThan(0)
  })

  it('renders the endpoints without the mode, login or references rows', async () => {
    renderAt(<About />)
    expect(await screen.findByText('https://ministack-control.mus.com')).toBeTruthy()
    expect(screen.getByText('https://ministack.mus.com')).toBeTruthy()
    expect(screen.queryByText('Mode')).toBeNull()
    expect(screen.queryByText('Login')).toBeNull()
    expect(screen.queryByText('References')).toBeNull()
  })
})
