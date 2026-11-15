import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { SessionProvider } from '../src/context'
import App from '../src/App'
import Dashboard from '../src/pages/Dashboard'
import Resources from '../src/pages/Resources'
import Settings from '../src/pages/Settings'
import About from '../src/pages/About'

const META = {
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
  '/api/auth/login': {
    ok: true,
    mfa_required: false,
    user: 'root@example.com',
    account: '111111111111',
    alias: 'mathewmusango',
    role: 'root',
  },
  '/api/auth/mfa': { ok: true },
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

const renderAt = (element, entries = ['/']) =>
  render(
    <MemoryRouter initialEntries={entries}>
      <SessionProvider>{element}</SessionProvider>
    </MemoryRouter>,
  )

describe('console', () => {
  it('renders the dashboard shell with the account and region', async () => {
    renderAt(<App />)
    expect(await screen.findByText('Services answering')).toBeTruthy()
    expect(screen.getAllByText('Console Home').length).toBeGreaterThan(0)
    expect(screen.getAllByText('111111111111', { exact: false }).length).toBeGreaterThan(0)
    expect(screen.getAllByText('us-east-1', { exact: false }).length).toBeGreaterThan(0)
  })

  it('names the account in the bar, and the identity beneath it', async () => {
    renderAt(<App />)
    // Root: the chip carries the account and its ID, the line under it the name.
    const chip = await screen.findByRole('button', { name: /mathewmusango \(111111111111\)/ })
    expect(chip).toBeTruthy()
    expect(screen.getByText('mathewmusango', { selector: '.topbar__chip-label' })).toBeTruthy()

    // IAM: same chip, but the line under it is the username, not the account.
    const original = RESPONSES['/api/meta']
    RESPONSES['/api/meta'] = {
      ...original,
      me: { ...original.me, user: 'test', role: 'iam' },
    }
    try {
      renderAt(<App />)
      expect(
        await screen.findByText('test', { selector: '.topbar__chip-label' }),
      ).toBeTruthy()
    } finally {
      RESPONSES['/api/meta'] = original
    }
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
    expect(await screen.findByText('My account')).toBeTruthy()
    expect(screen.getByDisplayValue('Mathew Musango')).toBeTruthy()
    expect(screen.getByDisplayValue('mathew@example.com')).toBeTruthy()
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
      await screen.findByRole('switch', { name: /View from all regions/i }),
    )
    expect(await screen.findByText('Region')).toBeTruthy()
    expect(screen.getByText(/created by mathewmusango/)).toBeTruthy()
    expect(screen.getByText('us-east-1, us-west-2', { exact: false })).toBeTruthy()
  })

  it('scopes recently visited to the signed-in account', async () => {
    localStorage.clear()
    localStorage.setItem('emuplane:recent', JSON.stringify(['s3']))
    const first = renderAt(<Dashboard />)
    expect(await screen.findByText('Services answering')).toBeTruthy()
    // The widget is always present; with no history it says so.
    expect(
      await screen.findByText(/Nothing yet. Open a service/),
    ).toBeTruthy()
    first.unmount()

    localStorage.setItem('emuplane:recent:111111111111', JSON.stringify(['s3']))
    renderAt(<Dashboard />)
    expect(await screen.findByRole('button', { name: 'S3' })).toBeTruthy()
    localStorage.clear()
  })

  it('renders the endpoints without the mode, login or references rows', async () => {
    renderAt(<About />)
    expect(await screen.findByText('https://ministack-control.example.com')).toBeTruthy()
    expect(screen.getByText('https://ministack.example.com')).toBeTruthy()
    expect(screen.queryByText('Mode')).toBeNull()
    expect(screen.queryByText('Login')).toBeNull()
    expect(screen.queryByText('References')).toBeNull()
  })

  it('signs a root user in through the login page', async () => {
    renderAt(<App />, ['/login'])
    expect(await screen.findByText('Access your account by user type.')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Email address'), {
      target: { value: 'root@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    expect(await screen.findByText('Root user sign in')).toBeTruthy()
    expect(screen.getByText('root@example.com')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Show password' }))
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'correct horse battery' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    // No MFA on this principal: the code screen must not appear.
    expect(await screen.findByText('Services answering')).toBeTruthy()
    expect(screen.queryByText('Additional verification required')).toBeNull()
  })

  it('asks for a code when the server says MFA is required', async () => {
    const original = RESPONSES['/api/auth/login']
    RESPONSES['/api/auth/login'] = { ...original, mfa_required: true }
    try {
      renderAt(<App />, ['/login'])
      expect(await screen.findByText('Access your account by user type.')).toBeTruthy()

      fireEvent.change(screen.getByLabelText('Email address'), {
        target: { value: 'root@example.com' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Next' }))
      await screen.findByText('Root user sign in')
      fireEvent.change(screen.getByLabelText('Password'), {
        target: { value: 'correct horse battery' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

      expect(await screen.findByText('Additional verification required')).toBeTruthy()

      fireEvent.change(screen.getByLabelText('MFA code'), { target: { value: '12' } })
      fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
      expect(
        await screen.findByText('Enter the 6-digit code from your MFA device.'),
      ).toBeTruthy()

      fireEvent.change(screen.getByLabelText('MFA code'), { target: { value: '123456' } })
      fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

      expect(await screen.findByText('Services answering')).toBeTruthy()
    } finally {
      RESPONSES['/api/auth/login'] = original
    }
  })

  it('checks the account reference before asking for IAM credentials', async () => {
    localStorage.removeItem('emuplane:signin-account')
    renderAt(<App />, ['/login'])

    fireEvent.click(await screen.findByRole('radio', { name: /IAM user/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Enter the account ID or alias.')).toBeTruthy()

    const alias = '111'
    fireEvent.change(screen.getByLabelText('Account ID (12 digits) or account alias'), {
      target: { value: alias },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('An account ID is exactly 12 digits.')).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Account ID (12 digits) or account alias'), {
      target: { value: '111111111111' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    expect(await screen.findByText('IAM user sign in')).toBeTruthy()
    expect(screen.getByText('Remember this account')).toBeTruthy()
    expect(screen.getByLabelText('IAM username')).toBeTruthy()
    expect(
      screen.getByRole('button', { name: 'Sign in using root user email' }),
    ).toBeTruthy()
  })
})
