// The account dropdown offers the actions the console has, not AWS's whole menu.

import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import TopBar from '../../web/src/components/TopBar'

const props = {
  me: { user: 'root', account: '123456789012' },
  account: '123456789012',
  accountName: 'acme',
  accountAlias: 'acme',
  regions: ['us-east-1'],
  region: 'us-east-1',
  onRegion: () => {},
  serviceNames: [],
  servicesOpen: false,
  onToggleServices: () => {},
  onPickService: () => {},
  onNavigate: () => {},
  dark: false,
  onToggleTheme: () => {},
}

describe('account menu', () => {
  it('offers the actions the console has, and not the ones it does not', () => {
    render(<TopBar {...props} />)
    fireEvent.click(screen.getByRole('button', { name: /123456789012/ }))

    expect(screen.getByRole('menuitem', { name: 'Account' })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: 'Security credentials' })).toBeTruthy()

    // Both pointed at the About page, which says nothing about quotas or billing.
    expect(screen.queryByRole('menuitem', { name: 'Service quotas' })).toBeNull()
    expect(screen.queryByRole('menuitem', { name: 'Billing and Cost Management' })).toBeNull()
  })
})
