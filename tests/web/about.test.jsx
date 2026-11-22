// About reports the build it is running, not only the emulator behind it.

import { beforeEach, describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import About from '../../web/src/pages/About'
import { installFetch, renderAt } from './fixtures'

beforeEach(installFetch)

describe('about page', () => {
  it('names the product and the version it is running', async () => {
    renderAt(<About />, ['/about'])

    expect(await screen.findByText('About Emuplane')).toBeTruthy()
    expect(screen.getByText('0.7.0')).toBeTruthy()
    expect(screen.queryByText('About MiniStack')).toBeNull()
  })
})
