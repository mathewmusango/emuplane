import { useEffect, useState } from 'react'
import Box from '@cloudscape-design/components/box'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Header from '@cloudscape-design/components/header'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import { api } from '../api'
import { useSession } from '../context'
import { Shell } from '../components/Shell'


function formatUptime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '—'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days) return `${days}d ${hours}h`
  if (hours) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

export default function About() {
  const { meta, me } = useSession()
  const [emulator, setEmulator] = useState({})
  const [available, setAvailable] = useState(null)

  useEffect(() => {
    let live = true
    Promise.all([api.nodes(), api.services()])
      .then(([rows, states]) => {
        if (!live) return
        const health = (Array.isArray(rows) ? rows[0]?.health : null) || {}
        setEmulator(health)
        setAvailable(
          Object.values(states || {}).filter((state) => state?.available !== false).length,
        )
      })
      .catch(() => {
        // The two readings are informative; the page still reports the instance without them.
      })
    return () => {
      live = false
    }
  }, [])

  return (
    <Shell activeHref="/about" breadcrumbs={[{ text: 'About', href: '/about' }]}>
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="A private, prod-shaped emulator of cloud APIs on one host."
          >
            About Emuplane
          </Header>
        }
      >
        <SpaceBetween size="l">
          <ColumnLayout columns={3}>
            <Container header={<Header variant="h3">This instance</Header>}>
              <SpaceBetween size="xs">
                <Box>
                  <Box variant="awsui-key-label">Emuplane</Box>
                  {meta?.version || 'dev'}
                </Box>
                <Box>
                  <Box variant="awsui-key-label">Backend</Box>
                  {meta?.backend || 'unknown'}
                  {meta?.backend_id && meta.backend_id !== meta.backend
                    ? ` (${meta.backend_id})`
                    : ''}
                </Box>
                <Box>
                  <Box variant="awsui-key-label">Emulator</Box>
                  <StatusIndicator type={emulator.reachable ? 'success' : 'error'}>
                    {emulator.reachable
                      ? `reachable · ${meta?.backend_id || 'emulator'} ${emulator.version || '?'}`
                      : 'unreachable'}
                  </StatusIndicator>
                </Box>
                <Box>
                  <Box variant="awsui-key-label">Services answering</Box>
                  {available === null ? '—' : available}
                </Box>
                <Box>
                  <Box variant="awsui-key-label">Control plane uptime</Box>
                  {formatUptime(meta?.uptime_seconds)}
                </Box>
                <Box>
                  <Box variant="awsui-key-label">Signed in</Box>
                  {me?.user} · {me?.role}
                </Box>
              </SpaceBetween>
            </Container>

            <Container header={<Header variant="h3">Tenancy</Header>}>
              <SpaceBetween size="xs">
                {meta?.platform_admin && (
                  <Box>
                    <Box variant="awsui-key-label">Root Accounts</Box>
                    {meta?.total_accounts ?? (meta?.accounts || []).length}
                  </Box>
                )}
                <Box>
                  <Box variant="awsui-key-label">Regions enabled</Box>
                  {(meta?.regions || []).join(', ') || 'none'}
                </Box>
                <Box>
                  <Box variant="awsui-key-label">Regions known</Box>
                  {(meta?.all_regions || []).length}
                </Box>
              </SpaceBetween>
            </Container>

            <Container header={<Header variant="h3">Reading next</Header>}>
              <SpaceBetween size="xs">
                <Box>
                  <a href="https://mathewmusango.github.io/emuplane/docs/" target="_blank" rel="noreferrer">
                    Documentation
                  </a>
                </Box>
                <Box>
                  <a href="https://mathewmusango.github.io/emuplane/docs/reference/limits/" target="_blank" rel="noreferrer">
                    Limits
                  </a>
                </Box>
                <Box>
                  <a href="https://github.com/mathewmusango/emuplane/releases" target="_blank" rel="noreferrer">
                    Release notes
                  </a>
                </Box>
              </SpaceBetween>
            </Container>

            <Container header={<Header variant="h3">Endpoints</Header>}>
              <SpaceBetween size="xs">
                <Box>
                  <Box variant="awsui-key-label">Console</Box>
                  <code>{meta?.console}</code>
                </Box>
                <Box>
                  <Box variant="awsui-key-label">Emulator gateway</Box>
                  <code>{meta?.gateway}</code>
                </Box>
                <Box>
                  <Box variant="awsui-key-label">API</Box>
                  {meta?.api_version || 'v1'}
                </Box>
              </SpaceBetween>
            </Container>
          </ColumnLayout>
        </SpaceBetween>
      </ContentLayout>
    </Shell>
  )
}
