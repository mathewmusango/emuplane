// A sign-in link names the account, so the IAM form opens ready to take a username.

import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import SignIn from '../../web/src/pages/SignIn'
import { renderAt } from './fixtures'

describe('sign-in link', () => {
  it('opens the IAM form with the linked account filled in', async () => {
    renderAt(<SignIn />, ['/login?account=iamuicheck'])

    expect(await screen.findByText('IAM user sign in')).toBeTruthy()
    expect(screen.getByLabelText(/Account ID or alias/).value).toBe('iamuicheck')
  })

  it('opens the account chooser without an account link', async () => {
    renderAt(<SignIn />, ['/login'])

    expect(await screen.findByText('Sign In')).toBeTruthy()
    expect(screen.queryByText('IAM user sign in')).toBeNull()
  })
})
