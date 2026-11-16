import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import Checkbox from '@cloudscape-design/components/checkbox'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import FileUpload from '@cloudscape-design/components/file-upload'
import Header from '@cloudscape-design/components/header'
import Input from '@cloudscape-design/components/input'
import Modal from '@cloudscape-design/components/modal'
import RadioGroup from '@cloudscape-design/components/radio-group'
import Select from '@cloudscape-design/components/select'
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

// One file per request, the same ceiling the control enforces.
const MAX_UPLOAD = 25 * 1024 * 1024

const dash = '\u2014'

// The one document that is a listing rather than a setting says so, since it sits
// in a section named for configuration.
const DOCUMENT_LABELS = { versions: 'versions (ListObjectVersions)' }

// The console's three encryption choices, as the create page offers them.
const ENCRYPTION = [
  ['AES256', 'Amazon S3 managed keys (SSE-S3)'],
  ['aws:kms', 'AWS Key Management Service keys (SSE-KMS)'],
  ['aws:kms:dsse', 'Dual-layer server-side encryption (DSSE-KMS)'],
]

// The bucket picker's options for a copy: every bucket the account has, each
// with the region it lives in, because a copy is addressed to the destination.

const formatSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

export default function BucketDetail() {
  const { name = '' } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const { account, region: sessionRegion } = useSession()

  // The URL names a region, but a bookmarked or pasted link may be missing it or
  // carrying the bar's region for a bucket that lives elsewhere. HeadBucket
  // answers where the bucket really is, and the page reads nothing until it does.
  const requested = searchParams.get('region') || sessionRegion
  const [bucketRegion, setBucketRegion] = useState('')
  const [headMissing, setHeadMissing] = useState(false)
  const region = bucketRegion || requested
  const created = location.state?.created || ''

  const [objects, setObjects] = useState([])
  const [prefix, setPrefix] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [newBody, setNewBody] = useState('')
  const [file, setFile] = useState([])
  const [uploadError, setUploadError] = useState('')
  const [saving, setSaving] = useState(false)
  const [versioningEdit, setVersioningEdit] = useState(null)
  const [encryptionEdit, setEncryptionEdit] = useState(null)
  const [bucketKeyEdit, setBucketKeyEdit] = useState(false)
  const [accessEdit, setAccessEdit] = useState(null)
  const [settings, setSettings] = useState(null)
  const [settingsError, setSettingsError] = useState('')
  const [documents, setDocuments] = useState({})
  const [documentsError, setDocumentsError] = useState('')
  const [objectView, setObjectView] = useState(null)
  const [objectError, setObjectError] = useState('')
  const [deletingObject, setDeletingObject] = useState(null)
  const [copying, setCopying] = useState(null)
  const [copyTo, setCopyTo] = useState(null)
  const [copyKey, setCopyKey] = useState('')
  const [copyError, setCopyError] = useState('')
  const [allBuckets, setAllBuckets] = useState([])

  useEffect(() => {
    if (!account || !name) return undefined
    let live = true
    api
      .headBucket(account, requested, name)
      .then((answer) => {
        if (!live) return
        if (!answer?.ok) {
          setBucketRegion(requested)
          return
        }
        setHeadMissing(!answer.exists)
        setBucketRegion(answer.region || requested)
      })
      .catch(() => {
        // A head that fails leaves the page where the URL pointed: the list below
        // reports the real problem.
        if (live) setBucketRegion(requested)
      })
    return () => {
      live = false
    }
  }, [account, requested, name])

  // The address bar follows the bucket, so the link is right the next time.
  useEffect(() => {
    if (!bucketRegion || bucketRegion === requested) return
    setSearchParams({ region: bucketRegion }, { replace: true })
  }, [bucketRegion, requested, setSearchParams])

  const loadObjects = useCallback(async () => {
    if (!account || !bucketRegion || headMissing) return
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
  }, [account, region, name, prefix, bucketRegion, headMissing])

  useEffect(() => {
    loadObjects()
  }, [loadObjects])

  useEffect(() => {
    if (!account || !bucketRegion || headMissing) return undefined
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
  }, [account, region, name, bucketRegion, headMissing])

  const upload = async () => {
    setSaving(true)
    setUploadError('')
    try {
      const chosen = file[0]
      if (chosen) {
        if (chosen.size > MAX_UPLOAD) {
          throw new Error(
            `${chosen.name} is ${formatSize(chosen.size)}; this console uploads up to ${formatSize(MAX_UPLOAD)} in one request.`,
          )
        }
        // The file's bytes are the body, and its type is stored with it, so a PNG
        // comes back as a PNG rather than as text.
        await api.uploadObjectFile({
          account,
          region,
          bucket: name,
          key: newKey.trim() || chosen.name,
          file: chosen,
        })
      } else {
        await api.putObject({ account, region, bucket: name, key: newKey, body: newBody })
      }
      setUploading(false)
      setNewKey('')
      setNewBody('')
      setFile([])
      await loadObjects()
    } catch (err) {
      setUploadError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const openObject = async (key) => {
    setObjectError('')
    try {
      const answer = await api.readObject(account, region, name, key)
      setObjectView(answer)
    } catch (err) {
      setObjectView(null)
      setObjectError(err.message)
    }
  }

  // The eight documents the bucket page displays: each is its own GET, and a
  // failure is an error rather than "nothing configured".
  useEffect(() => {
    if (!account || !bucketRegion || headMissing) return undefined
    let live = true
    api
      .bucketDocuments(account, region, name)
      .then((answer) => {
        if (!live) return
        setDocuments(answer.documents || {})
        setDocumentsError('')
      })
      .catch((err) => {
        if (!live) return
        setDocuments({})
        setDocumentsError(err.message)
      })
    return () => {
      live = false
    }
  }, [account, region, name, bucketRegion, headMissing])

  // The copy destination list is read when the copy form opens, not on every view
  // of the bucket page.
  useEffect(() => {
    if (!copying || !account) return undefined
    let live = true
    api
      .browse(account, 'all', 's3')
      .then((payload) => {
        if (live) setAllBuckets(payload.resources || [])
      })
      .catch(() => {
        if (live) setAllBuckets([])
      })
    return () => {
      live = false
    }
  }, [copying, account])

  const copyObject = async () => {
    if (!copying || !copyTo) return
    setSaving(true)
    setCopyError('')
    try {
      const answer = await api.copyObject({
        account,
        region,
        bucket: name,
        key: copying,
        destination: copyTo.value,
        destination_region: copyTo.region || region,
        destination_key: copyKey.trim() || copying,
      })
      if (!answer.ok) throw new Error(answer.error || 'Could not copy the object.')
      setCopying(null)
      await loadObjects()
    } catch (err) {
      setCopyError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const removeObject = async () => {
    if (!deletingObject) return
    setSaving(true)
    try {
      const answer = await api.exec({
        account,
        region,
        service: 's3',
        operation: 'delete-object',
        params: { Bucket: name, Key: deletingObject },
      })
      if (!answer.ok) throw new Error(answer.error || 'Could not delete the object.')
      setDeletingObject(null)
      await loadObjects()
    } catch (err) {
      setError(err.message)
      setDeletingObject(null)
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
                ariaLabel="Edit bucket versioning"
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
        {encryptionEdit === null ? (
          <SpaceBetween size="s">
            <Box>
              <Box variant="awsui-key-label">Encryption type</Box>
              {settings?.encryption || 'AES256'}
              {settings?.bucket_key ? ' · bucket key enabled' : ''}
            </Box>
            <Box>
              <Button
                ariaLabel="Edit default encryption"
                onClick={() => {
                  setEncryptionEdit(settings?.encryption || 'AES256')
                  setBucketKeyEdit(Boolean(settings?.bucket_key))
                }}
              >
                Edit
              </Button>
            </Box>
          </SpaceBetween>
        ) : (
          <SpaceBetween size="m">
            <RadioGroup
              value={encryptionEdit}
              onChange={({ detail }) => setEncryptionEdit(detail.value)}
              items={ENCRYPTION.map(([value, label]) => ({ value, label }))}
            />
            <Checkbox
              checked={bucketKeyEdit}
              disabled={!encryptionEdit.startsWith('aws:kms')}
              onChange={({ detail }) => setBucketKeyEdit(detail.checked)}
            >
              Bucket Key
            </Checkbox>
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="primary"
                loading={saving}
                onClick={() =>
                  save({ encryption: encryptionEdit, bucket_key: bucketKeyEdit })
                }
              >
                Save
              </Button>
              <Button variant="link" onClick={() => setEncryptionEdit(null)}>
                Cancel
              </Button>
            </SpaceBetween>
          </SpaceBetween>
        )}
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
            description="What S3 answers for this bucket's subresources, exactly as it answers them. A subresource S3 reports as empty is not configured, and is not shown here."
          >
            Configuration documents
          </Header>
        }
      >
        <SpaceBetween size="s">
          {documentsError && (
            <Alert type="error" header="Could not read these documents">
              {documentsError}
            </Alert>
          )}
          {!documentsError &&
            (Object.entries(documents).filter(([, xml]) => xml).length === 0 ? (
              <Box color="text-body-secondary">
                Nothing configured beyond the settings above.
              </Box>
            ) : (
              Object.entries(documents)
                .filter(([, xml]) => xml)
                .map(([label, xml]) => (
                  <div key={label}>
                    <Box variant="awsui-key-label">{DOCUMENT_LABELS[label] || label}</Box>
                    <pre className="result-body">{xml}</pre>
                  </div>
                ))
            ))}
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
        {headMissing ? (
          <Alert type="error" header="This bucket does not exist">
            S3 answered that <strong>{name}</strong> is not there in{' '}
            {regionName(region)} <span className="mono">{region}</span>. The name may have
            been deleted, or it may belong to the wrong region.
          </Alert>
        ) : (
          <Tabs
            tabs={[
              { id: 'objects', label: 'Objects', content: objectsTab },
              { id: 'properties', label: 'Properties', content: propertiesTab },
              { id: 'permissions', label: 'Permissions', content: permissionsTab },
            ]}
          />
        )}
        <Modal
          visible={Boolean(objectView) || Boolean(objectError)}
          onDismiss={() => {
            setObjectView(null)
            setObjectError('')
          }}
          header={objectView ? objectView.key : 'Could not read this object'}
          size="large"
          footer={
            objectView ? (
              <Box float="right">
                <SpaceBetween direction="horizontal" size="xs">
                  {objectView.binary && (
                    <Button
                      href={api.objectDownloadUrl(account, region, name, objectView.key)}
                    >
                      Download
                    </Button>
                  )}
                  <Button
                    onClick={() => {
                      // One confirmation, then the list is the truth again.
                      setDeletingObject(objectView.key)
                      setObjectView(null)
                    }}
                  >
                    Delete
                  </Button>
                  <Button
                    onClick={() => {
                      setCopying(objectView.key)
                      setCopyKey(objectView.key)
                      setCopyError('')
                      setCopyTo({
                        label: `${name} · ${region}`,
                        value: name,
                        region,
                      })
                      setObjectView(null)
                    }}
                  >
                    Copy
                  </Button>
                </SpaceBetween>
              </Box>
            ) : undefined
          }
        >
          {objectError ? (
            <Alert type="error">{objectError}</Alert>
          ) : (
            <SpaceBetween size="m">
              {/* What only HeadObject knows: a GET's bytes carry none of it. */}
              <ColumnLayout columns={4} variant="text-grid">
                <div>
                  <Box variant="awsui-key-label">Size</Box>
                  {formatSize(objectView?.size)}
                </div>
                <div>
                  <Box variant="awsui-key-label">Type</Box>
                  <span className="mono">{objectView?.content_type}</span>
                </div>
                <div>
                  <Box variant="awsui-key-label">ETag</Box>
                  <span className="mono">{objectView?.etag || dash}</span>
                </div>
                <div>
                  <Box variant="awsui-key-label">Last modified</Box>
                  {objectView?.last_modified || dash}
                </div>
              </ColumnLayout>
              {objectView?.binary ? (
                <Alert type="info" header="This object is not text">
                  It is stored as <span className="mono">{objectView.content_type}</span>, so
                  the page offers it as a download rather than showing bytes that would not
                  mean anything.
                </Alert>
              ) : (
                <SpaceBetween size="xs">
                  <pre className="result-body">{objectView?.body}</pre>
                  {objectView?.truncated && (
                    <Box color="text-body-secondary" fontSize="body-s">
                      Showing the first 20 000 characters. Download to see all of it.
                    </Box>
                  )}
                </SpaceBetween>
              )}
            </SpaceBetween>
          )}
        </Modal>
        <Modal
          visible={Boolean(copying)}
          onDismiss={() => setCopying(null)}
          header="Copy object"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setCopying(null)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  loading={saving}
                  disabled={!copyTo || !copyKey.trim()}
                  onClick={copyObject}
                >
                  Copy
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="m">
            {copyError && <Alert type="error">{copyError}</Alert>}
            <Box>
              Copying <span className="mono">{copying}</span> from <strong>{name}</strong>.
            </Box>
            <Box>
              <Box variant="awsui-key-label">Destination bucket</Box>
              <Select
                selectedOption={copyTo}
                onChange={({ detail }) => setCopyTo(detail.selectedOption)}
                options={allBuckets.map((row) => ({
                  label: `${row.name} · ${row.region || region}`,
                  value: row.name,
                  region: row.region || region,
                }))}
                placeholder="Choose bucket"
                empty="No buckets in this account"
              />
            </Box>
            <Box>
              <Box variant="awsui-key-label">Destination key</Box>
              <Input
                value={copyKey}
                onChange={({ detail }) => setCopyKey(detail.value)}
                placeholder={`copies/${copying || ''}`}
              />
            </Box>
          </SpaceBetween>
        </Modal>
        <Modal
          visible={Boolean(deletingObject)}
          onDismiss={() => setDeletingObject(null)}
          header="Delete object"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setDeletingObject(null)}>
                  Cancel
                </Button>
                <Button variant="primary" loading={saving} onClick={removeObject}>
                  Delete
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <Box>
            Delete <strong>{deletingObject}</strong> from <strong>{name}</strong>? S3 keeps no
            undo for a plain delete.
          </Box>
        </Modal>
        <Modal
          visible={uploading}
          onDismiss={() => {
            setUploading(false)
            setUploadError('')
            setFile([])
          }}
          header="Upload object"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button
                  variant="link"
                  onClick={() => {
                    setUploading(false)
                    setFile([])
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  loading={saving}
                  disabled={!file.length && !(newKey.trim() && newBody)}
                  onClick={upload}
                >
                  Upload
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="m">
            {uploadError && <Alert type="error">{uploadError}</Alert>}
            <FileUpload
              value={file}
              onChange={({ detail }) => {
                setFile(detail.value)
                setUploadError('')
                const chosen = detail.value[0]
                // The destination key follows the file name until the operator
                // types one, which is what the console does.
                if (chosen && (!newKey.trim() || newKey === file[0]?.name)) {
                  setNewKey(chosen.name)
                }
              }}
              accept="*/*"
              showFileSize
              showFileLastModified
              constraintText={`One file, up to ${formatSize(MAX_UPLOAD)}. The file's own type is stored with it.`}
              i18nStrings={{
                uploadButtonText: () => 'Choose file',
                dropzoneText: () => 'Drop a file here, or choose one',
                removeFileAriaLabel: (index) => `Remove file ${index + 1}`,
                limitShowFewer: 'Show fewer files',
                limitShowMore: 'Show more files',
                errorIconAriaLabel: 'Error',
                warningIconAriaLabel: 'Warning',
              }}
            />
            <Box>
              <Box variant="awsui-key-label">Object key</Box>
              <Input
                value={newKey}
                onChange={({ detail }) => setNewKey(detail.value)}
                placeholder="reports/2026.csv"
              />
            </Box>
            {!file.length && (
              <Box>
                <Box variant="awsui-key-label">Or type the contents</Box>
                <Textarea
                  value={newBody}
                  onChange={({ detail }) => setNewBody(detail.value)}
                  placeholder="contents"
                />
              </Box>
            )}
          </SpaceBetween>
        </Modal>
      </ContentLayout>
    </Shell>
  )
}
