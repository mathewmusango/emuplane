// The S3 page: the bucket table, its actions, and the create page, with the region driven from the bar's picker.

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

// A fetch stub that records the body-carrying request under test and answers the rest from the fixtures.
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

// Buckets the fixture instance has not got, for the forms that pick from them.
const withBuckets = (extra) => {
  const browse = RESPONSES['/api/browse']
  RESPONSES['/api/browse'] = { ...browse, resources: [...browse.resources, ...extra] }
  return () => {
    RESPONSES['/api/browse'] = browse
  }
}

const WEST_BUCKET = { name: 'west-bucket', kind: 'bucket', region: 'us-west-2', detail: {} }
const EAST_BUCKET = { name: 'east-bucket', kind: 'bucket', region: 'us-east-1', detail: {} }

// The Multi-Region create modal: Cloudscape's Multiselect needs user-event, and its options are in a portal.
const openMultiRegionCreate = async (name, memberLabels) => {
  fireEvent.click(screen.getByRole('button', { name: 'Create Multi-Region access point' }))
  const dialog = await screen.findByRole('dialog', { name: 'Create Multi-Region access point' })
  fireEvent.change(within(dialog).getByPlaceholderText('my-world-point'), {
    target: { value: name },
  })
  const user = userEvent.setup()
  await user.click(within(dialog).getByText('Choose buckets'))
  for (const label of memberLabels) {
    await user.click(await screen.findByRole('option', { name: label }))
  }
  return dialog
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
    // The listing must be signed for the bucket's own region, not the page's, or the emulator answers 301.
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

  it('copies settings from an existing bucket', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        const target = String(url).split('?')[0]
        if (target === '/api/s3/buckets') {
          if (options.body) sent.push(JSON.parse(options.body))
          return {
            ok: true,
            status: 200,
            text: async () => JSON.stringify({ ok: true, bucket: 'copied-bucket' }),
          }
        }
        if (target === '/api/s3/bucket-settings') {
          return {
            ok: true,
            status: 200,
            text: async () =>
              JSON.stringify({
                ok: true,
                bucket: 'logs-bucket',
                settings: RESPONSES['/api/s3/bucket-settings'].settings,
              }),
          }
        }
        return base(url, options)
      }),
    )
    try {
      renderAt(<App />, ['/s3/create'])
      fireEvent.change(await screen.findByPlaceholderText('my-bucket'), {
        target: { value: 'copied-bucket' },
      })

      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: /Choose bucket/ }))
      await user.click(await screen.findByRole('option', { name: /logs-bucket/ }))
      fireEvent.click(screen.getByRole('button', { name: 'Create bucket' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'copied-bucket',
        versioning: true,
        encryption: 'aws:kms',
        tags: [{ Key: 'team', Value: 'platform' }],
      })
      // MFA delete is not exposed on this page until the console carries it again.
      expect(sent[0].mfa_delete).toBeUndefined()
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

      // The trigger's accessible name comes from the field label, so find it by the placeholder it shows.
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
    // Cloudscape's dropdown does not open under jsdom, so only the control's presence is checked here.
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

  it('browses into a folder, walks back by the breadcrumb, and pages a long listing', async () => {
    pinRegion('us-east-1')
    const listed = []
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        if (String(url).split('?')[0] !== '/api/s3/objects') return base(url, options)
        listed.push(String(url))
        const params = new URL(String(url), 'http://console').searchParams
        const prefix = params.get('prefix') || ''
        const token = params.get('continuation_token') || ''
        const answer = (body) => ({
          ok: true,
          status: 200,
          text: async () => JSON.stringify({ prefix, ...body }),
        })
        if (!prefix) {
          return answer({
            objects: [
              { key: 'reports/', size: '', modified: '', storage: '' },
              { key: 'notes.txt', size: '4', modified: '', storage: 'STANDARD' },
            ],
          })
        }
        // A folder with more keys than a page: the token carries the rest.
        return token
          ? answer({ objects: [{ key: `${prefix}second.txt`, size: '1' }] })
          : answer({
              objects: [{ key: `${prefix}first.txt`, size: '1' }],
              truncated: true,
              next_token: 'page-2',
            })
      }),
    )
    try {
      renderAt(<App />, ['/s3/home?region=us-east-1'])
      await screen.findAllByText('General purpose buckets')
      fireEvent.click(await screen.findByRole('button', { name: 'logs-bucket' }))
      await screen.findByText('notes.txt')
      // The way out of a folder is the breadcrumb, not a ".." row above the table.
      expect(screen.queryByRole('link', { name: '..' })).toBeNull()

      fireEvent.click(screen.getByRole('link', { name: 'reports/' }))
      expect(await screen.findByText('reports/first.txt')).toBeTruthy()
      // The folder is in the listing's own request, so a new tab and the back button land in it too.
      expect(listed.some((url) => url.includes('prefix=reports%2F'))).toBe(true)

      fireEvent.click(screen.getByRole('button', { name: 'Load more objects' }))
      expect(await screen.findByText('reports/second.txt')).toBeTruthy()
      expect(screen.queryByRole('button', { name: 'Load more objects' })).toBeNull()
      expect(listed.some((url) => url.includes('continuation_token=page-2'))).toBe(true)

      // Every step of the path is a link back, and the bucket is the way to the root.
      fireEvent.click(screen.getByRole('link', { name: 'logs-bucket' }))
      expect(await screen.findByText('notes.txt')).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('opens an object and shows its text', async () => {
    pinRegion('us-east-1')
    await openBucket()
    fireEvent.click(screen.getByRole('link', { name: 'reports/2026.csv' }))
    const dialog = await screen.findByRole('heading', { name: 'reports/2026.csv' })
    expect(screen.getByText(/2026-01-01,10/)).toBeTruthy()
  })

  it('shows what only a HeadObject knows about an object', async () => {
    pinRegion('us-east-1')
    await openBucket()
    fireEvent.click(screen.getByRole('link', { name: 'reports/2026.csv' }))

    const dialog = await screen.findByRole('heading', { name: 'reports/2026.csv' })
    expect(screen.getByText('d41d8cd98f00b204e9800998ecf8427e')).toBeTruthy()
    expect(screen.getByText('Mon, 16 Nov 2026 13:06:12 GMT')).toBeTruthy()
    expect(screen.getByText('text/csv')).toBeTruthy()
    expect(screen.getByText('24 B')).toBeTruthy()
  })

  it('shows each document on the tab that owns it, and says so when one is unset', async () => {
    pinRegion('us-east-1')
    await openBucket()

    fireEvent.click(screen.getByRole('tab', { name: 'Properties' }))
    expect(await screen.findByText('Server access logging')).toBeTruthy()
    expect(screen.getByText('Event notifications')).toBeTruthy()
    expect(screen.getByText('Static website hosting')).toBeTruthy()
    // Versions is a listing of its own, not a document; this bucket's fixture has none.
    expect(screen.getByText('Versions')).toBeTruthy()
    expect(await screen.findByText('No versions in this folder yet.')).toBeTruthy()
    // ...but a document S3 reports as empty says so instead of showing an element.
    expect(screen.getAllByText('Not configured.').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('tab', { name: 'Permissions' }))
    expect(await screen.findByText('Bucket policy')).toBeTruthy()
    expect(screen.getByText(/<Policy><Statement>/)).toBeTruthy()
    expect(screen.getByText('Access control list (ACL)')).toBeTruthy()
    expect(screen.getByText('Cross-origin resource sharing (CORS)')).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: 'Management' }))
    expect(await screen.findByText('Lifecycle configuration')).toBeTruthy()
    expect(screen.getByText('Replication rules')).toBeTruthy()
  })

  it('writes a configuration document from its editor', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/bucket-document', { ok: true, status: 200 }, sent)
    const cors =
      '<CORSConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">' +
      '<CORSRule><AllowedMethod>GET</AllowedMethod><AllowedOrigin>*</AllowedOrigin></CORSRule>' +
      '</CORSConfiguration>'
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Permissions' }))
      fireEvent.click(await screen.findByRole('button', { name: 'Edit cors' }))

      const dialog = await screen.findByRole('dialog', { name: /Edit Cross-origin/ })
      fireEvent.change(within(dialog).getByRole('textbox'), {
        target: { value: cors },
      })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        document: 'cors',
        action: 'save',
        body: cors,
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('removes a configuration document from its editor', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/bucket-document', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Permissions' }))
      fireEvent.click(await screen.findByRole('button', { name: 'Edit policy' }))

      const dialog = await screen.findByRole('dialog', { name: /Edit Bucket policy/ })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Remove document' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        document: 'policy',
        action: 'clear',
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('deletes a configuration document from its card, after a confirmation', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/bucket-document', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Permissions' }))
      fireEvent.click(await screen.findByRole('button', { name: 'Delete policy' }))

      // The card's Delete asks first: it is not the editor with a different footer.
      const dialog = await screen.findByRole('dialog', { name: 'Delete Bucket policy' })
      expect(within(dialog).queryByRole('textbox')).toBeNull()
      fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        document: 'policy',
        action: 'clear',
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it("lists only this bucket's file systems", async () => {
    pinRegion('us-east-1')
    const base = stubOnce(
      '/api/s3/file-systems',
      {
        ok: true,
        status: 200,
        items: [
          { fileSystemId: 'fs-this-bucket', bucket: 'logs-bucket', status: 'available' },
          { fileSystemId: 'fs-other-bucket', bucket: 'west-bucket', status: 'available' },
        ],
      },
      [],
    )
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'File systems' }))
      expect(await screen.findByText('fs-this-bucket')).toBeTruthy()
      expect(screen.queryByText('fs-other-bucket')).toBeNull()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it("lists only this bucket's access points", async () => {
    pinRegion('us-east-1')
    const point = (name, bucket) => ({
      name,
      alias: `${name}-alias`,
      arn: `arn:aws:s3:us-east-1:111111111111:accesspoint/${name}`,
      network_origin: 'Internet',
      vpc_id: '',
      created: '2026-11-16T09:00:00Z',
      status: 'READY',
      bucket,
      buckets: [],
      region: 'us-east-1',
    })
    const base = stubOnce(
      '/api/s3/access-points',
      {
        ok: true,
        status: 200,
        section: 'general',
        region: 'us-east-1',
        access_points: [point('this-point', 'logs-bucket'), point('other-point', 'west-bucket')],
      },
      [],
    )
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Access Points' }))
      expect(await screen.findByText('this-point')).toBeTruthy()
      expect(screen.queryByText('other-point')).toBeNull()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('does not let a failed child listing read as nothing here', async () => {
    pinRegion('us-east-1')
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        if (String(url).split('?')[0] === '/api/s3/file-systems') {
          return {
            ok: false,
            status: 503,
            text: async () => JSON.stringify({ error: 'S3 Files is not configured' }),
          }
        }
        return base(url, options)
      }),
    )
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'File systems' }))
      expect(await screen.findByText('S3 Files is not configured')).toBeTruthy()
      // An unread listing is not an empty one.
      expect(screen.queryByText(/don\u2019t have any file systems/)).toBeNull()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it("shows an object's tags, annotations and Object Lock state, each read on its own", async () => {
    pinRegion('us-east-1')
    await openBucket()
    fireEvent.click(screen.getByRole('link', { name: 'reports/2026.csv' }))
    await screen.findByRole('heading', { name: 'reports/2026.csv' })

    fireEvent.click(screen.getByRole('tab', { name: 'Tags' }))
    expect(await screen.findByText('stage')).toBeTruthy()
    expect(screen.getByText('prod')).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: 'Annotations' }))
    fireEvent.click(await screen.findByRole('button', { name: 'note' }))
    // GetObjectAnnotation reads one annotation's own content.
    expect(await screen.findByText('the note')).toBeTruthy()

    fireEvent.click(screen.getByRole('tab', { name: 'Object Lock' }))
    expect(await screen.findByText('This object has no retention set.')).toBeTruthy()
    expect(screen.getByText('This object is not under a legal hold.')).toBeTruthy()
  })

  it('never dresses a failed object read up as an empty state', async () => {
    pinRegion('us-east-1')
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        if (String(url).split('?')[0] === '/api/s3/object-meta') {
          return {
            ok: false,
            status: 503,
            text: async () => JSON.stringify({ error: 'S3 refused the read' }),
          }
        }
        return base(url, options)
      }),
    )
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('link', { name: 'reports/2026.csv' }))
      await screen.findByRole('heading', { name: 'reports/2026.csv' })

      fireEvent.click(screen.getByRole('tab', { name: 'Tags' }))
      expect(await screen.findByText('S3 refused the read')).toBeTruthy()
      expect(screen.queryByText('This object has no tags.')).toBeNull()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('opens a bucket from a link that names no region, by asking where it lives', async () => {
    pinRegion('us-west-2')
    const listed = []
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        if (String(url).split('?')[0] === '/api/s3/objects') listed.push(String(url))
        return base(url, options)
      }),
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
        ['/s3/buckets/logs-bucket'],
      )

      await screen.findByText('reports/2026.csv')
      // HeadBucket said us-east-1, so the list is read there and the URL follows.
      expect(listed[0]).toContain('region=us-east-1')
      await waitFor(() =>
        expect(screen.getByTestId('location').textContent).toBe(
          '/s3/buckets/logs-bucket?region=us-east-1',
        ),
      )
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('says so when the bucket is not there, instead of an empty table', async () => {
    pinRegion('us-east-1')
    const listed = []
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        const path = String(url).split('?')[0]
        if (path === '/api/s3/bucket-head') {
          return {
            ok: true,
            status: 200,
            text: async () =>
              JSON.stringify({
                ok: true,
                exists: false,
                status: 404,
                region: 'us-east-1',
              }),
          }
        }
        if (path === '/api/s3/objects') listed.push(String(url))
        return base(url, options)
      }),
    )
    try {
      renderAt(<App />, ['/s3/buckets/ghost-bucket?region=us-east-1'])
      expect(await screen.findByText('This bucket does not exist')).toBeTruthy()
      // Nothing is read from a bucket that is not there.
      expect(listed).toEqual([])
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('copies an object into a bucket, addressed to the destination', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/object-copy', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('link', { name: 'reports/2026.csv' }))
      await screen.findByRole('heading', { name: 'reports/2026.csv' })
      // The object's page carries Copy; the closed copy modal's button shares the name, so the first is the page's.
      fireEvent.click(screen.getAllByRole('button', { name: 'Copy' })[0])

      const dialog = await screen.findByRole('dialog', { name: 'Copy object' })
      fireEvent.change(within(dialog).getByDisplayValue('reports/2026.csv'), {
        target: { value: 'archive/2026.csv' },
      })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Copy' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        region: 'us-east-1',
        bucket: 'logs-bucket',
        key: 'reports/2026.csv',
        destination: 'logs-bucket',
        destination_key: 'archive/2026.csv',
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('offers only the Actions it can run', async () => {
    pinRegion('us-east-1')
    await openBucket()

    // The first checkbox is the header's select-all; the second is the single object's row.
    fireEvent.click(screen.getAllByRole('checkbox')[1])
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Actions' }))

    const items = await screen.findAllByRole('menuitem')
    expect(items.map((item) => item.textContent.trim())).toEqual([
      'Copy',
      'Move',
      'Edit storage class',
      'Edit server-side encryption',
      'Make public using ACL',
    ])
  })

  it('changes one object storage class in place', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/object-rewrite', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getAllByRole('checkbox')[1])
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: 'Actions' }))
      await user.click(await screen.findByRole('menuitem', { name: 'Edit storage class' }))

      const dialog = await screen.findByRole('dialog', { name: 'Edit storage class' })
      await user.click(within(dialog).getByRole('button', { name: /Storage class/ }))
      await user.click(await screen.findByRole('option', { name: 'Standard-IA' }))
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        key: 'reports/2026.csv',
        storage_class: 'STANDARD_IA',
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('passes on S3\u2019s refusal when the bucket has ACLs disabled', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce(
      '/api/s3/object-acl',
      {
        ok: false,
        error: 'AccessControlListNotSupported: The bucket does not allow ACLs',
      },
      sent,
    )
    try {
      await openBucket()
      fireEvent.click(screen.getAllByRole('checkbox')[1])
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: 'Actions' }))
      await user.click(
        await screen.findByRole('menuitem', { name: 'Make public using ACL' }),
      )

      const dialog = await screen.findByRole('dialog', { name: 'Object ACL' })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))
      // The console repeats S3's sentence rather than paraphrasing it.
      expect(
        await within(dialog).findByText(/AccessControlListNotSupported/),
      ).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('shows the creation date, and suspends versioning rather than disabling it', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/bucket-settings-edit', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Properties' }))

      // The date is ListBuckets' answer, not what navigation happens to carry.
      expect(await screen.findByText('2026-11-16T09:00:00.000Z')).toBeTruthy()
      // MFA delete is not surfaced until the console carries it again.
      expect(screen.queryByText('MFA delete')).toBeNull()

      fireEvent.click(screen.getByRole('button', { name: 'Edit bucket versioning' }))
      // S3 has no "off" after "on": the choices are Enable and Suspend.
      expect(screen.queryByLabelText('Disable')).toBeNull()
      fireEvent.click(screen.getByLabelText('Suspend'))
      fireEvent.click(screen.getByRole('button', { name: 'Save bucket versioning' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        region: 'us-east-1',
        versioning_status: 'Suspended',
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('lists an object’s versions and deletes one of them', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        const path = String(url).split('?')[0]
        const answer = (body) => ({
          ok: true,
          status: 200,
          text: async () => JSON.stringify(body),
        })
        if (path === '/api/s3/object-version-delete') {
          sent.push(JSON.parse(options.body))
          return answer({ ok: true })
        }
        if (path === '/api/s3/versions') {
          // Two pages, because a listing is one page and the rest is asked for.
          const params = new URL(String(url), 'http://console').searchParams
          if (params.get('key_marker')) {
            return answer({
              ok: true,
              bucket: 'logs-bucket',
              versions: [
                {
                  key: 'reports/2026.csv',
                  version_id: 'v1',
                  latest: false,
                  delete_marker: false,
                  size: '12',
                  modified: '2026-11-15T09:00:00Z',
                  storage: 'STANDARD',
                },
              ],
              truncated: false,
            })
          }
          return answer({
            ok: true,
            bucket: 'logs-bucket',
            versions: [
              {
                key: 'reports/2026.csv',
                version_id: 'v2',
                latest: true,
                delete_marker: false,
                size: '24',
                modified: '2026-11-16T13:06:12Z',
                storage: 'STANDARD',
              },
            ],
            truncated: true,
            next_key_marker: 'reports/2026.csv',
            next_version_id_marker: 'v2',
          })
        }
        return base(url, options)
      }),
    )
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Properties' }))

      expect(await screen.findByText('v2')).toBeTruthy()
      // The first page ends there; the older version is behind the listing's own marker.
      expect(screen.queryByText('v1')).toBeNull()
      expect(screen.getByText('Load more versions')).toBeTruthy()
      fireEvent.click(screen.getByRole('button', { name: 'Load more versions' }))
      expect(await screen.findByText('v1')).toBeTruthy()
      expect(screen.queryByRole('button', { name: 'Load more versions' })).toBeNull()
      // One version can be fetched on its own, which is the only way to read an old body.
      expect(
        screen.getByRole('link', {
          name: 'Download version v2 of reports/2026.csv',
        }),
      ).toBeTruthy()

      fireEvent.click(
        screen.getByRole('button', { name: 'Delete version v1 of reports/2026.csv' }),
      )
      const confirm = await screen.findByRole('dialog', { name: 'Delete version' })
      fireEvent.click(within(confirm).getByRole('button', { name: 'Delete' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        region: 'us-east-1',
        bucket: 'logs-bucket',
        key: 'reports/2026.csv',
        version_id: 'v1',
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('lists keys whose versions share the emulator’s null version id', async () => {
    pinRegion('us-east-1')
    const base = globalThis.fetch
    // Everything written before versioning was enabled answers version id `null`, so two keys state the same id.
    const errors = []
    const record = vi.spyOn(console, 'error').mockImplementation((...args) => {
      errors.push(args.join(' '))
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        const path = String(url).split('?')[0]
        if (path === '/api/s3/versions') {
          return {
            ok: true,
            status: 200,
            text: async () =>
              JSON.stringify({
                ok: true,
                bucket: 'logs-bucket',
                versions: [
                  {
                    key: 'reports/2026.csv',
                    version_id: 'null',
                    latest: true,
                    delete_marker: false,
                    size: '24',
                    modified: '2026-11-16T13:06:12Z',
                    storage: 'STANDARD',
                  },
                  {
                    key: 'reports/2025.csv',
                    version_id: 'null',
                    latest: true,
                    delete_marker: false,
                    size: '12',
                    modified: '2026-11-15T09:00:00Z',
                    storage: 'STANDARD',
                  },
                ],
                truncated: false,
              }),
          }
        }
        return base(url, options)
      }),
    )
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Properties' }))

      expect(await screen.findByText('reports/2026.csv')).toBeTruthy()
      expect(screen.getByText('reports/2025.csv')).toBeTruthy()
      // Two rows sharing one React key make the table's reconciliation ambiguous, so React warns.
      expect(errors.filter((line) => /same key/i.test(line))).toEqual([])
    } finally {
      record.mockRestore()
      vi.stubGlobal('fetch', base)
    }
  })

  it('pages an upload list and its parts instead of cutting them short', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        const path = String(url).split('?')[0]
        const answer = (body) => ({
          ok: true,
          status: 200,
          text: async () => JSON.stringify(body),
        })
        if (path === '/api/s3/uploads') {
          const params = new URL(String(url), 'http://console').searchParams
          if (params.get('key_marker')) {
            return answer({
              ok: true,
              bucket: 'logs-bucket',
              uploads: [
                {
                  key: 'other/zeta.bin',
                  upload_id: 'upload-2',
                  initiated: '2026-11-16T11:00:00Z',
                  storage: 'STANDARD',
                },
              ],
              truncated: false,
            })
          }
          return answer({
            ok: true,
            bucket: 'logs-bucket',
            uploads: [
              {
                key: 'big.bin',
                upload_id: 'upload-1',
                initiated: '2026-11-16T10:00:00Z',
                storage: 'STANDARD',
              },
            ],
            truncated: true,
            next_key_marker: 'big.bin',
            next_upload_id_marker: 'upload-1',
          })
        }
        if (path === '/api/s3/upload-parts') {
          const params = new URL(String(url), 'http://console').searchParams
          if (params.get('part_number_marker')) {
            return answer({
              ok: true,
              bucket: 'logs-bucket',
              key: 'big.bin',
              upload_id: 'upload-1',
              parts: [
                {
                  part_number: '2',
                  size: '4194304',
                  etag: '"bbb"',
                  modified: '2026-11-16T10:01:00Z',
                },
              ],
              truncated: false,
            })
          }
          return answer({
            ok: true,
            bucket: 'logs-bucket',
            key: 'big.bin',
            upload_id: 'upload-1',
            parts: [
              {
                part_number: '1',
                size: '5242880',
                etag: '"aaa"',
                modified: '2026-11-16T10:00:30Z',
              },
            ],
            truncated: true,
            next_part_number_marker: '1',
          })
        }
        if (path === '/api/s3/multipart-abort') {
          sent.push(JSON.parse(options.body))
          return answer({ ok: true })
        }
        return base(url, options)
      }),
    )
    try {
      await openBucket()
      expect(await screen.findByText('Incomplete multipart uploads')).toBeTruthy()
      expect(await screen.findByText('upload-1')).toBeTruthy()
      // More uploads than one page: the rest is behind the listing's marker.
      fireEvent.click(screen.getByRole('button', { name: 'Load more uploads' }))
      expect(await screen.findByText('other/zeta.bin')).toBeTruthy()

      fireEvent.click(
        screen.getByRole('button', {
          name: 'Show the parts of the upload of big.bin',
        }),
      )
      const dialog = await screen.findByRole('dialog', { name: 'Incomplete upload' })
      expect(await within(dialog).findByText('5.0 MB')).toBeTruthy()
      // ListParts is paged by part number, not by a token.
      fireEvent.click(within(dialog).getByRole('button', { name: 'Load more parts' }))
      expect(await within(dialog).findByText('4.0 MB')).toBeTruthy()

      fireEvent.click(within(dialog).getByRole('button', { name: 'Abort upload' }))
      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        region: 'us-east-1',
        bucket: 'logs-bucket',
        key: 'big.bin',
        upload_id: 'upload-1',
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('switches Object Ownership, which is what object ACLs depend on', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/bucket-settings-edit', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Permissions' }))

      // The tab states the state S3 answered, and offers the switch that changes it.
      expect(
        await screen.findByText('ACLs enabled - bucket owner preferred'),
      ).toBeTruthy()
      fireEvent.click(screen.getByRole('button', { name: 'Edit object ownership' }))
      fireEvent.click(screen.getByLabelText('ACLs disabled (bucket owner enforced)'))
      fireEvent.click(screen.getByRole('button', { name: 'Save object ownership' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        region: 'us-east-1',
        ownership: 'BucketOwnerEnforced',
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('reads and writes an ACL on one version of an object', async () => {
    pinRegion('us-east-1')
    const sent = []
    const reads = []
    let granted = false
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        const path = String(url).split('?')[0]
        const answer = (body) => ({
          ok: true,
          status: 200,
          text: async () => JSON.stringify(body),
        })
        if (path === '/api/s3/versions') {
          return answer({
            ok: true,
            bucket: 'logs-bucket',
            versions: [
              {
                key: 'reports/2026.csv',
                version_id: 'v2',
                latest: true,
                delete_marker: false,
                size: '24',
                modified: '2026-11-16T13:06:12Z',
                storage: 'STANDARD',
              },
              {
                key: 'reports/2026.csv',
                version_id: 'v1',
                latest: false,
                delete_marker: false,
                size: '12',
                modified: '2026-11-15T09:00:00Z',
                storage: 'STANDARD',
              },
            ],
          })
        }
        if (path !== '/api/s3/object-acl') return base(url, options)
        if (options.method === 'POST') {
          sent.push(JSON.parse(options.body))
          granted = true
          return answer({ ok: true })
        }
        reads.push(String(url))
        return answer({
          ok: true,
          status: 200,
          bucket: 'logs-bucket',
          key: 'reports/2026.csv',
          owner: { id: 'owner-id', display_name: 'owner' },
          grants: [
            {
              type: 'CanonicalUser',
              id: 'owner-id',
              display_name: 'owner',
              uri: '',
              permission: granted ? 'READ_ACP' : 'FULL_CONTROL',
            },
          ],
          public: false,
          acl: '<AccessControlPolicy/>',
        })
      }),
    )
    try {
      await openBucket()
      fireEvent.click(screen.getAllByRole('checkbox')[1])
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: 'Actions' }))
      await user.click(await screen.findByRole('menuitem', { name: 'Make public using ACL' }))

      const dialog = await screen.findByRole('dialog', { name: 'Object ACL' })
      // The older version is offered, because an ACL belongs to a version.
      await user.click(await within(dialog).findByText('Current version'))
      await user.click(await screen.findByRole('option', { name: /v1 ·/ }))

      await waitFor(() =>
        expect(reads.some((url) => url.includes('version_id=v1'))).toBe(true),
      )

      fireEvent.click(within(dialog).getByLabelText('Public read'))
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))
      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        key: 'reports/2026.csv',
        canned_acl: 'public-read',
        version_id: 'v1',
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('reads an object ACL back, before and after a grant is written', async () => {
    pinRegion('us-east-1')
    const sent = []
    let granted = false
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        const path = String(url).split('?')[0]
        if (path !== '/api/s3/object-acl') return base(url, options)
        if (options.method === 'POST') {
          sent.push(JSON.parse(options.body))
          granted = true
          return { ok: true, status: 200, text: async () => JSON.stringify({ ok: true }) }
        }
        const owner = {
          type: 'CanonicalUser',
          id: 'owner-id',
          display_name: 'owner',
          uri: '',
          permission: 'FULL_CONTROL',
        }
        const publicGrant = {
          type: 'Group',
          id: '',
          display_name: '',
          uri: 'http://acs.amazonaws.com/groups/global/AllUsers',
          permission: 'READ',
        }
        return {
          ok: true,
          status: 200,
          text: async () =>
            JSON.stringify({
              ok: true,
              status: 200,
              bucket: 'logs-bucket',
              key: 'reports/2026.csv',
              owner: { id: 'owner-id', display_name: 'owner' },
              grants: granted ? [owner, publicGrant] : [owner],
              public: granted,
              acl: '<AccessControlPolicy/>',
            }),
        }
      }),
    )
    try {
      await openBucket()
      fireEvent.click(screen.getAllByRole('checkbox')[1])
      const user = userEvent.setup()
      await user.click(screen.getByRole('button', { name: 'Actions' }))
      await user.click(await screen.findByRole('menuitem', { name: 'Make public using ACL' }))

      const dialog = await screen.findByRole('dialog', { name: 'Object ACL' })
      // The dialog opens on what S3 holds, which for this object is the owner's grant only.
      expect(await within(dialog).findByText('FULL_CONTROL')).toBeTruthy()
      expect(within(dialog).getByText(/not public/)).toBeTruthy()
      expect(within(dialog).queryByText('READ')).toBeNull()

      fireEvent.click(within(dialog).getByLabelText('Public read'))
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))
      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        key: 'reports/2026.csv',
        canned_acl: 'public-read',
      })
      // The dialog stays open on the answer, so the new grant is visible rather than assumed.
      expect(
        await within(dialog).findByText(/S3 holds public-read on reports\/2026.csv/),
      ).toBeTruthy()
      expect(await within(dialog).findByText('READ')).toBeTruthy()
      expect(
        within(dialog).getByText(/public: a grant names the AllUsers group/),
      ).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('changes the default encryption from the bucket page', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/bucket-settings-edit', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Properties' }))
      fireEvent.click(
        await screen.findByRole('button', { name: 'Edit default encryption' }),
      )
      fireEvent.click(screen.getByLabelText(/Dual-layer/))
      fireEvent.click(screen.getByRole('button', { name: 'Save default encryption' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        encryption: 'aws:kms:dsse',
        bucket_key: true,
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('removes the default encryption, falling back to SSE-S3', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/bucket-settings-edit', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Properties' }))
      fireEvent.click(
        await screen.findByRole('button', { name: 'Edit default encryption' }),
      )
      fireEvent.click(
        screen.getByRole('button', { name: 'Remove default encryption' }),
      )

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({ bucket: 'logs-bucket', remove_encryption: true })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('edits bucket tags and removes them', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/bucket-settings-edit', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Properties' }))
      fireEvent.click(await screen.findByRole('button', { name: 'Edit bucket tags' }))

      // The fixture's tag is team=platform; the editor starts from it.
      fireEvent.change(screen.getByLabelText('Tag key 1'), {
        target: { value: 'stage' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Save bucket tags' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        tags: [{ Key: 'stage', Value: 'platform' }],
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('removes every bucket tag', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/bucket-settings-edit', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Properties' }))
      fireEvent.click(await screen.findByRole('button', { name: 'Remove bucket tags' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({ bucket: 'logs-bucket', remove_tags: true })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('removes the block public access configuration from the bucket page', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/bucket-settings-edit', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Permissions' }))
      fireEvent.click(
        await screen.findByRole('button', {
          name: 'Remove block public access configuration',
        }),
      )

      await waitFor(() => expect(sent.length).toBe(1))
      // DeletePublicAccessBlock removes the configuration itself, rather than saving all four false.
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        remove_public_access_block: true,
      })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('does not offer to remove a public access block that is not configured', async () => {
    pinRegion('us-east-1')
    const base = stubPath('/api/s3/bucket-settings', {
      ok: true,
      bucket: 'logs-bucket',
      settings: {
        ownership: 'BucketOwnerEnforced',
        block_public_access: {
          BlockPublicAcls: false,
          IgnorePublicAcls: false,
          BlockPublicPolicy: false,
          RestrictPublicBuckets: false,
        },
        public_access_block_configured: false,
        versioning: false,
        tags: [],
        encryption: 'AES256',
        bucket_key: false,
        object_lock: false,
      },
    })
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Permissions' }))
      expect(
        await screen.findByText(
          'No block public access configuration is set on this bucket.',
        ),
      ).toBeTruthy()
      expect(
        screen.queryByRole('button', { name: 'Remove block public access configuration' }),
      ).toBeNull()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('does not offer to edit the ACL where S3 turns ACLs off', async () => {
    pinRegion('us-east-1')
    const base = stubPath('/api/s3/bucket-settings', {
      ok: true,
      bucket: 'logs-bucket',
      settings: {
        ownership: 'BucketOwnerEnforced',
        block_public_access: {},
        versioning: false,
        tags: [],
        encryption: 'AES256',
        bucket_key: false,
        object_lock: false,
      },
    })
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('tab', { name: 'Permissions' }))
      const edit = await screen.findByRole('button', { name: 'Edit acl' })
      expect(edit.disabled).toBe(true)
      expect(screen.getByText(/ACLs are disabled for this bucket/)).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('deletes one object from its view, after confirming', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/exec', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('link', { name: 'reports/2026.csv' }))

      await screen.findByRole('heading', { name: 'reports/2026.csv' })
      // The object's page carries Delete; the closed confirm's button shares the name, so the first is the page's.
      fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0])

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
      fireEvent.click(screen.getByRole('link', { name: 'reports/2026.csv' }))
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
      // The header action and the closed modal's button share a name; the closed modal stays in the DOM, so the first is the page's.
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

  it('edits and removes an object tag set', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/object-tags', { ok: true, status: 200, tags: [] }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('link', { name: 'reports/2026.csv' }))
      await screen.findByRole('heading', { name: 'reports/2026.csv' })

      fireEvent.click(screen.getByRole('tab', { name: 'Tags' }))
      fireEvent.click(await screen.findByRole('button', { name: 'Edit object tags' }))
      fireEvent.change(screen.getByLabelText('Object tag key 1'), {
        target: { value: 'stage' },
      })
      fireEvent.change(screen.getByLabelText('Object tag value 1'), {
        target: { value: 'prod' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Save object tags' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        key: 'reports/2026.csv',
        tags: [{ Key: 'stage', Value: 'prod' }],
      })

      fireEvent.click(screen.getByRole('button', { name: 'Remove object tags' }))
      await waitFor(() => expect(sent.length).toBe(2))
      expect(sent[1].tags).toEqual([])
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('adds and removes an object annotation', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/object-annotation', { ok: true, status: 200 }, sent)
    try {
      await openBucket()
      fireEvent.click(screen.getByRole('link', { name: 'reports/2026.csv' }))
      await screen.findByRole('heading', { name: 'reports/2026.csv' })

      fireEvent.click(screen.getByRole('tab', { name: 'Annotations' }))
      fireEvent.click(await screen.findByRole('button', { name: 'Add annotation' }))
      fireEvent.change(screen.getByLabelText('Annotation name'), {
        target: { value: 'review' },
      })
      fireEvent.change(screen.getByLabelText('Annotation content'), {
        target: { value: 'looks good' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Save annotation' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        bucket: 'logs-bucket',
        key: 'reports/2026.csv',
        name: 'review',
        body: 'looks good',
      })

      fireEvent.click(screen.getByRole('button', { name: 'Remove annotation note' }))
      await waitFor(() => expect(sent.length).toBe(2))
      expect(sent[1]).toMatchObject({ name: 'note', remove: true })
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('sets retention and legal hold from the object view', async () => {
    pinRegion('us-east-1')
    const retention = []
    const holds = []
    const baseRetention = stubOnce(
      '/api/s3/object-retention',
      { ok: true, status: 200 },
      retention,
    )
    try {
      const base = stubOnce(
        '/api/s3/object-legal-hold',
        { ok: true, status: 200 },
        holds,
      )
      try {
        await openBucket()
        fireEvent.click(screen.getByRole('link', { name: 'reports/2026.csv' }))
        await screen.findByRole('heading', { name: 'reports/2026.csv' })

        fireEvent.click(screen.getByRole('tab', { name: 'Object Lock' }))
        fireEvent.click(await screen.findByRole('button', { name: 'Edit retention' }))

        const user = userEvent.setup()
        const modeTrigger = screen
          .getAllByRole('button')
          .find((button) => button.textContent.trim() === 'Governance')
        await user.click(modeTrigger)
        await user.click(await screen.findByRole('option', { name: 'Compliance' }))
        fireEvent.change(screen.getByLabelText('Retain until'), {
          target: { value: '2030-01-01T00:00:00Z' },
        })
        fireEvent.click(screen.getByRole('button', { name: 'Save retention' }))

        await waitFor(() => expect(retention.length).toBe(1))
        expect(retention[0]).toMatchObject({
          bucket: 'logs-bucket',
          key: 'reports/2026.csv',
          mode: 'COMPLIANCE',
          until: '2030-01-01T00:00:00Z',
        })

        fireEvent.click(screen.getByRole('button', { name: 'Edit legal hold' }))
        const holdTrigger = screen
          .getAllByRole('button')
          .find((button) => button.textContent.trim() === 'Off')
        await user.click(holdTrigger)
        await user.click(await screen.findByRole('option', { name: 'On' }))
        fireEvent.click(screen.getByRole('button', { name: 'Save legal hold' }))

        await waitFor(() => expect(holds.length).toBe(1))
        expect(holds[0]).toMatchObject({ key: 'reports/2026.csv', status: 'ON' })
      } finally {
        vi.stubGlobal('fetch', base)
      }
    } finally {
      vi.stubGlobal('fetch', baseRetention)
    }
  })

  it('still uploads typed contents when no file is chosen', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/object', { ok: true, status: 200, key: 'notes.txt' }, sent)
    try {
      await openBucket()
      // The header action and the closed modal's button share a name, so the first is the page's.
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

  it('uploads a file above the part size in parts', async () => {
    pinRegion('us-east-1')
    const calls = []
    const base = globalThis.fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url, options = {}) => {
        const path = String(url).split('?')[0]
        if (path === '/api/s3/multipart-create') {
          calls.push({ kind: 'create', body: JSON.parse(options.body) })
          return {
            ok: true,
            status: 200,
            text: async () => JSON.stringify({ ok: true, upload_id: 'upload-1' }),
          }
        }
        if (path === '/api/s3/multipart-part') {
          calls.push({ kind: 'part', url: String(url), size: options.body?.size })
          return {
            ok: true,
            status: 200,
            text: async () => JSON.stringify({ ok: true, etag: `"etag-${calls.length}"` }),
          }
        }
        if (path === '/api/s3/multipart-complete') {
          calls.push({ kind: 'complete', body: JSON.parse(options.body) })
          return { ok: true, status: 200, text: async () => JSON.stringify({ ok: true }) }
        }
        return base(url, options)
      }),
    )
    try {
      await openBucket()
      fireEvent.click(screen.getAllByRole('button', { name: 'Upload' })[0])
      const big = new File([new Uint8Array(9 * 1024 * 1024)], 'big.bin', {
        type: 'application/octet-stream',
      })
      const input = document.querySelector('input[type="file"]')
      Object.defineProperty(input, 'files', { value: [big], configurable: true })
      fireEvent.change(input)

      const dialog = await screen.findByRole('dialog', { name: 'Upload object' })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Upload' }))

      await waitFor(() => expect(calls.some((call) => call.kind === 'complete')).toBe(true), {
        timeout: 15000,
      })
      // 9 MiB at 5 MiB a part is two parts, and the complete names both.
      expect(calls.filter((call) => call.kind === 'part').length).toBe(2)
      expect(calls.find((call) => call.kind === 'create').body).toMatchObject({
        bucket: 'logs-bucket',
        key: 'big.bin',
      })
      expect(calls.find((call) => call.kind === 'complete').body.parts.length).toBe(2)
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
    // Creating one belongs to the Multi-Region tab, not to the single-bucket page.
    expect(
      screen.getByRole('button', { name: 'Create Multi-Region access point' }),
    ).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Create access point' })).toBeNull()
  })

  it('creates a Multi-Region access point over two Regions and shows its operation', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/mrap', RESPONSES['/api/s3/mrap'], sent)
    const restore = withBuckets([WEST_BUCKET, EAST_BUCKET])
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')
      fireEvent.click(screen.getByRole('tab', { name: 'Multi-Region' }))
      await screen.findByText('world-point')

      const dialog = await openMultiRegionCreate('new-world-point', [/logs-bucket/, /west-bucket/])
      fireEvent.click(within(dialog).getByRole('button', { name: 'Create' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        region: 'us-east-1',
        name: 'new-world-point',
        buckets: ['logs-bucket', 'west-bucket'],
      })
      // The create is asynchronous: the answer's operation is shown with its token, and the listing reloads.
      expect(
        await within(dialog).findByText(/async-request\/mrap\/create/),
      ).toBeTruthy()
      expect(within(dialog).getAllByText('SUCCEEDED').length).toBeGreaterThan(0)
      expect(
        await screen.findByText('Multi-Region access point new-world-point is ready'),
      ).toBeTruthy()
    } finally {
      restore()
      vi.stubGlobal('fetch', base)
    }
  })

  it('refuses two member buckets in one Region before the request', async () => {
    pinRegion('us-east-1')
    const restore = withBuckets([EAST_BUCKET])
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')
      fireEvent.click(screen.getByRole('tab', { name: 'Multi-Region' }))
      await screen.findByText('world-point')

      const dialog = await openMultiRegionCreate('new-world-point', [/logs-bucket/, /east-bucket/])
      // Both are in us-east-1, which is the create S3 would refuse.
      expect(screen.getByText(/two are in us-east-1/)).toBeTruthy()
      // The closed Object Lambda create modal also has a Create, so this is the open one's.
      expect(within(dialog).getByRole('button', { name: 'Create' }).disabled).toBe(true)
    } finally {
      restore()
    }
  })

  it('shows the operation that created a Multi-Region access point in its details', async () => {
    pinRegion('us-east-1')
    const base = stubOnce('/api/s3/mrap', RESPONSES['/api/s3/mrap'], [])
    const restore = withBuckets([WEST_BUCKET])
    const listing = RESPONSES['/api/s3/access-points']
    RESPONSES['/api/s3/access-points'] = (url) => {
      const answer = listing(url)
      if (answer.section !== 'multi-region') return answer
      // The refresh after the create lists what it made.
      const made = {
        ...answer.access_points[0],
        name: 'new-world-point',
        alias: 'new-world-point.mrap',
      }
      return { ...answer, access_points: [made] }
    }
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')
      fireEvent.click(screen.getByRole('tab', { name: 'Multi-Region' }))
      await screen.findByText('new-world-point')

      const dialog = await openMultiRegionCreate('new-world-point', [/logs-bucket/, /west-bucket/])
      fireEvent.click(within(dialog).getByRole('button', { name: 'Create' }))
      await waitFor(() => expect(screen.getAllByText('SUCCEEDED').length).toBe(3))
      // Every closed modal keeps a Close, so the create dialog's is the one to press.
      fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }))

      // The row's view carries the operation, whose token exists only in the answer this page still holds.
      const named = (await screen.findAllByText('new-world-point')).find((cell) =>
        cell.closest('tr'),
      )
      fireEvent.click(within(named.closest('tr')).getByRole('radio'))
      fireEvent.click(screen.getByRole('button', { name: 'View details' }))

      const details = await screen.findByRole('dialog', {
        name: 'Access point new-world-point',
      })
      expect(within(details).getByText('Creation operation')).toBeTruthy()
      expect(within(details).getByText(/async-request\/mrap\/create/)).toBeTruthy()
    } finally {
      RESPONSES['/api/s3/access-points'] = listing
      restore()
      vi.stubGlobal('fetch', base)
    }
  })

  it('opens a Multi-Region access point: its buckets, its routes and its policy', async () => {
    pinRegion('us-east-1')
    renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
    await screen.findByText('reports-point')

    fireEvent.click(screen.getByRole('tab', { name: 'Multi-Region' }))
    await screen.findByText('world-point')
    fireEvent.click(screen.getAllByRole('radio')[0])
    fireEvent.click(screen.getByRole('button', { name: 'View details' }))

    const dialog = await screen.findByRole('dialog', { name: 'Access point world-point' })
    // The listing has none of this: the report, the dials and the policy are three reads on the access point.
    expect(screen.getByText('Routes')).toBeTruthy()
    expect(screen.getAllByText('100%').length).toBe(2)
    expect(screen.getByText(/"Statement"/)).toBeTruthy()
  })

  it('deletes a Multi-Region access point after confirming', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/mrap-delete', RESPONSES['/api/s3/mrap-delete'], sent)
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')
      fireEvent.click(screen.getByRole('tab', { name: 'Multi-Region' }))
      await screen.findByText('world-point')

      fireEvent.click(screen.getAllByRole('radio')[0])
      // The header's action and the closed dialog's button share a name, so the first is the page's.
      fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0])

      const dialog = await screen.findByRole('dialog', {
        name: 'Delete Multi-Region access point',
      })
      // Deleting one is asynchronous, and the dialog says so rather than promising it is already gone.
      expect(screen.getByText(/member buckets and their objects are not touched/)).toBeTruthy()
      fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        region: 'us-east-1',
        name: 'world-point',
      })
      expect(await screen.findByText('Deleted access point world-point')).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('writes a Multi-Region access point policy, which is replaced and not removed', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/mrap-policy', RESPONSES['/api/s3/mrap-policy'], sent)
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')
      fireEvent.click(screen.getByRole('tab', { name: 'Multi-Region' }))
      await screen.findByText('world-point')

      fireEvent.click(screen.getAllByRole('radio')[0])
      fireEvent.click(screen.getByRole('button', { name: 'Edit policy' }))

      const dialog = await screen.findByRole('dialog', { name: /Edit policy/ })
      // The editor opens on the policy the access point holds now.
      const editor = within(dialog).getByRole('textbox')
      await waitFor(() => expect(editor.value).toContain('Statement'))
      // S3 Control has no delete for a Multi-Region policy.
      expect(within(dialog).queryByRole('button', { name: 'Remove policy' })).toBeNull()

      const document = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow"}]}'
      fireEvent.change(editor, { target: { value: document } })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        region: 'us-east-1',
        name: 'world-point',
        policy: document,
      })
      expect(await screen.findByText('Access point policy saved')).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('sets a traffic dial from the routes table', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce('/api/s3/mrap-routes', RESPONSES['/api/s3/mrap-routes'], sent)
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')
      fireEvent.click(screen.getByRole('tab', { name: 'Multi-Region' }))
      await screen.findByText('world-point')
      fireEvent.click(screen.getAllByRole('radio')[0])
      fireEvent.click(screen.getByRole('button', { name: 'View details' }))

      const dialog = await screen.findByRole('dialog', { name: 'Access point world-point' })
      // The detail is its own read: the dials exist only once it lands.
      await screen.findAllByText('100%')
      fireEvent.click(screen.getByRole('button', { name: 'Edit traffic dials' }))

      // One dial per member: the second bucket is the one switched off.
      const user = userEvent.setup()
      await user.click(
        within(dialog).getByRole('button', { name: /Traffic dial for west-bucket/ }),
      )
      await user.click(await screen.findByRole('option', { name: 'Inactive (0%)' }))
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        arn: 'arn:aws:s3::111111111111:accesspoint/world-point.mrap',
        routes: [
          { bucket: 'logs-bucket', traffic: '100' },
          { bucket: 'west-bucket', traffic: '0' },
        ],
      })
      expect(await screen.findByText('Traffic dials saved for world-point')).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('refuses to switch every member off', async () => {
    pinRegion('us-east-1')
    renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
    await screen.findByText('reports-point')
    fireEvent.click(screen.getByRole('tab', { name: 'Multi-Region' }))
    await screen.findByText('world-point')
    fireEvent.click(screen.getAllByRole('radio')[0])
    fireEvent.click(screen.getByRole('button', { name: 'View details' }))

    const dialog = await screen.findByRole('dialog', { name: 'Access point world-point' })
    await screen.findAllByText('100%')
    fireEvent.click(screen.getByRole('button', { name: 'Edit traffic dials' }))

    const user = userEvent.setup()
    for (const bucket of ['logs-bucket', 'west-bucket']) {
      await user.click(
        within(dialog).getByRole('button', { name: new RegExp(`Traffic dial for ${bucket}`) }),
      )
      await user.click(await screen.findByRole('option', { name: 'Inactive (0%)' }))
    }

    // S3 refuses an access point with every member switched off, so the page does not offer to ask.
    expect(screen.getByText(/At least one Region has to stay Active/)).toBeTruthy()
    // The closed dialogs keep their own Save, so this is the one in the access point's dialog.
    expect(within(dialog).getByRole('button', { name: 'Save' }).disabled).toBe(true)
  })

  it('opens an Object Lambda access point with its configuration, and no policy is a state', async () => {
    pinRegion('us-east-1')
    renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
    await screen.findByText('reports-point')

    fireEvent.click(screen.getByRole('tab', { name: 'Object Lambda' }))
    await screen.findByText('lambda-point')
    fireEvent.click(screen.getAllByRole('radio')[0])
    fireEvent.click(screen.getByRole('button', { name: 'View details' }))

    const dialog = await screen.findByRole('dialog', { name: 'Access point lambda-point' })
    expect(screen.getByText(/SupportingAccessPoint/)).toBeTruthy()
    expect(screen.getByText('No policy on this access point.')).toBeTruthy()
  })

  it('writes an Object Lambda access point policy from the editor', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce(
      '/api/s3/access-point-policy-edit',
      RESPONSES['/api/s3/access-point-policy-edit'],
      sent,
    )
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')
      fireEvent.click(screen.getByRole('tab', { name: 'Object Lambda' }))
      await screen.findByText('lambda-point')
      fireEvent.click(screen.getAllByRole('radio')[0])
      fireEvent.click(screen.getByRole('button', { name: 'Edit policy' }))

      const dialog = await screen.findByRole('dialog', { name: /Edit policy/ })
      const editor = within(dialog).getByRole('textbox')
      await waitFor(() => expect(editor.value).toContain('Statement'))
      const document = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow"}]}'
      fireEvent.change(editor, { target: { value: document } })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

      await waitFor(() => expect(sent.length).toBe(1))
      // The Object Lambda policy is its own resource, so the editor names its section.
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        region: 'us-east-1',
        section: 'object-lambda',
        name: 'lambda-point',
        policy: document,
      })
      expect(await screen.findByText('Access point policy saved')).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('removes an Object Lambda access point policy from the editor', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce(
      '/api/s3/access-point-policy-edit',
      RESPONSES['/api/s3/access-point-policy-edit'],
      sent,
    )
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')
      fireEvent.click(screen.getByRole('tab', { name: 'Object Lambda' }))
      await screen.findByText('lambda-point')
      fireEvent.click(screen.getAllByRole('radio')[0])
      fireEvent.click(screen.getByRole('button', { name: 'Edit policy' }))

      const dialog = await screen.findByRole('dialog', { name: /Edit policy/ })
      const editor = within(dialog).getByRole('textbox')
      await waitFor(() => expect(editor.value).toContain('Statement'))
      fireEvent.click(screen.getByRole('button', { name: 'Remove policy' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        section: 'object-lambda',
        name: 'lambda-point',
        policy: null,
      })
      expect(await screen.findByText('Access point policy removed')).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('creates an Object Lambda access point from its tab', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce(
      '/api/s3/object-lambda',
      { ok: true, status: 200, name: 'new-lambda-point', created: true },
      sent,
    )
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')
      fireEvent.click(screen.getByRole('tab', { name: 'Object Lambda' }))
      await screen.findByText('lambda-point')
      fireEvent.click(screen.getByRole('button', { name: 'Create Object Lambda access point' }))

      const dialog = await screen.findByRole('dialog', {
        name: 'Create Object Lambda access point',
      })
      fireEvent.change(screen.getByPlaceholderText('my-object-lambda'), {
        target: { value: 'new-lambda-point' },
      })

      // Cloudscape's Select opens under user-event, and its options are in a portal.
      const user = userEvent.setup()
      const trigger = (await screen.findAllByRole('button')).find(
        (button) => button.textContent.trim() === 'Choose an access point',
      )
      await user.click(trigger)
      await user.click(await screen.findByRole('option', { name: /reports-point/ }))

      fireEvent.change(
        screen.getByPlaceholderText(
          'arn:aws:lambda:us-east-1:111111111111:function:my-transform',
        ),
        { target: { value: 'arn:aws:lambda:us-east-1:111111111111:function:transform-demo' } },
      )
      fireEvent.click(within(dialog).getByRole('button', { name: 'Create' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        region: 'us-east-1',
        name: 'new-lambda-point',
        supporting_access_point:
          'arn:aws:s3:us-east-1:111111111111:accesspoint/reports-point',
        function_arn: 'arn:aws:lambda:us-east-1:111111111111:function:transform-demo',
        actions: ['GetObject', 'HeadObject'],
        cloudwatch_metrics: false,
      })
      expect(await screen.findByText('Object Lambda access point new-lambda-point created')).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('deletes an Object Lambda access point after confirming', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce(
      '/api/s3/object-lambda-delete',
      { ok: true, status: 204, name: 'lambda-point' },
      sent,
    )
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')
      fireEvent.click(screen.getByRole('tab', { name: 'Object Lambda' }))
      await screen.findByText('lambda-point')

      fireEvent.click(screen.getAllByRole('radio')[0])
      fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0])

      const dialog = await screen.findByRole('dialog', {
        name: 'Delete Object Lambda access point',
      })
      expect(
        screen.getByText(/supporting access point and its bucket are not touched/),
      ).toBeTruthy()
      fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        region: 'us-east-1',
        name: 'lambda-point',
      })
      expect(await screen.findByText('Deleted access point lambda-point')).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
  })

  it('replaces the Object Lambda configuration from its details view', async () => {
    pinRegion('us-east-1')
    const sent = []
    const base = stubOnce(
      '/api/s3/object-lambda-configuration',
      { ok: true, status: 200, name: 'lambda-point' },
      sent,
    )
    try {
      renderAt(<AccessPoints />, ['/s3/access-points?region=us-east-1'])
      await screen.findByText('reports-point')
      fireEvent.click(screen.getByRole('tab', { name: 'Object Lambda' }))
      await screen.findByText('lambda-point')
      fireEvent.click(screen.getAllByRole('radio')[0])
      fireEvent.click(screen.getByRole('button', { name: 'View details' }))

      const details = await screen.findByRole('dialog', { name: 'Access point lambda-point' })
      fireEvent.click(within(details).getByRole('button', { name: 'Edit configuration' }))

      const dialog = await screen.findByRole('dialog', {
        name: /Edit configuration: lambda-point/,
      })
      const editor = within(dialog).getByRole('textbox')
      await waitFor(() => expect(editor.value).toContain('SupportingAccessPoint'))
      const replacement =
        '<Configuration><SupportingAccessPoint>arn:aws:s3:us-east-1:111111111111:accesspoint/reports-point</SupportingAccessPoint>' +
        '<TransformationConfigurations><TransformationConfiguration><Actions>' +
        '<Action>GetObject</Action></Actions><ContentTransformation><AwsLambda>' +
        '<FunctionArn>arn:aws:lambda:us-east-1:111111111111:function:edited</FunctionArn>' +
        '</AwsLambda></ContentTransformation></TransformationConfiguration>' +
        '</TransformationConfigurations></Configuration>'
      fireEvent.change(editor, { target: { value: replacement } })
      fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

      await waitFor(() => expect(sent.length).toBe(1))
      expect(sent[0]).toMatchObject({
        account: '111111111111',
        region: 'us-east-1',
        name: 'lambda-point',
        configuration: replacement,
      })
      expect(await screen.findByText('Configuration saved for lambda-point')).toBeTruthy()
    } finally {
      vi.stubGlobal('fetch', base)
    }
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
