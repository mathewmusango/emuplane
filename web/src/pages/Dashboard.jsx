import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import Checkbox from '@cloudscape-design/components/checkbox'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Header from '@cloudscape-design/components/header'
import Link from '@cloudscape-design/components/link'
import Modal from '@cloudscape-design/components/modal'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import { api } from '../api'
import { useSession } from '../context'
import { useRecent } from '../prefs'
import { Shell, loadCatalogue } from '../components/Shell'
import { serviceIconUrl } from '../serviceIcons'
import { serviceLabel } from '../serviceLabels'

// Console Home is a grid of widgets rather than one fixed page: the layout the
// visitor settles on is remembered, and "Reset to default layout" brings every
// widget back. Same shape as the console's own home.

const HIDDEN_KEY = 'emuplane:widgets:hidden'

const WIDGETS = [
  { id: 'recent', title: 'Recently visited' },
  { id: 'welcome', title: 'Welcome to Emuplane' },
  { id: 'health', title: 'Backend health' },
  { id: 'usage', title: 'Usage' },
  { id: 'endpoints', title: 'Endpoints' },
]

const readHidden = () => {
  try {
    const raw = JSON.parse(localStorage.getItem(HIDDEN_KEY) || '[]')
    return Array.isArray(raw) ? raw : []
  } catch {
    return []
  }
}

function formatUptime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days) return `${days}d ${hours}h`
  if (hours) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

