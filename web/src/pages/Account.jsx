
import { useEffect, useState } from 'react'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import CopyToClipboard from '@cloudscape-design/components/copy-to-clipboard'
import Header from '@cloudscape-design/components/header'
import ExpandableSection from '@cloudscape-design/components/expandable-section'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import Table from '@cloudscape-design/components/table'
import Toggle from '@cloudscape-design/components/toggle'
import { api } from '../api'
import { useSession } from '../context'
import { Shell } from '../components/Shell'

export default function Account() {
  const { meta, me, account, refresh, region } = useSession()
  const [error, setError] = useState('')
  const [savingRegion, setSavingRegion] = useState('')
  const [settings, setSettings] = useState(null)
  const [savingSignup, setSavingSignup] = useState(false)

  const [accountFacts, setAccountFacts] = useState(null)
  const [contactFacts, setContactFacts] = useState(null)
  const [regionsKnown, setRegionsKnown] = useState(null)
  const [signedRegionStatus, setSignedRegionStatus] = useState('')

  const homeRegion = region || (meta?.regions || [])[0] || 'us-east-1'
  useEffect(() => {
    if (!account) return undefined
    let cancelled = false
    const ask = (operation, params = {}) =>
      api.exec({ account, region: homeRegion, service: 'account', operation, params })
    const read = (result) => {
      try {
        return result && result.ok ? JSON.parse(result.body) : null
      } catch {
        return null
      }
    }
    Promise.all([
      ask('get-account-information').catch(() => null),
      ask('get-contact-information').catch(() => null),
      ask('list-regions').catch(() => null),
      ask('get-region-opt-status', { RegionName: homeRegion }).catch(() => null),
    ]).then(([info, contact, regions, status]) => {
      if (cancelled) return
      setAccountFacts(read(info))
      setContactFacts(read(contact)?.ContactInformation || null)
      const list = read(regions)?.Regions || null
      setRegionsKnown(list ? list.length : null)
      setSignedRegionStatus(read(status)?.RegionOptStatus || '')
    })
    return () => {
      cancelled = true
    }
  }, [account, homeRegion])

  useEffect(() => {
    if (!meta?.platform_admin) return
    let cancelled = false
    api
      .settings()
      .then((payload) => {
        if (!cancelled) setSettings(payload)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [meta?.platform_admin])

  const toggleSignup = async (enabled) => {
    setSavingSignup(true)
    setError('')
    try {
      const payload = await api.setSettings({ signup_enabled: enabled })
      setSettings(payload)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingSignup(false)
    }
  }

  const enabledRegions = meta?.regions || []

  const toggleRegion = async (name, enabled) => {
    setSavingRegion(name)
    setError('')
    try {
      await api.setRegion(account, name, enabled)
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingRegion('')
    }
  }

  const regionRows = (meta?.all_regions || []).map((name) => ({
    name,
    enabled: enabledRegions.includes(name),
    automatic: (meta?.auto_regions || []).includes(name),
    locked: name === 'us-east-1',
  }))

  return (
    <Shell
      activeHref="/Account"
      breadcrumbs={[
        { text: 'Billing and Cost Management' },
        { text: 'Account', href: '/Account' },
      ]}
    >
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="The account and its contact details, this session, sign-up and the regions it can use."
          >
            Account
          </Header>
        }
      >
        <SpaceBetween size="l">
          {error && <Alert type="error">{error}</Alert>}

          <Container header={<Header variant="h2">Session</Header>}>
            <ColumnLayout columns={3} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Signed in as</Box>
                <Box>{me?.user || '—'}</Box>
              </div>
              <div>
                <Box variant="awsui-key-label">Account</Box>
                <CopyToClipboard
                  variant="inline"
                  textToCopy={account || ''}
                  copyButtonAriaLabel="Copy account ID"
                  copySuccessText="Account ID copied"
                  copyErrorText="Could not copy the account ID"
                  wrapText={false}
                />
              </div>
              <div>
                <Box variant="awsui-key-label">Role</Box>
                <Box>{me?.role || '—'}</Box>
              </div>
            </ColumnLayout>
          </Container>

          <ColumnLayout columns={2}>
            <Container header={<Header variant="h2">Account details</Header>}>
              <ColumnLayout columns={2} variant="text-grid">
                <div>
                  <Box variant="awsui-key-label">Name</Box>
                  <Box>{accountFacts?.AccountName || '—'}</Box>
                </div>
                <div>
                  <Box variant="awsui-key-label">Account ID</Box>
                  <CopyToClipboard
                    variant="inline"
                    textToCopy={accountFacts?.AccountId || account || ''}
                    copyButtonAriaLabel="Copy account ID"
                    copySuccessText="Account ID copied"
                    copyErrorText="Could not copy the account ID"
                    wrapText={false}
                  />
                </div>
                <div>
                  <Box variant="awsui-key-label">ARN</Box>
                  <CopyToClipboard
                    variant="inline"
                    textToCopy={
                      accountFacts?.AccountId ? `arn:aws:account::${accountFacts.AccountId}:account` : ''
                    }
                    copyButtonAriaLabel="Copy account ARN"
                    copySuccessText="Account ARN copied"
                    copyErrorText="Could not copy the account ARN"
                    wrapText={false}
                  />
                </div>
                <div>
                  <Box variant="awsui-key-label">Created</Box>
                  <Box>{accountFacts?.AccountCreatedDate || '—'}</Box>
                </div>
                <div>
                  <Box variant="awsui-key-label">State</Box>
                  <StatusIndicator type="success">
                    {accountFacts?.AccountState || 'unknown'}
                  </StatusIndicator>
                </div>
              </ColumnLayout>
            </Container>

            <Container
              header={
                <Header variant="h2" description="Reported by the emulator; read-only here.">
                  Contact information
                </Header>
              }
            >
              <ColumnLayout columns={1} variant="text-grid">
                <div>
                  <Box variant="awsui-key-label">Full name</Box>
                  <Box>{contactFacts?.FullName || '—'}</Box>
                </div>
                <div>
                  <Box variant="awsui-key-label">Phone number</Box>
                  <Box>{contactFacts?.PhoneNumber || '—'}</Box>
                </div>
                <div>
                  <Box variant="awsui-key-label">Address</Box>
                  <Box>
                    {[
                      contactFacts?.AddressLine1,
                      contactFacts?.City,
                      contactFacts?.PostalCode,
                      contactFacts?.CountryCode,
                    ]
                      .filter(Boolean)
                      .join(', ') || '—'}
                  </Box>
                </div>
              </ColumnLayout>
            </Container>
          </ColumnLayout>

          <Container header={<Header variant="h2">AWS Regions</Header>}>
            <ColumnLayout columns={2} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Regions the emulator knows</Box>
                <Box>{regionsKnown === null ? '—' : regionsKnown}</Box>
              </div>
              <div>
                <Box variant="awsui-key-label">{homeRegion}</Box>
                <Box>{signedRegionStatus || '—'}</Box>
              </div>
            </ColumnLayout>
          </Container>

          {meta?.platform_admin && (
            <Container
              header={
                <Header
                  variant="h2"
                  description="Global admins can turn self-service sign-up on or off. The first account created always becomes a global admin."
                >
                  Sign-up
                </Header>
              }
            >
              <Toggle
                checked={Boolean(settings?.signup_enabled)}
                disabled={savingSignup || settings === null}
                onChange={({ detail }) => toggleSignup(detail.checked)}
              >
                {settings?.signup_enabled ? 'Enabled' : 'Disabled'}
              </Toggle>
            </Container>
          )}

          <ExpandableSection
            headerText={`Supported regions (${regionRows.filter((row) => row.enabled).length} enabled)`}
            defaultExpanded={false}
          >
            <Table
              items={regionRows}
              trackBy="name"
              columnDefinitions={[
                {
                  id: 'name',
                  header: 'Region',
                  cell: (item) => (
                    <SpaceBetween direction="horizontal" size="xs">
                      <span className="mono">{item.name}</span>
                      {item.automatic && (
                        <Box color="text-body-secondary" fontSize="body-s">
                          enabled on first use
                        </Box>
                      )}
                    </SpaceBetween>
                  ),
                  sortingField: 'name',
                },
                {
                  id: 'enabled',
                  header: 'Enabled',
                  cell: (item) => (
                    <Toggle
                      checked={item.enabled}
                      disabled={item.locked || savingRegion === item.name}
                      onChange={({ detail }) => toggleRegion(item.name, detail.checked)}
                    >
                      {item.enabled ? 'Enabled' : 'Disabled'}
                    </Toggle>
                  ),
                  width: 160,
                },
              ]}
            />
          </ExpandableSection>

        </SpaceBetween>
      </ContentLayout>
    </Shell>
  )
}
