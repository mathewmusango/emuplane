// About reports the build it is running, and the instance behind it, not only the emulator.

import { beforeEach, describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import About from '../../web/src/pages/About'
import { RESPONSES, installFetch, renderAt } from './fixtures'

beforeEach(installFetch)

describe('about page', () => {
  it('names the product and the version it is running', async () => {
    renderAt(<About />, ['/about'])

    expect(await screen.findByText('About Emuplane')).toBeTruthy()
    expect(screen.getByText('0.7.0')).toBeTruthy()
    expect(screen.queryByText('About MiniStack')).toBeNull()
  })

  it('reports the backend, its reachability and the control plane', async () => {
    const original = RESPONSES['/api/nodes']
    RESPONSES['/api/nodes'] = [{ health: { reachable: true, version: '1.5.40' } }]
    try {
      renderAt(<About />, ['/about'])

      // The backend id comes before the emulator's own version, so a second profile
      // reads differently without the panel changing shape.
      expect(await screen.findByText('reachable · ministack 1.5.40')).toBeTruthy()
      expect(screen.getByText('Services answering')).toBeTruthy()
      expect(screen.getByText('Control plane uptime')).toBeTruthy()
      // META.uptime_seconds is 60, and the formatter reads minutes below an hour.
      expect(screen.getByText('1m')).toBeTruthy()
      expect(screen.getByText('Signed in')).toBeTruthy()
    } finally {
      RESPONSES['/api/nodes'] = original
    }
  })
})
