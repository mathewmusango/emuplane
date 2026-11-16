// The S3 page: the bucket table, its actions, and the create page.
//
// The region is the console's own — it comes from the bar's picker — so these
// tests drive it there rather than through a form control, and they pin the
// Account Regional namespace suffix following that selection.

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter, useLocation } from 'react-router-dom'
import { SessionProvider } from '../../web/src/context'
import App from '../../web/src/App'
import Resources from '../../web/src/pages/Resources'
import AccessPoints from '../../web/src/pages/AccessPoints'
import { RESPONSES, installFetch, renderAt } from './fixtures'

const pinRegion = (region) => sessionStorage.setItem('emuplane:region', region)

// A fetch stub that records the one request under test and answers the rest from
// the shared fixtures. A GET carries no body, so only a request with one is
// recorded — the same helper then serves a listing.
const stubOnce = (path, answer, record) => {
  const base = globalThis.fetch
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url, options = {}) => {
      if (String(url).split('?')[0] === path) {
        if (options.body) record.push(JSON.parse(options.body))
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

  it('opens a bucket on its own page, with its objects', async () => {
    pinRegion('us-east-1')
    renderAt(<App />, ['/s3/home?region=us-east-1'])
    expect(await screen.findAllByText('General purpose buckets')).toBeTruthy()

    // The bucket name is the link into the bucket's page, as in the console.
    fireEvent.click(await screen.findByRole('button', { name: 'logs-bucket' }))
    expect(await screen.findByText('reports/2026.csv')).toBeTruthy()
    expect(screen.getByRole('tab', { name: /Objects/ })).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'Properties' })).toBeTruthy()
    // No inline panel on the list page any more.
    expect(screen.queryByText('Bucket objects')).toBeNull()
  })

  it("reads an object listing in the bucket's own region", async () => {
    // The row says where the bucket lives; the listing must be signed for that
    // region, not the page's — otherwise the emulator answers 301.
    pinRegion('us-east-1')
    const browse = RESPONSES['/api/browse']
    const urls = []
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        urls.push(String(url))
        return base(url, options)
      }),
    )
    RESPONSES['/api/browse'] = {
      ...browse,
      resources: [
        ...browse.resources,
        { name: 'west-bucket', kind: 'bucket', region: 'us-west-2', detail: {} },
      ],
    }
    try {
      renderAt(<App />, ['/s3/home?region=us-east-1'])
      await screen.findAllByText('General purpose buckets')
      fireEvent.click(await screen.findByRole('button', { name: 'west-bucket' }))

      await waitFor(() =>
        expect(urls.some((url) => url.includes('/api/s3/objects'))).toBe(true),
      )
      const listing = urls.find((url) => url.includes('/api/s3/objects'))
      expect(listing).toContain('region=us-west-2')
      expect(listing).toContain('bucket=west-bucket')
    } finally {
      RESPONSES['/api/browse'] = browse
      vi.stubGlobal('fetch', base)
    }
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

  it('keeps the supported S3 tabs as children of S3', async () => {
    pinRegion('us-east-1')
    renderAt(<App />, ['/s3/home?region=us-east-1'])
    expect(await screen.findAllByText('General purpose buckets')).toBeTruthy()

    // Only the tabs this emulator backs are here at all: S3 Tables and S3 Files.
    expect(screen.queryByRole('link', { name: 'Directory buckets' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Vector buckets' })).toBeNull()

    // The nav's other tabs are S3 pages, not services of their own.
    for (const [tab, heading] of [
      ['File systems', 'File systems'],
      ['Table buckets', 'Table buckets'],
    ]) {
      fireEvent.click(screen.getByRole('link', { name: tab }))
      expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeTruthy()
      expect(screen.getAllByText('Amazon S3').length).toBeGreaterThan(0)
    }
  })

  it('lists S3 table buckets from the S3 Tables API', async () => {
    pinRegion('us-east-1')
    renderAt(<App />, ['/s3/table-buckets?region=us-east-1'])
    expect(await screen.findByText('analytics-tables')).toBeTruthy()
    expect(screen.getAllByText('Amazon S3').length).toBeGreaterThan(0)
  })

  it('lists file systems from the S3 Files API', async () => {
    pinRegion('us-east-1')
    renderAt(<App />, ['/s3/files?region=us-east-1'])
    expect((await screen.findAllByText('fs-0123456789abcdef')).length).toBeGreaterThan(0)
    expect(screen.getByText('available')).toBeTruthy()
    expect(screen.getByText('logs-bucket')).toBeTruthy()
  })

  it('sends S3 Files and S3 Tables to their S3 pages, not to a service of their own', async () => {
    pinRegion('us-east-1')
    const Probe = () => {
      const where = useLocation()
      return <div data-testid="location">{where.pathname}</div>
    }

    // The name alone resolves to S3's own page.
    for (const [from, to] of [
      ['/s3tables/home', '/s3/table-buckets'],
      ['/s3files/home', '/s3/files'],
    ]) {
      const view = renderAt(
        <>
          <App />
          <Probe />
        </>,
        [from],
      )
      await waitFor(() =>
        expect(screen.getByTestId('location').textContent).toBe(to),
      )
      view.unmount()
    }
  })

  it('sends a service the console does not serve back to the services page', async () => {
    // A name no service answers for: the catch-all route must not render a page.
    const Probe = () => {
      const where = useLocation()
      return <div data-testid="location">{where.pathname}</div>
    }
    renderAt(
      <>
        <App />
        <Probe />
      </>,
      ['/banana/home?region=us-east-1'],
    )
    await waitFor(() =>
      expect(screen.getByTestId('location').textContent).toBe('/services'),
    )
  })

  it("copies the chosen bucket's settings into the form", async () => {
    pinRegion('us-east-1')
    const user = userEvent.setup()
    const sent = []
    const base = stubOnce(
      '/api/s3/buckets',
      { ok: true, status: 200, bucket: 'copied-bucket' },
      sent,
    )
    try {
      renderAt(<App />, ['/s3/create'])
      await screen.findByText('Copy settings from an existing bucket - optional')

      // The trigger's accessible name comes from the field label, so find it by
      // the placeholder it shows.
      const trigger = screen
        .getAllByRole('button')
        .find((button) => button.textContent.trim() === 'Choose bucket')
      await user.click(trigger)
      await user.click(await screen.findByRole('option', { name: /logs-bucket/ }))

      // The form now reads like the source bucket.
      expect((await screen.findByLabelText(/ACLs enabled/)).checked).toBe(true)
      expect(screen.getByDisplayValue('team')).toBeTruthy()
      expect(screen.getByDisplayValue('platform')).toBeTruthy()

      await user.type(screen.getByPlaceholderText('my-bucket'), 'copied-bucket')
      await user.click(screen.getByRole('button', { name: 'Create bucket' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'copied-bucket',
        ownership: 'BucketOwnerPreferred',
        versioning: true,
        encryption: 'aws:kms',
        bucket_key: true,
        object_lock: false,
        tags: [{ Key: 'team', Value: 'platform' }],
        block_public_access: {
          BlockPublicAcls: false,
          IgnorePublicAcls: true,
          BlockPublicPolicy: true,
          RestrictPublicBuckets: true,
        },
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('offers the account\u2019s buckets for copying their settings', async () => {
    pinRegion('us-east-1')
    renderAt(<App />, ['/s3/create'])
    // The control is there and reads the account's buckets; the copy itself is
    // covered by control/buckets.py's round trip (tests/s3) and on the live
    // instance, because Cloudscape's dropdown does not open under jsdom.
    expect(
      await screen.findByText('Copy settings from an existing bucket - optional'),
    ).toBeTruthy()
    expect(
      screen.getAllByRole('button').some((b) => b.textContent.trim() === 'Choose bucket'),
    ).toBe(true)
  })

  it('has no bucket-type choice, because there is only one type', async () => {
    pinRegion('us-east-1')
    renderAt(<App />, ['/s3/create'])
    await screen.findByText('General configuration')
    expect(screen.queryByText('Bucket type')).toBeNull()
    expect(screen.queryByText('Directory')).toBeNull()
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

  it('empties a selected bucket with one batch call, once its name is typed', async () => {
    const sent = []
    const base = stubOnce('/api/s3/empty', { ok: true, status: 200, removed: 1 }, sent)
    try {
      renderAt(<Resources />)
      await screen.findAllByText('General purpose buckets')
      const empty = screen.getAllByRole('button', { name: 'Empty' })[0]
      expect(empty.disabled).toBe(true)

      fireEvent.click(screen.getAllByRole('radio')[0])
      fireEvent.click(empty)

      const dialog = await screen.findByRole('dialog', { name: 'Empty bucket?' })
      const confirm = within(dialog).getByRole('button', { name: 'Empty' })
      expect(confirm.disabled).toBe(true)
      fireEvent.change(within(dialog).getByRole('textbox'), {
        target: { value: 'logs-bucket' },
      })
      fireEvent.click(confirm)

      // DeleteObjects through the control, not one call per key.
      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        region: 'us-east-1',
      })
      expect(await screen.findByText(/Bucket logs-bucket emptied \(1 objects deleted\)/)).toBeTruthy()
    } finally {
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

  // A stub for one path, with the answer the page should see.
  const stubPath = (path, answer) => {
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        if (String(url).split('?')[0] === path) {
          return { ok: true, status: 200, text: async () => JSON.stringify(answer) }
        }
        return base(url, options)
      }),
    )
    return base
  }

  const openBucket = async () => {
    renderAt(<App />, ['/s3/home?region=us-east-1'])
    await screen.findAllByText('General purpose buckets')
    fireEvent.click(await screen.findByRole('button', { name: 'logs-bucket' }))
    await screen.findByText('reports/2026.csv')
  }

  it('opens an object and shows its text', async () => {
    pinRegion('us-east-1')
    await openBucket()
    fireEvent.click(screen.getByRole('button', { name: 'reports/2026.csv' }))
    const dialog = await screen.findByRole('dialog', { name: 'reports/2026.csv' })
    expect(within(dialog).getByText(/2026-01-01,10/)).toBeTruthy()
  })

  it('deletes one object from its view, after confirming', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/exec', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('button', { name: 'reports/2026.csv' }))

      const view = await screen.findByRole('dialog', { name: 'reports/2026.csv' })
      fireEvent.click(within(view).getByRole('button', { name: 'Delete' }))

      const confirm = await screen.findByRole('dialog', { name: 'Delete object' })
      fireEvent.click(within(confirm).getByRole('button', { name: 'Delete' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        service: 's3',
        operation: 'delete-object',
        region: 'us-east-1',
        params: { Bucket: 'logs-bucket', Key: 'reports/2026.csv' },
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('offers a non-text object as a download instead of showing bytes', async () => {
    pinRegion('us-east-1')
    const base = stubPath('/api/s3/object', {
      ok: true,
      key: 'reports/2026.csv',
      body: null,
      binary: true,
      size: 2048,
      content_type: 'image/png',
    })
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('button', { name: 'reports/2026.csv' }))
      expect(await screen.findByText('This object is not text')).toBeTruthy()
      const link = screen.getByRole('link', { name: 'Download' })
      expect(link.getAttribute('href')).toContain('/api/s3/object-download?')
      expect(link.getAttribute('href')).toContain('key=reports%2F2026.csv')
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('uploads a file from the filesystem with its own type', async () => {
    pinRegion('us-east-1')
    const seen = []
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        if (String(url).split('?')[0] === '/api/s3/object-upload') {
          seen.push({
            url: String(url),
            body: options.body,
            type: options.headers?.['Content-Type'],
          })
          return {
            ok: true,
            status: 200,
            text: async () => JSON.stringify({ ok: true, key: 'notes.txt' }),
          }
        }
        return base(url, options)
      }),
    )
    try {
      await openBucket()
      // The header action and the modal's own button share a name; the closed
      // modal stays in the DOM, so the first is the page's.
      fireEvent.click(screen.getAllByRole('button', { name: 'Upload' })[0])

      const file = new File(['hello from disk\n'], 'notes.txt', { type: 'text/plain' })
      const input = document.querySelector('input[type="file"]')
      Object.defineProperty(input, 'files', { value: [file], configurable: true })
      fireEvent.change(input)

      // The destination key follows the file name until it is typed over.
      await waitFor(() =>
        expect(screen.getByDisplayValue('notes.txt')).toBeTruthy(),
      )
      const dialog = await screen.findByRole('dialog', { name: 'Upload object' })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Upload' }))

      await waitFor(() => expect(seen.length).toBe(1))
      expect(seen[0].body).toBe(file)
      expect(seen[0].type).toBe('text/plain')
      expect(seen[0].url).toContain('key=notes.txt')
      expect(seen[0].url).toContain('bucket=logs-bucket')
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('still uploads typed contents when no file is chosen', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/object', { ok: true, status: 200, key: 'notes.txt' }, sent)
    try {
      await openBucket()
      // The header action and the modal's own button share a name; the closed
      // modal stays in the DOM, so the first is the page's.
      fireEvent.click(screen.getAllByRole('button', { name: 'Upload' })[0])
      const dialog = await screen.findByRole('dialog', { name: 'Upload object' })

      fireEvent.change(within(dialog).getByPlaceholderText('reports/2026.csv'), {
        target: { value: 'notes/typed.txt' },
      })
      fireEvent.change(within(dialog).getByPlaceholderText('contents'), {
        target: { value: 'typed into the page' },
      })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Upload' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        key: 'notes/typed.txt',
        body: 'typed into the page',
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('lists the access points S3 Control reports, in the console columns', async () => {
    pinRegion('us-east-1')
    renderAt(<App />, ['/s3/access-points?region=us-east-1'])

    expect(
      await screen.findByText('Access Points for general purpose buckets (1)'),
    ).toBeTruthy()
    expect(screen.getByText('reports-point')).toBeTruthy()
    // Data source type and id, the alias, and the network origin.
    expect(screen.getByText('Bucket')).toBeTruthy()
    expect(screen.getByText('logs-bucket')).toBeTruthy()
    expect(screen.getByText('reports-point-4ud6rlwts3alias')).toBeTruthy()
    expect(screen.getByText('Internet')).toBeTruthy()
  })

  it('offers only the access point kinds this instance backs', async () => {
    pinRegion('us-east-1')
    renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
    await screen.findByText('reports-point')

    for (const tab of ['General purpose buckets', 'Multi-Region', 'Object Lambda']) {
      expect(screen.getByRole('tab', { name: tab })).toBeTruthy()
    }
    // Directory buckets have no backend here, so they are not a tab at all.
    expect(screen.queryByText('Directory buckets')).toBeNull()
  })

  it('names the region when there are no access points, and offers to create one', async () => {
    pinRegion('us-east-1')
    const base = stubOnce(
      '/api/s3/access-points',
      { ok: true, status: 200, section: 'general', access_points: [] },
      [],
    )
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      expect(
        await screen.findByText(
          "You don't have any access points in the US East (N. Virginia) us-east-1 Region",
        ),
      ).toBeTruthy()
      expect(
        screen.getAllByRole('button', { name: 'Create access point' }).length,
      ).toBeGreaterThan(0)
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('creates an access point from its own page, applying the form', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce(
      '/api/s3/access-points',
      { ok: true, status: 200, name: 'reports-point', created: true },
      sent,
    )
    try {
      renderAt(<App />, ['/s3/access-points/create?region=us-east-1'])
      await screen.findByText('Block Public Access settings for this access point')

      fireEvent.change(screen.getByPlaceholderText('my-access-point'), {
        target: { value: 'reports-point' },
      })

      // Cloudscape's Select does not open under fireEvent; user-event does.
      const user = userEvent.setup()
      const trigger = (await screen.findAllByRole('button')).find(
        (button) => button.textContent.trim() === 'Choose bucket',
      )
      await user.click(trigger)
      await user.click(await screen.findByRole('option', { name: /logs-bucket/ }))

      fireEvent.click(screen.getByRole('button', { name: 'Create access point' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        region: 'us-east-1',
        name: 'reports-point',
        bucket: 'logs-bucket',
        vpc_id: '',
        block_public_access: {
          BlockPublicAcls: true,
          IgnorePublicAcls: true,
          BlockPublicPolicy: true,
          RestrictPublicBuckets: true,
        },
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('deletes a selected access point after confirming', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce(
      '/api/s3/access-point-delete',
      { ok: true, status: 204, name: 'reports-point' },
      sent,
    )
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')

      const remove = screen.getAllByRole('button', { name: 'Delete' })[0]
      expect(remove.disabled).toBe(true)
      fireEvent.click(screen.getAllByRole('radio')[0])
      fireEvent.click(remove)

      const dialog = await screen.findByRole('dialog', { name: 'Delete access point' })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        region: 'us-east-1',
        name: 'reports-point',
      })
      expect(await screen.findByText('Deleted access point reports-point')).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('edits the access point policy in a modal', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce(
      '/api/s3/access-point-policy-edit',
      { ok: true, status: 200, name: 'reports-point', policy: null },
      sent,
    )
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')
      fireEvent.click(screen.getAllByRole('radio')[0])
      fireEvent.click(screen.getByRole('button', { name: 'Edit policy' }))

      const dialog = await screen.findByRole('dialog', { name: /Edit policy/ })
      const editor = within(dialog).getByRole('textbox')
      const document = '{"Statement":[{"Effect":"Allow"}]}'
      fireEvent.change(editor, { target: { value: document } })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        region: 'us-east-1',
        name: 'reports-point',
        policy: document,
      })
      expect(await screen.findByText('Access point policy saved')).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('reads the Multi-Region section from its own region', async () => {
    pinRegion('us-east-1')
    renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
    await screen.findByText('reports-point')

    fireEvent.click(screen.getByRole('tab', { name: 'Multi-Region' }))
    expect(await screen.findByText('world-point')).toBeTruthy()
    expect(screen.getByText('logs-bucket · us-east-1, west-bucket · us-west-2')).toBeTruthy()
    // Creation is not on this page yet, and the tab says so rather than
    // offering a button that cannot finish.
    expect(screen.queryByRole('button', { name: 'Create access point' })).toBeNull()
  })

  it('links Access Points from the S3 navigation', async () => {
    pinRegion('us-east-1')
    renderAt(<App />, ['/s3/home?region=us-east-1'])
    expect(await screen.findAllByText('General purpose buckets')).toBeTruthy()
    expect(screen.getByText('Access management and security')).toBeTruthy()
    const link = screen.getByRole('link', { name: 'Access Points' })
    expect(link.getAttribute('href')).toBe('/s3/access-points')
  })
})
