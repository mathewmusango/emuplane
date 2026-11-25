import { useCallback, useEffect, useState } from 'react'
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
import { api } from '../api'
import { useSession } from '../context'
import { useRecent } from '../prefs'
import { Shell, loadCatalogue } from '../components/Shell'
import { ServiceIcon } from '../serviceIcons'
import { serviceLabel } from '../serviceLabels'
import { serviceHref } from '../serviceRoutes'

// Console Home is a grid of remembered widgets; "Reset to default layout" brings every widget back.

const HIDDEN_KEY = 'emuplane:widgets:hidden'

const WIDGETS = [
  { id: 'recent', title: 'Recently visited' },
  { id: 'welcome', title: 'Welcome to Emuplane' },
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
  const [counts, setCounts] = useState({})
  const [catalogue, setCatalogue] = useState(null)
  const [error, setError] = useState('')
  const [hidden, setHidden] = useState(readHidden)
  const [choosing, setChoosing] = useState(false)
  const [welcomeDismissed, setWelcomeDismissed] = useState(
    () => localStorage.getItem('emuplane:welcome') === 'seen',
  )

  const load = useCallback(async () => {
    try {
      const [cat, countData] = await Promise.all([
        loadCatalogue(),
        account && region ? api.counts(account, region) : Promise.resolve({ counts: {} }),
      ])
      setCatalogue(cat)
      setCounts(countData?.counts || {})
      setError('')
    } catch (err) {
      setError(err.message)
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

  const actionServices = Object.keys(catalogue?.services || {}).length
  const totalResources = Object.values(counts).reduce(
    (sum, value) => sum + (Number(value) || 0),
    0,
  )

  const dismissWelcome = () => {
    setWelcomeDismissed(true)
    try {
      localStorage.setItem('emuplane:welcome', 'seen')
    } catch {
      // ignore
    }
  }

  // Services read as a two-column list: icon, name, and an underline on hover.
  const shortcuts = (names) => (
    <ul className="home-links">
      {names.map((name) => (
        <li key={name}>
          <a
            href={serviceHref(name)}
            onClick={(event) => {
              event.preventDefault()
              navigate(serviceHref(name))
            }}
          >
            <ServiceIcon name={name} size={18} />
            {serviceLabel(name)}
          </a>
        </li>
      ))}
    </ul>
  )

  const recentList = recent.slice(0, meta?.recent_limit || 5)

  const show = (id) => !hidden.includes(id)

  return (
    <Shell activeHref="/" breadcrumbs={[]}>
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
                      href="/Account"
                      onFollow={(event) => {
                        event.preventDefault()
                        navigate('/Account')
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
