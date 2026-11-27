import { useEffect, useRef, useState } from 'react'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Header from '@cloudscape-design/components/header'
import Input from '@cloudscape-design/components/input'
import KeyValuePairs from '@cloudscape-design/components/key-value-pairs'
import Modal from '@cloudscape-design/components/modal'
import Select from '@cloudscape-design/components/select'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import Table from '@cloudscape-design/components/table'
import Toggle from '@cloudscape-design/components/toggle'
import { api } from '../api'
import { Shell } from '../components/Shell'

// The gateway's own record: newest first, paged by id, with a live tail that polls for what is new.
const PAGE = 100
const STATUS_OPTIONS = [
  { label: 'Any status', value: '' },
  { label: '2xx success', value: '2xx' },
  { label: '3xx redirect', value: '3xx' },
  { label: '4xx client error', value: '4xx' },
  { label: '5xx server error', value: '5xx' },
]

const statusType = (status) => {
  if (status >= 500) return 'error'
  if (status >= 400) return 'warning'
  if (status >= 300) return 'info'
  if (status >= 200) return 'success'
  return 'stopped'
}

const clock = (time) => (time.length >= 19 ? time.slice(11, 19) : time)

export default function Traffic() {
  const [entries, setEntries] = useState([])
  const [service, setService] = useState('')
  const [status, setStatus] = useState('')
  const [live, setLive] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [capacity, setCapacity] = useState(500)
  const [buffered, setBuffered] = useState(0)
  const [reloadKey, setReloadKey] = useState(0)
  const latest = useRef(0)

  useEffect(() => {
    let current = true
    setLoading(true)
    api
      .traffic({ limit: PAGE, service, status })
      .then((answer) => {
        if (!current) return
        setEntries(answer.entries)
        setCapacity(answer.capacity)
        setBuffered(answer.buffered)
        latest.current = answer.latest
        setError('')
      })
      .catch((err) => {
        if (current) setError(err.message)
      })
      .finally(() => {
        if (current) setLoading(false)
      })
    return () => {
      current = false
    }
  }, [service, status, reloadKey])

  // A tail reads what is newer than the last id it saw, so a poll cannot duplicate a row.
  useEffect(() => {
    if (!live) return undefined
    const timer = setInterval(() => {
      api
        .traffic({ since: latest.current, limit: 500, service, status })
        .then((answer) => {
          latest.current = answer.latest
          setCapacity(answer.capacity)
          setBuffered(answer.buffered)
          if (!answer.entries.length) return
          setEntries((shown) => {
            const seen = new Set(shown.map((entry) => entry.id))
            const fresh = answer.entries
              .filter((entry) => !seen.has(entry.id))
              .reverse()
            return [...fresh, ...shown].slice(0, 500)
          })
        })
        .catch(() => {
          // A failed poll leaves the next tick to retry.
        })
    }, 2000)
    return () => clearInterval(timer)
  }, [live, service, status])

  const loadOlder = async () => {
    const oldest = entries[entries.length - 1]?.id
    if (!oldest) return
    try {
      const answer = await api.traffic({ before: oldest, limit: PAGE, service, status })
      setEntries((shown) => [...shown, ...answer.entries])
    } catch (err) {
      setError(err.message)
    }
  }

  const columns = [
    { id: 'time', header: 'Time', cell: (entry) => clock(entry.time), width: 90 },
    { id: 'method', header: 'Method', cell: (entry) => entry.method, width: 90 },
    { id: 'service', header: 'Service', cell: (entry) => entry.service || '—' },
    { id: 'operation', header: 'Operation', cell: (entry) => entry.operation || '—' },
    {
      id: 'status',
      header: 'Status',
      cell: (entry) => (
        <StatusIndicator type={statusType(entry.status)}>
          {entry.status || 'none'}
        </StatusIndicator>
      ),
    },
    { id: 'duration', header: 'Duration', cell: (entry) => `${entry.duration_ms} ms` },
    {
      id: 'request',
      header: 'Request',
      cell: (entry) => (
        <Box>
          <code>{entry.path || '/'}</code>
          {entry.query.length > 0 && (
            <Box variant="small" color="text-body-secondary">
              ?{entry.query.join('&')}
            </Box>
          )}
        </Box>
      ),
    },
    {
      id: 'details',
      header: '',
      cell: (entry) => (
        <Button variant="inline-link" onClick={() => setSelected(entry)}>
          Details
        </Button>
      ),
    },
  ]

  return (
    <Shell
      activeHref="/traffic"
      breadcrumbs={[{ text: 'Request inspector', href: '/traffic' }]}
    >
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="What the gateway saw, newest first. Header and query names only; every credential value is redacted."
          >
            Request inspector
          </Header>
        }
      >
        <SpaceBetween size="l">
          {error && <Alert type="error">{error}</Alert>}
          <SpaceBetween direction="horizontal" size="xs">
            <Input
              type="search"
              ariaLabel="Filter by service"
              placeholder="Filter by service"
              value={service}
              onChange={({ detail }) => setService(detail.value)}
            />
            <Select
              ariaLabel="Filter by status"
              selectedOption={STATUS_OPTIONS.find((option) => option.value === status)}
              options={STATUS_OPTIONS}
              onChange={({ detail }) => setStatus(detail.selectedOption.value)}
            />
          </SpaceBetween>
          <Table
            variant="container"
            loading={loading}
            loadingText="Reading the gateway's record"
            items={entries}
            trackBy="id"
            columnDefinitions={columns}
            header={
              <Header
                variant="h2"
                counter={`(${entries.length})`}
                description={`The last ${capacity} requests are kept; ${buffered} held now.`}
                actions={
                  <SpaceBetween direction="horizontal" size="xs">
                    <Toggle
                      checked={live}
                      onChange={({ detail }) => setLive(detail.checked)}
                    >
                      Live tail
                    </Toggle>
                    <Button iconName="refresh" onClick={() => setReloadKey((key) => key + 1)}>
                      Refresh
                    </Button>
                  </SpaceBetween>
                }
              >
                Requests
              </Header>
            }
            empty={
              <Box textAlign="center" color="inherit">
                The gateway has not seen a request yet.
              </Box>
            }
          />
          <Box>
            <Button onClick={loadOlder} disabled={!entries.length}>
              Load older requests
            </Button>
          </Box>
        </SpaceBetween>
      </ContentLayout>

      <Modal
        visible={!!selected}
        onDismiss={() => setSelected(null)}
        header={selected ? `Request ${selected.id}` : 'Request'}
        footer={
          <Box float="right">
            <Button variant="primary" onClick={() => setSelected(null)}>
              Close
            </Button>
          </Box>
        }
      >
        {selected && (
          <SpaceBetween size="m">
            <KeyValuePairs
              columns={2}
              items={[
                { label: 'Time', value: selected.time },
                { label: 'Request', value: `${selected.method} ${selected.path || '/'}` },
                { label: 'Service', value: selected.service || '—' },
                { label: 'Operation', value: selected.operation || '—' },
                { label: 'Status', value: String(selected.status) },
                { label: 'Duration', value: `${selected.duration_ms} ms` },
                { label: 'Account', value: selected.account || 'anonymous' },
                { label: 'Region', value: selected.region || '—' },
                { label: 'Request id', value: selected.request_id || '—' },
                { label: 'Request body', value: `${selected.request_bytes} bytes` },
                { label: 'Response body', value: `${selected.response_bytes} bytes` },
                {
                  label: 'Query parameters',
                  value: selected.query.length ? selected.query.join(', ') : 'none',
                },
                {
                  label: 'Headers',
                  value: selected.headers.length ? selected.headers.join(', ') : 'none',
                },
                {
                  label: 'Credentials',
                  value: selected.credentials.length
                    ? selected.credentials.join(', ')
                    : 'none',
                },
                {
                  label: 'Bucket',
                  value: selected.bucket || '—',
                },
              ]}
            />
            <Box color="text-body-secondary" fontSize="body-s">
              Only header names, query names and body sizes are kept. No header or query
              value is stored, so a token, a cookie or a signature never reaches this page.
            </Box>
          </SpaceBetween>
        )}
      </Modal>
    </Shell>
  )
}
