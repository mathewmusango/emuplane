import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Badge from '@cloudscape-design/components/badge'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Header from '@cloudscape-design/components/header'
import Link from '@cloudscape-design/components/link'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import { api } from '../api'
import { useSession } from '../context'
import { useRecent } from '../prefs'
import { Shell, loadCatalogue } from '../components/Shell'
import { serviceIconUrl } from '../serviceIcons'

function formatUptime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days) return `${days}d ${hours}h`
  if (hours) return `${hours}h ${minutes}m`
  return `${minutes}m`
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
  const [bannerBusy, setBannerBusy] = useState(false)

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

  const availableCount = useMemo(
    () => Object.values(services).filter((nodes) => Object.values(nodes || {}).some(Boolean)).length,
    [services],
  )
  const totalResources = useMemo(
    () => Object.values(counts).reduce((sum, value) => sum + (Number(value) || 0), 0),
    [counts],
  )
  const actionServices = Object.keys(catalogue?.services || {}).length
  const emulator = nodes[0]?.health || {}
  const go = (name) => navigate(`/resources/${name}`)

  const disableDefault = async () => {
    setBannerBusy(true)
    try {
      await api.setAccountDisabled(account, true)
      window.location.assign('/logout')
    } catch (err) {
      setError(err.message)
    } finally {
      setBannerBusy(false)
    }
  }

  const shortcuts = (names) => (
    <SpaceBetween direction="horizontal" size="xs">
      {names.map((name) => (
        <Button
          key={name}
          iconUrl={serviceIconUrl(name)}
          onClick={() => go(name)}
        >
          {name}
        </Button>
      ))}
    </SpaceBetween>
  )

  return (
    <Shell activeHref="/" breadcrumbs={[{ text: 'Dashboard', href: '/' }]}>
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="One emulator, every region and every account."
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button iconName="refresh" onClick={() => { load(); refreshMeta() }}>
                  Refresh
                </Button>
                <Button variant="primary" onClick={() => navigate('/services')}>
                  Services
                </Button>
              </SpaceBetween>
            }
            info={
              meta?.platform_admin ? <Badge color="blue">Global admin</Badge> : undefined
            }
          >
            Dashboard
          </Header>
        }
      >
        <SpaceBetween size="l">
          {error && (
            <Alert type="error" header="Could not reach the control plane">
              {error}
            </Alert>
          )}

          {meta?.default_admin && (
            <Container
              header={
                <Header variant="h2">
                  Action required: retire the default administrator
                </Header>
              }
            >
              <SpaceBetween size="m">
                <Alert type="warning" header="This is the default administrator account">
                  {meta.other_global_admins > 0
                    ? `You now have ${meta.other_global_admins} other global admin account(s). Disable or delete this default account so the bootstrap login stops existing.`
                    : 'Create a second global admin from Accounts, then disable or delete this default account.'}
                </Alert>
                <SpaceBetween direction="horizontal" size="xs">
                  <Button
                    variant="primary"
                    loading={bannerBusy}
                    disabled={!meta.other_global_admins}
                    onClick={disableDefault}
                  >
                    Disable this account
                  </Button>
                  <Button onClick={() => navigate('/accounts')}>Manage accounts</Button>
                </SpaceBetween>
              </SpaceBetween>
            </Container>
          )}

          <Container>
            <ColumnLayout columns={3} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Services answering</Box>
                <Box variant="awsui-value-large" fontSize="heading-l">{availableCount}</Box>
                <Box color="text-body-secondary" fontSize="body-s">
                  {actionServices} with console actions
                </Box>
              </div>
              <div>
                <Box variant="awsui-key-label">Total resources</Box>
                <Box variant="awsui-value-large" fontSize="heading-l">{totalResources}</Box>
                <Box color="text-body-secondary" fontSize="body-s">
                  account {account || '—'} · {region}
                </Box>
              </div>
              <div>
                <Box variant="awsui-key-label">Control Plane Uptime</Box>
                <Box variant="awsui-value-large" fontSize="heading-l">
                  {formatUptime(meta?.uptime_seconds)}
                </Box>
                <Box color="text-body-secondary" fontSize="body-s">
                  emulator {meta?.emulator_version || 'unknown'}
                </Box>
              </div>
            </ColumnLayout>
          </Container>

          <Container header={<Header variant="h2">Endpoints</Header>}>
            <ColumnLayout columns={3} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Console</Box>
                <Link href={meta?.console} external>{meta?.console || '—'}</Link>
              </div>
              <div>
                <Box variant="awsui-key-label">Emulator gateway</Box>
                <Link href={meta?.gateway} external>{meta?.gateway || '—'}</Link>
              </div>
              <div>
                <Box variant="awsui-key-label">Emulator</Box>
                <StatusIndicator type={emulator.reachable ? 'success' : 'error'}>
                  {emulator.reachable ? `reachable · ${emulator.version || '?'}` : 'unreachable'}
                </StatusIndicator>
              </div>
            </ColumnLayout>
          </Container>

          {recent.length > 0 && (
            <Container
              header={
                <Header variant="h2" description="Services you opened on this browser.">
                  Recently visited
                </Header>
              }
            >
              {shortcuts(recent.slice(0, meta?.recent_limit || 5))}
            </Container>
          )}
        </SpaceBetween>
      </ContentLayout>
    </Shell>
  )
}
