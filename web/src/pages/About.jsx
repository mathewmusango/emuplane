import Box from '@cloudscape-design/components/box'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Header from '@cloudscape-design/components/header'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import { useSession } from '../context'
import { Shell } from '../components/Shell'


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
                  <StatusIndicator type="success">{meta?.emulator_version || 'unknown'}</StatusIndicator>
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
