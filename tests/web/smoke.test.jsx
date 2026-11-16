import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { BrowserRouter, useLocation } from 'react-router-dom'
import { MemoryRouter } from 'react-router-dom'
import { SessionProvider } from '../../web/src/context'
import App from '../../web/src/App'
import Dashboard from '../../web/src/pages/Dashboard'
import Resources from '../../web/src/pages/Resources'
import Settings from '../../web/src/pages/Settings'
import About from '../../web/src/pages/About'

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
    expect(screen.getAllByText('Home').length).toBeGreaterThan(0)
    expect(screen.getAllByText('111111111111', { exact: false }).length).toBeGreaterThan(0)
    expect(screen.getAllByText('us-east-1', { exact: false }).length).toBeGreaterThan(0)
  })

  it('says Copied after copying the account ID', async () => {
    Object.assign(navigator, {
      clipboard: { writeText: () => Promise.resolve() },
    })
    renderAt(<App />)
    fireEvent.click(
      await screen.findByRole('button', { name: /mathewmusango \(111111111111\)/ }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Copy account ID' }))
    expect(await screen.findByText('Copied')).toBeTruthy()
  })

  it('opens the account menu and turns multi-session on', async () => {
    localStorage.clear()
    renderAt(<App />)
    fireEvent.click(
      await screen.findByRole('button', { name: /mathewmusango \(111111111111\)/ }),
    )
    const toggle = await screen.findByRole('button', {
      name: 'Turn on multi-session support',
    })
    fireEvent.click(toggle)
    // The label flips only if the remember call resolved and the flag was stored.
    expect(
      await screen.findByRole('button', { name: 'Turn off multi-session support' }),
    ).toBeTruthy()
    expect(
      screen.getByRole('button', { name: 'Add session' }),
    ).toBeTruthy()
    localStorage.clear()
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

  it('stars a service from the services menu', async () => {
    localStorage.clear()
    renderAt(<App />)
    // Open the services grid, then star the first service in All services.
    fireEvent.click(await screen.findByRole('button', { name: 'Services' }))
    const menu = await screen.findByRole('dialog', { name: 'Services' })
    fireEvent.click(within(menu).getByRole('button', { name: 'All services' }))
    const stars = await within(menu).findAllByRole('button', {
      name: /Add .* to favorites/,
    })
    fireEvent.click(stars[0])
    expect(
      await within(menu).findByRole('button', { name: /Remove .* from favorites/ }),
    ).toBeTruthy()
    expect(localStorage.getItem('emuplane:favorites:111111111111')).toBeTruthy()
    localStorage.clear()
  })

  it('updates the real address bar when the picker changes region', async () => {
    // Same journey as below, but through BrowserRouter and window.history, which
    // is what the browser actually does.
    window.history.replaceState({}, '', '/s3/home?region=us-east-1')
    render(
      <BrowserRouter>
        <SessionProvider>
          <App />
        </SessionProvider>
      </BrowserRouter>,
    )
    expect(await screen.findAllByText('General purpose buckets')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /N\. Virginia/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /Oregon/ }))
    await waitFor(() =>
      expect(window.location.pathname + window.location.search).toBe(
        '/s3/home?region=us-west-2',
      ),
    )
  })

  it('follows the region picker into the URL', async () => {
    const Probe = () => {
      const location = useLocation()
      return <div data-testid="location">{location.pathname + location.search}</div>
    }
    renderAt(
      <>
        <App />
        <Probe />
      </>,
      ['/s3/home?region=us-east-1'],
    )
    expect(await screen.findAllByText('General purpose buckets')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /N\. Virginia/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /Oregon/ }))

    await screen.findByText(/region=us-west-2/)
    expect(screen.getByTestId('location').textContent).toBe(
      '/s3/home?region=us-west-2',
    )
  })

  it('renders the bucket table without the API explorer', async () => {
    renderAt(<Resources />)
    expect(await screen.findAllByText('General purpose buckets')).toBeTruthy()
    // The table carries the actions; the API explorer is for services without one.
    expect(screen.queryByText('Actions')).toBeNull()
  })

  it('empties a selected bucket, but only once its name is typed', async () => {
    const deleted = []
    const listing = RESPONSES['/api/s3/objects']
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        if (String(url).split('?')[0] === '/api/exec') {
          deleted.push(JSON.parse(options.body).params.Key)
          // Empty from here on, so the re-listing loop stops after one pass.
          RESPONSES['/api/s3/objects'] = { bucket: 'logs-bucket', objects: [] }
          return {
            ok: true,
            status: 200,
            text: async () => JSON.stringify({ ok: true, status: 200, body: '' }),
          }
        }
        return base(url, options)
      }),
    )
    try {
      renderAt(<Resources />)
      await screen.findAllByText('General purpose buckets')
      // Cloudscape keeps a closed modal in the DOM, so the header action is the
      // first of the two buttons named Empty.
      const empty = screen.getAllByRole('button', { name: 'Empty' })[0]
      expect(empty.disabled).toBe(true)

      fireEvent.click(screen.getAllByRole('radio')[0])
      expect(empty.disabled).toBe(false)
      fireEvent.click(empty)

      const dialog = await screen.findByRole('dialog', { name: 'Empty bucket?' })
      const confirm = within(dialog).getByRole('button', { name: 'Empty' })
      expect(confirm.disabled).toBe(true)
      fireEvent.change(within(dialog).getByRole('textbox'), {
        target: { value: 'logs-bucket' },
      })
      expect(confirm.disabled).toBe(false)
      fireEvent.click(confirm)

      await waitFor(() => expect(deleted).toEqual(['reports/2026.csv']))
      expect(await screen.findByText(/Bucket logs-bucket emptied/)).toBeTruthy()
    } finally {
      RESPONSES['/api/s3/objects'] = listing
      vi.stubGlobal('fetch', base)
    }
  })

  it('creates a bucket from its own page, applying the options chosen', async () => {
    // Pin the region: an earlier test leaves us-west-2 selected for the session.
    sessionStorage.setItem('emuplane:region', 'us-east-1')
    const sent = []
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        if (String(url).split('?')[0] === '/api/s3/buckets') {
          sent.push(JSON.parse(options.body))
          return {
            ok: true,
            status: 200,
            text: async () =>
              JSON.stringify({ ok: true, status: 200, bucket: 'demo-bucket' }),
          }
        }
        return base(url, options)
      }),
    )
    try {
      const Probe = () => {
        const where = useLocation()
        return <div data-testid="location">{where.pathname + where.search}</div>
      }
      renderAt(
        <>
          <App />
          <Probe />
        </>,
        ['/s3/create'],
      )
      expect((await screen.findAllByText('Amazon S3')).length).toBeGreaterThan(0)

      fireEvent.change(screen.getByPlaceholderText('my-bucket'), {
        target: { value: 'demo-bucket' },
      })
      fireEvent.click(screen.getByLabelText(/ACLs enabled/))
      fireEvent.click(screen.getByRole('button', { name: 'Create bucket' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'demo-bucket',
        region: 'us-east-1',
        ownership: 'BucketOwnerPreferred',
        versioning: false,
        object_lock: false,
        encryption: 'AES256',
        block_public_access: {
          BlockPublicAcls: true,
          IgnorePublicAcls: true,
          BlockPublicPolicy: true,
          RestrictPublicBuckets: true,
        },
      })
      // Creating hands back to the buckets list, in the bucket's region.
      await screen.findByText('/s3/home?region=us-east-1')
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('opens a bucket and lists its objects', async () => {
    renderAt(<Resources />)
    await screen.findAllByText('General purpose buckets')
    // The bucket name is the link into the bucket, as in the console.
    fireEvent.click(await screen.findByRole('button', { name: 'logs-bucket' }))
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

  it('lists resources across every enabled region by default', async () => {
    renderAt(<Resources />)
    await screen.findAllByText('General purpose buckets')
    // No switch: the page always reads every region the account enabled, and
    // each row carries the region the bucket lives in.
    expect(await screen.findByText('AWS Region')).toBeTruthy()
    expect(screen.getByText('US East (N. Virginia)')).toBeTruthy()
    expect(screen.getAllByText('us-east-1').length).toBeGreaterThan(0)
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
    expect(await screen.findByRole('link', { name: 'S3' })).toBeTruthy()
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

  it('stores the identity when multi-session is on at sign-in', async () => {
    // This is the path that crashed: the identity store's `remember` used to be
    // shadowed by the "remember this account" checkbox state, so signing in with
    // multi-session on called a boolean.
    localStorage.clear()
    localStorage.setItem('emuplane:multi-session', 'on')
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

    expect(await screen.findByText('Services answering')).toBeTruthy()
    const stored = JSON.parse(localStorage.getItem('emuplane:identities') || '[]')
    expect(stored[0]?.token).toBe('login-token')
    localStorage.clear()
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
