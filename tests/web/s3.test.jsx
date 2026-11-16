// The S3 page: the bucket table, its actions, and the create page.
//
// The region is the console's own — it comes from the bar's picker — so these
// tests drive it there rather than through a form control, and they pin the
// Account Regional namespace suffix following that selection.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { BrowserRouter, useLocation } from 'react-router-dom'
import { SessionProvider } from '../../web/src/context'
import App from '../../web/src/App'
import Resources from '../../web/src/pages/Resources'
import { RESPONSES, installFetch, renderAt } from './fixtures'

const pinRegion = (region) => sessionStorage.setItem('emuplane:region', region)

// A fetch stub that records the one request under test and answers the rest from
// the shared fixtures.
const stubOnce = (path, answer, record) => {
  const base = globalThis.fetch
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, options = {}) => {
      if (String(url).split('?')[0] === path) {
        record.push(JSON.parse(options.body))
        return { ok: true, status: 200, text: async () => JSON.stringify(answer) }
      }
      return base(url, options)
    }),
  )
  return base
}

describe('s3', () => {
  beforeEach(installFetch)

  it('renders the bucket table without the API explorer', async () => {
    renderAt(<Resources />)
    expect(await screen.findAllByText('General purpose buckets')).toBeTruthy()
    // The table carries the actions; the API explorer is for services without one.
    expect(screen.queryByText('Actions')).toBeNull()
  })

  it('lists buckets across every enabled region, each with its own region', async () => {
    renderAt(<Resources />)
    await screen.findAllByText('General purpose buckets')
    expect(await screen.findByText('AWS Region')).toBeTruthy()
    expect(screen.getByText('US East (N. Virginia)')).toBeTruthy()
    expect(screen.getAllByText('us-east-1').length).toBeGreaterThan(0)
  })

  it('opens a bucket and lists its objects', async () => {
    renderAt(<Resources />)
    await screen.findAllByText('General purpose buckets')
    // The bucket name is the link into the bucket, as in the console.
    fireEvent.click(await screen.findByRole('button', { name: 'logs-bucket' }))
    expect(await screen.findByText('reports/2026.csv')).toBeTruthy()
  })

  it('updates the real address bar when the picker changes region', async () => {
    pinRegion('us-east-1')
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
    pinRegion('us-east-1')
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

  it('creates a bucket from its own page, applying the options chosen', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce(
      '/api/s3/buckets',
      { ok: true, status: 200, bucket: 'demo-bucket' },
      sent,
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
        namespace: 'global',
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
      expect(await screen.findByText(/Bucket demo-bucket created/)).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('takes the region from the top bar, not the form, and follows it into the suffix', async () => {
    pinRegion('us-east-1')
    renderAt(<App />, ['/s3/create'])
    // The bar owns the region; the form must not offer a second control.
    expect(screen.queryByText('AWS Region')).toBeNull()
    expect(screen.getByText('US East (N. Virginia)')).toBeTruthy()

    fireEvent.click(await screen.findByLabelText(/Account Regional namespace/))
    expect(screen.getByText('.111111111111-us-east-1-an')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /N\. Virginia/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /Oregon/ }))
    expect(await screen.findByText('.111111111111-us-west-2-an')).toBeTruthy()
  })

  it('posts the Account Regional namespace as the name typed, leaving the suffix to the server', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce(
      '/api/s3/buckets',
      { ok: true, status: 200, bucket: 'demo.111111111111-us-east-1-an' },
      sent,
    )
    try {
      renderAt(<App />, ['/s3/create'])
      fireEvent.click(await screen.findByLabelText(/Account Regional namespace/))
      fireEvent.change(screen.getByPlaceholderText('my-bucket'), {
        target: { value: 'demo' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Create bucket' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'demo',
        namespace: 'regional',
        region: 'us-east-1',
      })
      // The name that lands is the one the server composed.
      expect(
        await screen.findByText(/Bucket demo\.111111111111-us-east-1-an created/),
      ).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('sends a service the console does not serve back to the services page', async () => {
    // `/s3files/home` and `/s3tables/home` answer `unknown service` upstream; the
    // catch-all route must not render a page for them.
    const Probe = () => {
      const where = useLocation()
      return <div data-testid="location">{where.pathname}</div>
    }
    renderAt(
      <>
        <App />
        <Probe />
      </>,
      ['/s3files/home?region=us-east-1'],
    )
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toBe('/services'),
    )
  })

  it('opens the create page from the table', async () => {
    pinRegion('us-east-1')
    renderAt(<App />, ['/s3/home?region=us-east-1'])
    expect(await screen.findAllByText('General purpose buckets')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Create bucket' }))
    expect(
      await screen.findByText('Block Public Access settings for this bucket'),
    ).toBeTruthy()
  })

  it('empties a selected bucket, but only once its name is typed', async () => {
    const deleted = []
    const listing = RESPONSES['/api/s3/objects']
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        if (String(url).split('?')[0] === '/api/exec') {
          deleted.push(JSON.parse(options.body))
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

      await waitFor(() => expect(deleted.length).toBe(1))
      expect(deleted[0]).toMatchObject({
        service: 's3',
        operation: 'delete-object',
        region: 'us-east-1',
        params: { Bucket: 'logs-bucket', Key: 'reports/2026.csv' },
      })
      expect(await screen.findByText(/Bucket logs-bucket emptied/)).toBeTruthy()
    } finally {
      RESPONSES['/api/s3/objects'] = listing
      vi.stubGlobal('fetch', base)
    }
  })

  it('deletes a selected bucket, but only once its name is typed', async () => {
    const sent = []
    const base = stubOnce(
      '/api/exec',
      { ok: true, status: 200, body: '' },
      sent,
    )
    try {
      renderAt(<Resources />)
      await screen.findAllByText('General purpose buckets')
      const remove = screen.getAllByRole('button', { name: 'Delete' })[0]
      expect(remove.disabled).toBe(true)

      fireEvent.click(screen.getAllByRole('radio')[0])
      fireEvent.click(remove)

      const dialog = await screen.findByRole('dialog', { name: 'Delete bucket?' })
      const confirm = within(dialog).getByRole('button', { name: 'Delete' })
      expect(confirm.disabled).toBe(true)
      fireEvent.change(within(dialog).getByRole('textbox'), {
        target: { value: 'logs-bucket' },
      })
      expect(confirm.disabled).toBe(false)
      fireEvent.click(confirm)

      // The action follows the row's region, not the page's.
      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        service: 's3',
        operation: 'delete-bucket',
        region: 'us-east-1',
        params: { Bucket: 'logs-bucket' },
      })
      expect(await screen.findByText(/Bucket logs-bucket deleted/)).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })
})
