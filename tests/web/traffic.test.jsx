// The request inspector lists what the gateway saw, and keeps every credential value out of it.

import { beforeEach, describe, expect, it } from 'vitest'
import userEvent from '@testing-library/user-event'
import { screen, waitFor } from '@testing-library/react'
import App from '../../web/src/App'
import Traffic from '../../web/src/pages/Traffic'
import { RESPONSES, installFetch, renderAt } from './fixtures'

export const TRAFFIC = {
  latest: 2,
  capacity: 500,
  buffered: 2,
  entries: [
    {
      id: 2,
      time: '2026-11-27T19:00:02.000Z',
      method: 'PUT',
      path: '/demo-bucket/key.txt',
      query: [],
      bucket: 'demo-bucket',
      key: 'key.txt',
      service: 's3',
      operation: 'PutObject',
      account: '111111111111',
      region: 'us-east-1',
      status: 200,
      duration_ms: 12.5,
      request_bytes: 1024,
      response_bytes: 0,
      headers: ['authorization', 'host', 'x-amz-date'],
      credentials: ['SigV4 (redacted)'],
      request_id: 'req-2',
      signed: true,
    },
    {
      id: 1,
      time: '2026-11-27T19:00:01.000Z',
      method: 'GET',
      path: '/demo-bucket',
      query: ['list-type', 'x-id'],
      bucket: 'demo-bucket',
      key: '',
      service: 's3',
      operation: 'ListObjectsV2',
      account: '111111111111',
      region: 'us-east-1',
      status: 403,
      duration_ms: 4,
      request_bytes: 0,
      response_bytes: 210,
      headers: ['cookie', 'host'],
      credentials: ['Cookie (redacted)'],
      request_id: '',
      signed: false,
    },
  ],
}

beforeEach(installFetch)

describe('traffic page', () => {
  it('lists what the gateway saw and opens a request without a credential value', async () => {
    const original = RESPONSES['/api/traffic']
    RESPONSES['/api/traffic'] = TRAFFIC
    try {
      renderAt(<Traffic />, ['/traffic'])

      expect(await screen.findByText('PutObject')).toBeTruthy()
      expect(screen.getByText('ListObjectsV2')).toBeTruthy()
      expect(screen.getByText('403')).toBeTruthy()
      // The query is shown as names, never as values.
      expect(screen.getByText('?list-type&x-id')).toBeTruthy()

      const user = userEvent.setup()
      await user.click(screen.getAllByText('Details')[0])

      expect(await screen.findByText('SigV4 (redacted)')).toBeTruthy()
      expect(screen.getByText('authorization, host, x-amz-date')).toBeTruthy()
      expect(screen.getByText('1024 bytes')).toBeTruthy()
      expect(
        screen.getByText(/No header or query value is stored/),
      ).toBeTruthy()
      expect(document.body.textContent).not.toContain('AWS4-HMAC-SHA256')
      expect(document.body.textContent).not.toContain('emuplane_session')
    } finally {
      RESPONSES['/api/traffic'] = original
    }
  })

  it('filters by status through the API', async () => {
    const original = RESPONSES['/api/traffic']
    const seen = []
    RESPONSES['/api/traffic'] = (url) => {
      seen.push(url)
      return url.includes('status=5xx')
        ? { ...TRAFFIC, entries: [], buffered: 0 }
        : TRAFFIC
    }
    try {
      renderAt(<Traffic />, ['/traffic'])
      expect(await screen.findByText('PutObject')).toBeTruthy()

      const user = userEvent.setup()
      await user.click(screen.getByText('Any status'))
      await user.click(await screen.findByRole('option', { name: '5xx server error' }))

      expect(
        await screen.findByText('The gateway has not seen a request yet.'),
      ).toBeTruthy()
      expect(seen.some((url) => url.includes('status=5xx'))).toBe(true)
    } finally {
      RESPONSES['/api/traffic'] = original
    }
  })

  it('is offered in the console navigation', async () => {
    renderAt(<App />)
    expect(await screen.findByText('Request inspector')).toBeTruthy()
    await waitFor(() =>
      expect(screen.getByRole('link', { name: 'Request inspector' })).toBeTruthy(),
    )
  })
})