/** One card in the grid, with the title bar the console's widgets carry. */
function Widget({ title, description, actions, children }) {
  return (
    <Container
      header={
        <Header variant="h2" description={description} actions={actions}>
          {title}
        </Header>
      }
    >
      {children}
    </Container>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { meta, account, region, refresh: refreshMeta } = useSession()
  const { recent } = useRecent(meta?.me?.account)
  const [services, setServices] = useState({})
  const [counts, setCounts] = useState({})
  const [nodes, setNodes] = useState([])
  const [catalogue, setCatalogue] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [hidden, setHidden] = useState(readHidden)
  const [choosing, setChoosing] = useState(false)
  const [welcomeDismissed, setWelcomeDismissed] = useState(
    () => localStorage.getItem('emuplane:welcome') === 'seen',
  )

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [states, cat, countData, nodeRows] = await Promise.all([
        api.services(),
        loadCatalogue(),
        account && region ? api.counts(account, region) : Promise.resolve({ counts: {} }),
        api.nodes(),
      ])
      setServices(states || {})
      setCatalogue(cat)
      setCounts(countData?.counts || {})
      setNodes(Array.isArray(nodeRows) ? nodeRows : [])
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [account, region])

  useEffect(() => {
    load()
  }, [load])

  const hide = (id) => {
    const next = [...new Set([...hidden, id])]
    setHidden(next)
    try {
      localStorage.setItem(HIDDEN_KEY, JSON.stringify(next))
    } catch {
      // storage denied: the choice just does not survive the session
    }
  }

  const resetLayout = () => {
    setHidden([])
    try {
      localStorage.removeItem(HIDDEN_KEY)
    } catch {
      // ignore
    }
  }

  const available = useMemo(
    () => Object.values(services).filter((state) => state?.available !== false).length,
    [services],
  )
  const actionServices = Object.keys(catalogue?.services || {}).length
  const totalResources = Object.values(counts).reduce(
    (sum, value) => sum + (Number(value) || 0),
    0,
  )
  const emulator = nodes[0]?.health || {}

  const dismissWelcome = () => {
    setWelcomeDismissed(true)
    try {
      localStorage.setItem('emuplane:welcome', 'seen')
    } catch {
      // ignore
    }
  }

  // Services read as a two-column list, the way the console's own shortcuts do:
  // icon, name, and an underline on hover — not a row of buttons that wraps at
  // an awkward width.
  const shortcuts = (names) => (
    <ul className="home-links">
      {names.map((name) => (
        <li key={name}>
          <a
            href={`/resources/${name}`}
            onClick={(event) => {
              event.preventDefault()
              navigate(`/resources/${name}`)
            }}
          >
            <img src={serviceIconUrl(name)} alt="" aria-hidden="true" />
            {serviceLabel(name)}
          </a>
        </li>
      ))}
    </ul>
  )

  const recentList = recent.slice(0, meta?.recent_limit || 5)

  const show = (id) => !hidden.includes(id)

  return (
    <Shell activeHref="/" breadcrumbs={[{ text: 'Home', href: '/' }]}>
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="One backend, every region and every account."
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button iconName="refresh" onClick={() => { load(); refreshMeta() }}>
                  Refresh
                </Button>
                <Button onClick={resetLayout}>Reset to default layout</Button>
                <Button variant="primary" onClick={() => setChoosing(true)}>
                  Add widgets
                </Button>
              </SpaceBetween>
            }
          >
            Home
          </Header>
        }
      >
        <SpaceBetween size="l">
          {error && (
            <Alert type="error" header="Could not reach the control plane">
              {error}
            </Alert>
          )}

          <div className="home-grid">
            {show('recent') && (
              <Widget
                title="Recently visited"
                description="Services you opened on this browser."
                actions={
                  <SpaceBetween direction="horizontal" size="xs">
                    <Button onClick={() => navigate('/services')}>All services</Button>
                    <Button
                      variant="icon"
                      iconName="close"
                      ariaLabel="Remove this widget"
                      onClick={() => hide('recent')}
                    />
                  </SpaceBetween>
                }
              >
                {recentList.length ? (
                  shortcuts(recentList)
                ) : (
                  <Box color="text-body-secondary">
                    Nothing yet. Open a service from All services and it lands here.
                  </Box>
                )}
              </Widget>
            )}

            {show('welcome') && (
              <Widget
                title="Welcome to Emuplane"
                actions={
                  <SpaceBetween direction="horizontal" size="xs">
                    {!welcomeDismissed && (
                      <Button onClick={dismissWelcome}>Got it</Button>
                    )}
                    <Button
                      variant="icon"
                      iconName="close"
                      ariaLabel="Remove this widget"
                      onClick={() => hide('welcome')}
                    />
                  </SpaceBetween>
                }
              >
                <SpaceBetween size="m">
                  <Box>
                    Emuplane is the control plane in front of an AWS-compatible
                    backend. Every page here maps to real API calls against it.
                  </Box>
                  <SpaceBetween size="xs">
                    <Link
                      href="/services"
                      onFollow={(event) => {
                        event.preventDefault()
                        navigate('/services')
                      }}
                    >
                      Browse all services
                    </Link>
                    <Link
                      href="/settings"
                      onFollow={(event) => {
                        event.preventDefault()
                        navigate('/settings')
                      }}
                    >
                      Create an access key for the CLI
                    </Link>
                    <Link
                      href="/about"
                      onFollow={(event) => {
                        event.preventDefault()
                        navigate('/about')
                      }}
                    >
                      Read what this instance is
                    </Link>
                  </SpaceBetween>
                </SpaceBetween>
              </Widget>
            )}

            {show('health') && (
              <Widget
                title="Backend health"
                actions={
                  <Button
                    variant="icon"
                    iconName="close"
                    ariaLabel="Remove this widget"
                    onClick={() => hide('health')}
                  />
                }
              >
                <SpaceBetween size="m">
                  <div>
                    <Box variant="awsui-key-label">Emulator</Box>
                    <StatusIndicator
                      type={emulator.reachable ? 'success' : 'error'}
                    >
                      {emulator.reachable
                        ? `reachable · ${emulator.version || '?'}`
                        : 'unreachable'}
                    </StatusIndicator>
                  </div>
                  <div>
                    <Box variant="awsui-key-label">Services answering</Box>
                    <Box fontSize="heading-m">{loading ? '—' : available}</Box>
                  </div>
                  <div>
                    <Box variant="awsui-key-label">Control plane uptime</Box>
                    <Box>{formatUptime(meta?.uptime_seconds)}</Box>
                  </div>
                </SpaceBetween>
              </Widget>
            )}

            {show('usage') && (
              <Widget
                title="Usage"
                description={`Account ${account || '—'} · ${region}`}
                actions={
                  <Button
                    variant="icon"
                    iconName="close"
                    ariaLabel="Remove this widget"
                    onClick={() => hide('usage')}
                  />
                }
              >
                <ColumnLayout columns={2} variant="text-grid">
                  <div>
                    <Box variant="awsui-key-label">Total resources</Box>
                    <Box fontSize="heading-l">{totalResources}</Box>
                    <Box color="text-body-secondary" fontSize="body-s">
                      {actionServices} with console actions
                    </Box>
                  </div>
                  <div>
                    <Box variant="awsui-key-label">Console actions</Box>
                    <Box fontSize="heading-l">{actionServices}</Box>
                    <Box color="text-body-secondary" fontSize="body-s">
                      across the catalogue
                    </Box>
                  </div>
                </ColumnLayout>
              </Widget>
            )}

            {show('endpoints') && (
              <Widget
                title="Endpoints"
                actions={
                  <Button
                    variant="icon"
                    iconName="close"
                    ariaLabel="Remove this widget"
                    onClick={() => hide('endpoints')}
                  />
                }
              >
                <ColumnLayout columns={2} variant="text-grid">
                  <div>
                    <Box variant="awsui-key-label">Console</Box>
                    <Link href={meta?.console} external>
                      {meta?.console || '—'}
                    </Link>
                  </div>
                  <div>
                    <Box variant="awsui-key-label">Gateway</Box>
                    <Link href={meta?.gateway} external>
                      {meta?.gateway || '—'}
                    </Link>
                  </div>
                </ColumnLayout>
              </Widget>
            )}
          </div>
        </SpaceBetween>
      </ContentLayout>

      <Modal
        visible={choosing}
        onDismiss={() => setChoosing(false)}
        header="Add widgets"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button onClick={resetLayout}>Reset to default layout</Button>
              <Button variant="primary" onClick={() => setChoosing(false)}>
                Done
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="s">
          {WIDGETS.map((widget) => (
            <Checkbox
              key={widget.id}
              checked={show(widget.id)}
              onChange={({ detail }) => {
                if (detail.checked) {
                  const next = hidden.filter((id) => id !== widget.id)
                  setHidden(next)
                  try {
                    localStorage.setItem(HIDDEN_KEY, JSON.stringify(next))
                  } catch {
                    // ignore
                  }
                } else {
                  hide(widget.id)
                }
              }}
            >
              {widget.title}
            </Checkbox>
          ))}
        </SpaceBetween>
      </Modal>
    </Shell>
  )
}
