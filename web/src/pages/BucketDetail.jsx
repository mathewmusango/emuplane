import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Header from '@cloudscape-design/components/header'
import Input from '@cloudscape-design/components/input'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import Table from '@cloudscape-design/components/table'
import Tabs from '@cloudscape-design/components/tabs'
import { api } from '../api'
import { useSession } from '../context'
import { regionName } from '../regionNames'
import { Shell } from '../components/Shell'

// One bucket, the way the console shows it: a page of its own with the tabs this
// instance can actually back. Metrics, Management, File systems, Access Points and
// Metadata are not tabs here — the console has nothing to put in them.
export default function BucketDetail() {
  const { name = '' } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const { account, region: sessionRegion } = useSession()

  const region = searchParams.get('region') || sessionRegion
  const created = location.state?.created || ''

  const [objects, setObjects] = useState([])
  const [prefix, setPrefix] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [settings, setSettings] = useState(null)
  const [settingsError, setSettingsError] = useState('')

  const loadObjects = useCallback(async () => {
    if (!account) return
    setLoading(true)
    try {
      const payload = await api.s3Objects(account, region, name, prefix)
      setObjects(payload.objects || [])
      setError('')
    } catch (err) {
      setObjects([])
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [account, region, name, prefix])

  useEffect(() => {
    loadObjects()
  }, [loadObjects])

  useEffect(() => {
    if (!account) return undefined
    let live = true
    api
      .bucketSettings(account, region, name)
      .then((answer) => {
        if (!live) return
        setSettings(answer.settings || null)
        setSettingsError('')
      })
      .catch((err) => {
        if (live) setSettingsError(err.message)
      })
    return () => {
      live = false
    }
  }, [account, region, name])

  const kind = (key) => (key.endsWith('/') ? 'Folder' : 'Object')

  const objectsTab = (
    <Container
      header={
        <Header
          variant="h2"
          counter={`(${objects.length})`}
          description="Objects are the fundamental entities stored in Amazon S3."
          actions={
            <Button iconName="refresh" ariaLabel="Refresh" onClick={loadObjects} />
          }
        >
          Objects
        </Header>
      }
    >
      <SpaceBetween size="m">
        {error && (
          <Alert type="error" header="Could not read this bucket">
            {error}
          </Alert>
        )}
        <div style={{ maxWidth: 420 }}>
          <Input
            value={prefix}
            onChange={({ detail }) => setPrefix(detail.value)}
            placeholder="Find objects by prefix"
            ariaLabel="Find objects by prefix"
            type="search"
          />
        </div>
        <Table
          items={objects}
          loading={loading}
          loadingText="Reading objects"
          trackBy="key"
          columnDefinitions={[
            {
              id: 'key',
              header: 'Name',
              cell: (item) => <span className="mono">{item.key}</span>,
              sortingField: 'key',
            },
            { id: 'type', header: 'Type', cell: (item) => kind(item.key), width: 110 },
            {
              id: 'modified',
              header: 'Last modified',
              cell: (item) => item.modified,
              width: 230,
            },
            { id: 'size', header: 'Size', cell: (item) => item.size, width: 110 },
          ]}
          empty={
            <Box textAlign="center">
              <SpaceBetween size="xs">
                <Box fontSize="heading-s">No objects</Box>
                <Box color="text-body-secondary">
                  You don&apos;t have any objects in this bucket.
                </Box>
              </SpaceBetween>
            </Box>
          }
        />
      </SpaceBetween>
    </Container>
  )

  const propertiesTab = (
    <SpaceBetween size="l">
      {settingsError && (
        <Alert type="error" header="Could not read this bucket's properties">
          {settingsError}
        </Alert>
      )}
      <Container header={<Header variant="h2">Bucket overview</Header>}>
        <SpaceBetween size="xs">
          <Box>
            <Box variant="awsui-key-label">AWS Region</Box>
            {regionName(region)} <span className="mono">{region}</span>
          </Box>
          <Box>
            <Box variant="awsui-key-label">Amazon Resource Name (ARN)</Box>
            <span className="mono">{`arn:aws:s3:::${name}`}</span>
          </Box>
          {created && (
            <Box>
              <Box variant="awsui-key-label">Creation date</Box>
              {created}
            </Box>
          )}
        </SpaceBetween>
      </Container>

      <Container header={<Header variant="h2">Bucket Versioning</Header>}>
        <Box>
          <Box variant="awsui-key-label">Bucket Versioning</Box>
          <StatusIndicator type={settings?.versioning ? 'success' : 'stopped'}>
            {settings?.versioning ? 'Enabled' : 'Disabled'}
          </StatusIndicator>
        </Box>
      </Container>

      <Container header={<Header variant="h2">Default encryption</Header>}>
        <Box>
          <Box variant="awsui-key-label">Encryption type</Box>
          {settings?.encryption || 'AES256'}
          {settings?.bucket_key ? ' · bucket key enabled' : ''}
        </Box>
      </Container>

      <Container
        header={
          <Header variant="h2" counter={`(${settings?.tags?.length || 0})`}>
            Tags
          </Header>
        }
      >
        {(settings?.tags || []).length === 0 ? (
          <Box color="text-body-secondary">No tags associated with this bucket.</Box>
        ) : (
          <Table
            items={settings.tags}
            trackBy="Key"
            columnDefinitions={[
              { id: 'key', header: 'Key', cell: (item) => item.Key },
              { id: 'value', header: 'Value', cell: (item) => item.Value },
            ]}
          />
        )}
      </Container>
    </SpaceBetween>
  )

  const permissionsTab = (
    <SpaceBetween size="l">
      <Container
        header={
          <Header
            variant="h2"
            description="Public access is granted to buckets and objects through access control lists (ACLs), bucket policies, access point policies, or all."
          >
            Block public access (bucket settings)
          </Header>
        }
      >
        <SpaceBetween size="xs">
          <Box>
            <Box variant="awsui-key-label">Block all public access</Box>
            <StatusIndicator
              type={
                Object.values(settings?.block_public_access || {}).every(Boolean)
                  ? 'success'
                  : 'warning'
              }
            >
              {Object.values(settings?.block_public_access || {}).every(Boolean)
                ? 'On'
                : 'Off'}
            </StatusIndicator>
          </Box>
          <Table
            items={Object.entries(settings?.block_public_access || {}).map(
              ([name_, value]) => ({ name: name_, value }),
            )}
            trackBy="name"
            columnDefinitions={[
              { id: 'name', header: 'Individual setting', cell: (item) => item.name },
              {
                id: 'value',
                header: 'State',
                cell: (item) => (item.value ? 'On' : 'Off'),
                width: 120,
              },
            ]}
            empty={<Box color="text-body-secondary">No configuration on this bucket.</Box>}
          />
        </SpaceBetween>
      </Container>

      <Alert type="info" header="Object Ownership">
        {settings?.ownership === 'BucketOwnerPreferred'
          ? 'ACLs enabled — bucket owner preferred'
          : 'ACLs disabled — bucket owner enforced'}
      </Alert>
    </SpaceBetween>
  )

  return (
    <Shell
      breadcrumbs={[
        { text: 'Amazon S3', href: '/s3/home' },
        { text: 'Buckets', href: '/s3/home' },
        { text: name },
      ]}
    >
      <ContentLayout header={<Header variant="h1">{name}</Header>}>
        <Tabs
          tabs={[
            { id: 'objects', label: 'Objects', content: objectsTab },
            { id: 'properties', label: 'Properties', content: propertiesTab },
            { id: 'permissions', label: 'Permissions', content: permissionsTab },
          ]}
        />
      </ContentLayout>
    </Shell>
  )
}
