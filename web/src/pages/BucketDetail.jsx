import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Header from '@cloudscape-design/components/header'
import Input from '@cloudscape-design/components/input'
import Modal from '@cloudscape-design/components/modal'
import RadioGroup from '@cloudscape-design/components/radio-group'
import Textarea from '@cloudscape-design/components/textarea'
import Toggle from '@cloudscape-design/components/toggle'
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
  const [uploading, setUploading] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [newBody, setNewBody] = useState('')
  const [saving, setSaving] = useState(false)
  const [versioningEdit, setVersioningEdit] = useState(null)
  const [accessEdit, setAccessEdit] = useState(null)
  const [settings, setSettings] = useState(null)
  const [settingsError, setSettingsError] = useState('')
  const [documents, setDocuments] = useState({})
  const [objectView, setObjectView] = useState(null)
  const [objectError, setObjectError] = useState('')

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

  const upload = async () => {
    setSaving(true)
    try {
      await api.putObject({ account, region, bucket: name, key: newKey, body: newBody })
      setUploading(false)
      setNewKey('')
      setNewBody('')
      await loadObjects()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const save = async (change) => {
    setSaving(true)
    try {
      await api.editBucketSettings({ account, region, bucket: name, ...change })
      const answer = await api.bucketSettings(account, region, name)
      setSettings(answer.settings || null)
      setVersioningEdit(null)
      setAccessEdit(null)
    } catch (err) {
      setSettingsError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const kind = (key) => (key.endsWith('/') ? 'Folder' : 'Object')

  const objectsTab = (
    <Container
      header={
        <Header
          variant="h2"
          counter={`(${objects.length})`}
          description="Objects are the fundamental entities stored in Amazon S3."
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button iconName="refresh" ariaLabel="Refresh" onClick={loadObjects} />
              <Button variant="primary" onClick={() => setUploading(true)}>
                Upload
              </Button>
            </SpaceBetween>
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
              cell: (item) => (
                <Button variant="inline-link" onClick={() => openObject(item.key)}>
                  {item.key}
                </Button>
              ),
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
          <SpaceBetween size="s">
            <StatusIndicator type={settings?.versioning ? 'success' : 'stopped'}>
              {settings?.versioning ? 'Enabled' : 'Disabled'}
            </StatusIndicator>
            {versioningEdit === null ? (
              <Button
                onClick={() => setVersioningEdit(Boolean(settings?.versioning))}
              >
                Edit
              </Button>
            ) : (
              <SpaceBetween direction="horizontal" size="xs">
                <RadioGroup
                  value={versioningEdit ? 'enable' : 'disable'}
                  onChange={({ detail }) => setVersioningEdit(detail.value === 'enable')}
                  items={[
                    { value: 'disable', label: 'Disable' },
                    { value: 'enable', label: 'Enable' },
                  ]}
                />
                <Button
                  variant="primary"
                  loading={saving}
                  onClick={() => save({ versioning: versioningEdit })}
                >
                  Save
                </Button>
              </SpaceBetween>
            )}
          </SpaceBetween>
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
      <Container
        header={
          <Header
            variant="h2"
            description="The configuration S3 holds for this bucket, exactly as it answers."
          >
            Configuration documents
          </Header>
        }
      >
        <SpaceBetween size="s">
          {Object.entries(documents).filter(([, xml]) => xml).length === 0 ? (
            <Box color="text-body-secondary">
              Nothing configured beyond the settings above.
            </Box>
          ) : (
            Object.entries(documents)
              .filter(([, xml]) => xml)
              .map(([label, xml]) => (
                <div key={label}>
                  <Box variant="awsui-key-label">{label}</Box>
                  <pre className="result-body">{xml}</pre>
                </div>
              ))
          )}
        </SpaceBetween>
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
          <SpaceBetween size="s">
            {Object.entries(accessEdit ?? settings?.block_public_access ?? {}).map(
              ([setting, value]) => (
                <Toggle
                  key={setting}
                  checked={Boolean(value)}
                  onChange={({ detail }) =>
                    setAccessEdit({
                      ...(accessEdit ?? settings?.block_public_access ?? {}),
                      [setting]: detail.checked,
                    })
                  }
                >
                  {setting}
                </Toggle>
              ),
            )}
            <Button
              variant="primary"
              loading={saving}
              disabled={accessEdit === null}
              onClick={() => save({ block_public_access: accessEdit })}
            >
              Save
            </Button>
          </SpaceBetween>
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
        <Modal
          visible={Boolean(objectView) || Boolean(objectError)}
          onDismiss={() => {
            setObjectView(null)
            setObjectError('')
          }}
          header={objectView ? objectView.key : 'Could not read this object'}
          size="large"
        >
          {objectError ? (
            <Alert type="error">{objectError}</Alert>
          ) : (
            <pre className="result-body">{objectView?.body}</pre>
          )}
        </Modal>
        <Modal
          visible={uploading}
          onDismiss={() => setUploading(false)}
          header="Upload object"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setUploading(false)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  loading={saving}
                  disabled={!newKey.trim()}
                  onClick={upload}
                >
                  Upload
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="m">
            <Box>
              <Box variant="awsui-key-label">Object key</Box>
              <Input
                value={newKey}
                onChange={({ detail }) => setNewKey(detail.value)}
                placeholder="reports/2026.csv"
              />
            </Box>
            <Box>
              <Box variant="awsui-key-label">Content</Box>
              <Textarea
                value={newBody}
                onChange={({ detail }) => setNewBody(detail.value)}
                placeholder="contents"
              />
            </Box>
          </SpaceBetween>
        </Modal>
      </ContentLayout>
    </Shell>
  )
}
