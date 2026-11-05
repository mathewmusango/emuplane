import Box from '@cloudscape-design/components/box'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Header from '@cloudscape-design/components/header'
import Link from '@cloudscape-design/components/link'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import { useSession } from '../context'
import { Shell } from '../components/Shell'

const LINKS = [
  { label: 'MiniStack documentation', url: 'https://ministack.org/docs/' },
  { label: 'Multi-tenancy (accounts and regions)', url: 'https://ministack.org/docs/multi-tenancy' },
  { label: 'MiniStack on GitHub', url: 'https://github.com/ministackorg/ministack' },
  { label: 'StackPort (UI inspiration)', url: 'https://github.com/DaviReisVieira/stackport' },
]

export default function About() {
  const { meta, me } = useSession()

  return (
    <Shell activeHref="/about" breadcrumbs={[{ text: 'About', href: '/about' }]}>
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="A private, prod-shaped AWS replica running on one host."
          >
            About MiniStack
          </Header>
        }
      >
        <SpaceBetween size="l">
          <ColumnLayout columns={3}>
            <Container header={<Header variant="h3">This instance</Header>}>
              <SpaceBetween size="xs">
                <Box>
                  <Box variant="awsui-key-label">Emulator</Box>
                  <StatusIndicator type="success">{meta?.version || 'unknown'}</StatusIndicator>
                </Box>
                <Box>
                  <Box variant="awsui-key-label">Mode</Box>
                  —
                </Box>
                <Box>
                  <Box variant="awsui-key-label">Login</Box>
                  {meta?.login || 'local'}
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
                {meta?.platform_admin && (
                  <Box>
                    <Box variant="awsui-key-label">Global admins</Box>
                    {meta?.global_admins ??
                      (meta?.accounts || []).filter((item) => item.global_admin).length}
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

            <Container header={<Header variant="h3">Endpoints</Header>}>
              <SpaceBetween size="xs">
                <Box>
                  <Box variant="awsui-key-label">Console</Box>
                  <code>{meta?.console}</code>
                </Box>
                <Box>
                  <Box variant="awsui-key-label">AWS gateway</Box>
                  <code>{meta?.gateway}</code>
                </Box>
                <Box>
                  <Box variant="awsui-key-label">API</Box>
                  {meta?.api_version || 'v1'}
                </Box>
              </SpaceBetween>
            </Container>
          </ColumnLayout>

          <Container header={<Header variant="h2">References</Header>}>
            <SpaceBetween size="xs">
              {LINKS.map((link) => (
                <Link key={link.url} href={link.url} external>
                  {link.label}
                </Link>
              ))}
            </SpaceBetween>
          </Container>
        </SpaceBetween>
      </ContentLayout>
    </Shell>
  )
}
