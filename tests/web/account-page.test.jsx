// The account page is filed under Billing and Cost Management, as it is in AWS.

import { beforeEach, describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import Account from '../../web/src/pages/Account'
import { installFetch, renderAt } from './fixtures'

const EXEC = {
  'get-account-information': {
    AccountId: '111111111111',
    AccountName: 'MiniStack Local Account',
    AccountCreatedDate: '2025-01-01T00:00:00Z',
    AccountState: 'ACTIVE',
  },
  'get-contact-information': {
    ContactInformation: {
      FullName: 'MiniStack Local',
      AddressLine1: '1 Localhost Lane',
      City: 'Local',
      PostalCode: '00000',
      CountryCode: 'US',
      PhoneNumber: '+10000000000',
    },
  },
  'list-regions': {
    Regions: [{ RegionName: 'us-east-1', RegionOptStatus: 'ENABLED_BY_DEFAULT' }],
  },
  'get-region-opt-status': {
    RegionName: 'us-east-1',
    RegionOptStatus: 'ENABLED_BY_DEFAULT',
  },
}

beforeEach(() =>
  installFetch({
    '/api/exec': (_url, init) => {
      const { operation } = JSON.parse(init.body)
      return { ok: true, status: 200, body: JSON.stringify(EXEC[operation]) }
    },
  }),
)

describe('account page', () => {
  it('is Billing and Cost Management > Account, not Settings', async () => {
    renderAt(<Account />, ['/Account'])

    expect(await screen.findByRole('heading', { name: 'Account', level: 1 })).toBeTruthy()
    expect(screen.getAllByText('Billing and Cost Management').length).toBeGreaterThan(0)
    expect(screen.queryByRole('heading', { name: 'Settings', level: 1 })).toBeNull()
  })

  it('reads the account the way the emulator answers it', async () => {
    renderAt(<Account />, ['/Account'])

    expect(await screen.findByText('MiniStack Local Account')).toBeTruthy()
    expect(screen.getByText('1 Localhost Lane, Local, 00000, US')).toBeTruthy()
    expect(screen.getByText('ENABLED_BY_DEFAULT')).toBeTruthy()
  })

  it('keeps About in the sidebar, below the divider', async () => {
    renderAt(<Account />, ['/Account'])

    expect(await screen.findByRole('link', { name: 'About' })).toBeTruthy()
  })
})
