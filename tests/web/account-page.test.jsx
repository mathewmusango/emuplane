// The account page is filed under Billing and Cost Management, as it is in AWS.

import { beforeEach, describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import Account from '../../web/src/pages/Account'
import { installFetch, renderAt } from './fixtures'

beforeEach(installFetch)

describe('account page', () => {
  it('is Billing and Cost Management > Account, not Settings', async () => {
    renderAt(<Account />, ['/Account'])

    expect(await screen.findByRole('heading', { name: 'Account', level: 1 })).toBeTruthy()
    expect(screen.getAllByText('Billing and Cost Management').length).toBeGreaterThan(0)
    expect(screen.queryByRole('heading', { name: 'Settings', level: 1 })).toBeNull()
  })

  it('keeps About in the sidebar, below the divider', async () => {
    renderAt(<Account />, ['/Account'])

    expect(await screen.findByRole('link', { name: 'About' })).toBeTruthy()
  })
})
