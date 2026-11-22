import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import App from '../../web/src/App'
import Dashboard from '../../web/src/pages/Dashboard'
import SecurityCredentials from '../../web/src/pages/SecurityCredentials'
import About from '../../web/src/pages/About'
import SignIn from '../../web/src/pages/SignIn'
import { RESPONSES, installFetch, renderAt } from './fixtures'

beforeEach(installFetch)

describe('console', () => {
  it('offers the password reset link before a user type is chosen', () => {
    renderAt(<SignIn />, ['/login'])
    const link = screen.getByText('Forgot password?').closest('a')
    expect(link.getAttribute('href')).toBe('/forgot')
  })
  it('renders the dashboard shell with the account and region', async () => {
    renderAt(<App />)
    expect(await screen.findByText('Services answering')).toBeTruthy()
    expect(screen.getAllByText('Home').length).toBeGreaterThan(0)
    expect(screen.getAllByText('111111111111', { exact: false }).length).toBeGreaterThan(0)
    expect(screen.getAllByText('us-east-1', { exact: false }).length).toBeGreaterThan(0)
  })

  it('names the Emuplane version, and which backend answers beside the emulator version', async () => {
    const original = RESPONSES['/api/nodes']
    RESPONSES['/api/nodes'] = [{ health: { reachable: true, version: '1.5.40' } }]
    try {
      renderAt(<App />)

      expect(await screen.findByText('0.7.0')).toBeTruthy()
      // The backend id comes before the emulator's own version, so a second profile
      // reads differently without the panel changing shape.
      expect(await screen.findByText('reachable · ministack 1.5.40')).toBeTruthy()
    } finally {
      RESPONSES['/api/nodes'] = original
    }
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

  it('lists access keys masked and refuses a third key', async () => {
    renderAt(<SecurityCredentials />)
    expect(await screen.findByText('laptop-cli')).toBeTruthy()
    expect(screen.getByText('ci-pipeline')).toBeTruthy()
    expect(screen.getAllByText('••••••••••••').length).toBe(2)
    const create = screen.getByRole('button', { name: 'Create access key' })
    expect(create.disabled).toBe(true)
    expect(screen.getByText('(2/2)')).toBeTruthy()
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
    expect(await screen.findByText('https://emuplane.example.com')).toBeTruthy()
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
