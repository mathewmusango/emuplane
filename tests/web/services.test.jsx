// The services menu offers what the console can open, not everything the emulator answers.

import { beforeEach, describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import Services from '../../web/src/pages/Services'
import { installFetch, renderAt } from './fixtures'

beforeEach(installFetch)

describe('services menu', () => {
  it('lists a service the console can open, under its category', async () => {
    renderAt(<Services />, ['/services'])

    expect(await screen.findByRole('link', { name: 'IAM' })).toBeTruthy()
    expect(screen.getByText('Security, Identity & Compliance')).toBeTruthy()
  })

  it('leaves out the services it has no page for', async () => {
    renderAt(<Services />, ['/services'])
    await screen.findByRole('link', { name: 'IAM' })

    // Both are in the emulator's group list: STS has no console action at all and Athena
    // has no catalogue entry, so either would only land the reader back here.
    expect(screen.queryByRole('link', { name: 'STS' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Athena' })).toBeNull()
  })

  it('leaves out a service it has no mark for', async () => {
    renderAt(<Services />, ['/services'])
    await screen.findByRole('link', { name: 'IAM' })

    // The emulator groups `states`, but Step Functions is catalogued as `stepfunctions`,
    // which is the name with a page and an icon.
    expect(screen.queryByRole('link', { name: 'Step Functions' })).toBeNull()
  })
})
