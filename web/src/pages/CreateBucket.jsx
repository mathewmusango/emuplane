import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import Checkbox from '@cloudscape-design/components/checkbox'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import ExpandableSection from '@cloudscape-design/components/expandable-section'
import Form from '@cloudscape-design/components/form'
import FormField from '@cloudscape-design/components/form-field'
import Header from '@cloudscape-design/components/header'
import Input from '@cloudscape-design/components/input'
import RadioGroup from '@cloudscape-design/components/radio-group'
import Select from '@cloudscape-design/components/select'
import SpaceBetween from '@cloudscape-design/components/space-between'
import { api } from '../api'
import { useSession } from '../context'
import { regionName } from '../regionNames'
import { serviceLongName } from '../serviceLabels'
import { Shell } from '../components/Shell'

// Block Public Access: the four settings the console nests under one master
// checkbox, in its own wording.
const PUBLIC_ACCESS = [
  [
    'BlockPublicAcls',
    'Block public access to buckets and objects granted through new access control lists (ACLs)',
  ],
  [
    'IgnorePublicAcls',
    'Block public access to buckets and objects granted through any access control lists (ACLs)',
  ],
  [
    'BlockPublicPolicy',
    'Block public access to buckets and objects granted through new public bucket or access point policies',
  ],
  [
    'RestrictPublicBuckets',
    'Block public and cross-account access to buckets and objects through any public bucket or access point policies',
  ],
]

const ENCRYPTION = [
  ['AES256', 'Server-side encryption with Amazon S3 managed keys (SSE-S3)'],
  ['aws:kms', 'Server-side encryption with AWS Key Management Service keys (SSE-KMS)'],
  ['aws:kms:dsse', 'Dual-layer server-side encryption with AWS Key Management Service keys (DSSE-KMS)'],
]

const MAX_TAGS = 50

// S3's naming rules, so the field answers before the round trip.
const NAME_RE = /^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/
const IP_RE = /^\d{1,3}(\.\d{1,3}){3}$/

const nameProblem = (name, suffix = '') => {
  if (!name) return 'A bucket name is required.'
  if (!NAME_RE.test(name) || name.includes('..') || IP_RE.test(name)) {
    return 'Use 3-63 lowercase letters, digits, dots or hyphens, starting and ending with a letter or digit.'
  }
  if (name.length + suffix.length > 63) {
    return `The namespace suffix takes ${suffix.length} characters, so the name is at most ${63 - suffix.length}.`
  }
  return ''
}

const allPublic = (value) =>
  Object.fromEntries(PUBLIC_ACCESS.map(([field]) => [field, value]))

export default function CreateBucket() {
  const navigate = useNavigate()
  const { meta, account, region: sessionRegion, setRegion } = useSession()

  const regions = meta?.regions?.length ? meta.regions : [sessionRegion]
  const [region, setFormRegion] = useState(sessionRegion)
  const [name, setName] = useState('')
  const [nameError, setNameError] = useState('')
  const [namespace, setNamespace] = useState('global')
  const [ownership, setOwnership] = useState('BucketOwnerEnforced')
  const [publicAccess, setPublicAccess] = useState(allPublic(true))
  const [blockAll, setBlockAll] = useState(true)
  const [versioning, setVersioning] = useState('disable')
  const [tags, setTags] = useState([])
  const [encryption, setEncryption] = useState('AES256')
  const [bucketKey, setBucketKey] = useState('enable')
  const [objectLock, setObjectLock] = useState('disable')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const regionOptions = useMemo(
    () =>
      regions.map((code) => ({
        label: `${regionName(code)} ${code}`,
        value: code,
      })),
    [regions],
  )

  const backToBuckets = () => navigate(`/s3/home?region=${region}`)

  // The Account Regional namespace appends `<account>-<region>-an` to the name;
  // the backend appends it too, and that is the name the bucket gets.
  const suffix = namespace === 'regional' ? `.${account}-${region}-an` : ''

  const setPublicField = (field, value) => {
    const next = { ...publicAccess, [field]: value }
    setPublicAccess(next)
    setBlockAll(Object.values(next).every(Boolean))
  }

  const setAllPublic = (value) => {
    setBlockAll(value)
    setPublicAccess(allPublic(value))
  }

  const lockOn = objectLock === 'enable'
  // Object Lock only exists on a versioned bucket, and it turns versioning on
  // rather than offering a choice.
  const versioningEnabled = lockOn || versioning === 'enable'

  const addTag = () => setTags((current) => [...current, { Key: '', Value: '' }])
  const setTag = (index, field, value) =>
    setTags((current) =>
      current.map((tag, at) => (at === index ? { ...tag, [field]: value } : tag)),
    )
  const removeTag = (index) =>
    setTags((current) => current.filter((_, at) => at !== index))

  const submit = async () => {
    const problem = nameProblem(name.trim(), suffix)
    setNameError(problem)
    if (problem) return
    setBusy(true)
    setError('')
    try {
      const result = await api.createBucket({
        account,
        region,
        bucket: name.trim(),
        namespace,
        ownership,
        block_public_access: publicAccess,
        versioning: versioningEnabled,
        tags: tags.filter((tag) => tag.Key.trim()),
        encryption,
        bucket_key: bucketKey === 'enable',
        object_lock: lockOn,
      })
      if (!result?.ok) {
        setError(result?.error || 'Could not create the bucket.')
        return
      }
      // The page's region is where the bucket now lives, so the app follows it.
      setRegion(region)
      navigate(`/s3/home?region=${region}`, {
        state: { created: result.bucket || name.trim() },
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell
      breadcrumbs={[
        { text: serviceLongName('s3'), href: '/s3/home' },
        { text: 'Buckets', href: '/s3/home' },
        { text: 'Create bucket' },
      ]}
    >
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="Buckets are containers for data stored in S3."
          >
            Create bucket
          </Header>
        }
      >
        <Form
          actions={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={backToBuckets}>
                  Cancel
                </Button>
                <Button variant="primary" loading={busy} onClick={submit}>
                  Create bucket
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="l">
            {error && (
              <Alert type="error" header="Could not create the bucket">
                {error}
              </Alert>
            )}

            <Container header={<Header variant="h2">General configuration</Header>}>
              <SpaceBetween size="l">
                <FormField label="AWS Region">
                  <Select
                    selectedOption={
                      regionOptions.find((option) => option.value === region) || null
                    }
                    onChange={({ detail }) => detail.selectedOption?.value
                      && setFormRegion(detail.selectedOption.value)}
                    options={regionOptions}
                    ariaLabel="AWS Region"
                  />
                </FormField>

                <FormField
                  label="Bucket type"
                  description="General purpose buckets are the original S3 bucket type, and the only one this backend serves."
                >
                  <RadioGroup
                    value="general"
                    onChange={() => {}}
                    items={[
                      {
                        value: 'general',
                        label: 'General purpose',
                        description:
                          'Recommended for most use cases and access patterns. Allows a mix of storage classes that redundantly store objects across multiple Availability Zones.',
                      },
                      {
                        value: 'directory',
                        label: 'Directory',
                        description: 'Not available on this backend.',
                        disabled: true,
                      },
                    ]}
                  />
                </FormField>

                <FormField
                  label="Bucket namespace"
                  description="Choose the namespace where you want to create your bucket."
                >
                  <RadioGroup
                    value={namespace}
                    onChange={({ detail }) => setNamespace(detail.value)}
                    items={[
                      {
                        value: 'global',
                        label: 'Global namespace',
                        description:
                          'S3 creates general purpose buckets in the global namespace.',
                      },
                      {
                        value: 'regional',
                        label: 'Account Regional namespace (recommended)',
                        description: `The name carries this account and region — ${`.${account}-${region}-an`} — so it cannot collide with another account's bucket.`,
                      },
                    ]}
                  />
                </FormField>

                <FormField
                  label="Bucket name"
                  description="The name is the bucket's identity in the gateway, in the console and on the wire."
                  errorText={nameError}
                  constraintText={
                    suffix
                      ? `3-63 characters: lowercase letters, digits, periods and hyphens. The namespace adds ${suffix}, so the name itself is at most ${63 - suffix.length}.`
                      : '3-63 characters: lowercase letters, digits, periods and hyphens; must begin and end with a letter or number; unique in the global namespace.'
                  }
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ flex: 1 }}>
                      <Input
                        value={name}
                        onChange={({ detail }) => {
                          setName(detail.value)
                          setNameError('')
                        }}
                        placeholder="my-bucket"
                      />
                    </div>
                    {suffix && <Box variant="span" color="text-body-secondary">{suffix}</Box>}
                  </div>
                </FormField>
              </SpaceBetween>
            </Container>

            <Container
              header={
                <Header
                  variant="h2"
                  description="Control ownership of objects written to this bucket from other AWS accounts and the use of access control lists (ACLs). Object ownership determines who can specify access to objects."
                >
                  Object Ownership
                </Header>
              }
            >
              <SpaceBetween size="m">
                <RadioGroup
                  value={ownership}
                  onChange={({ detail }) => setOwnership(detail.value)}
                  items={[
                    {
                      value: 'BucketOwnerEnforced',
                      label: 'ACLs disabled (recommended)',
                      description:
                        'All objects in this bucket are owned by this account. Access to this bucket and its objects is specified using only policies.',
                    },
                    {
                      value: 'BucketOwnerPreferred',
                      label: 'ACLs enabled',
                      description:
                        'Objects in this bucket can be owned by other AWS accounts. Access to this bucket and its objects can be specified using ACLs.',
                    },
                  ]}
                />
                <Box>
                  <Box variant="awsui-key-label">Object Ownership</Box>
                  {ownership === 'BucketOwnerEnforced'
                    ? 'Bucket owner enforced'
                    : 'Bucket owner preferred'}
                </Box>
              </SpaceBetween>
            </Container>

            <Container
              header={
                <Header
                  variant="h2"
                  description="Public access is granted to buckets and objects through access control lists (ACLs), bucket policies, access point policies, or all. These settings apply only to this bucket and its access points."
                >
                  Block Public Access settings for this bucket
                </Header>
              }
            >
              <SpaceBetween size="m">
                <Checkbox
                  checked={blockAll}
                  onChange={({ detail }) => setAllPublic(detail.checked)}
                  description="Turning this setting on is the same as turning on all four settings below. Each of the following settings is independent of one another."
                >
                  Block all public access
                </Checkbox>
                <div style={{ marginLeft: 20 }}>
                  <SpaceBetween size="s">
                    {PUBLIC_ACCESS.map(([field, label]) => (
                      <Checkbox
                        key={field}
                        checked={Boolean(publicAccess[field])}
                        onChange={({ detail }) => setPublicField(field, detail.checked)}
                      >
                        {label}
                      </Checkbox>
                    ))}
                  </SpaceBetween>
                </div>
              </SpaceBetween>
            </Container>

            <Container
              header={
                <Header
                  variant="h2"
                  description="Versioning keeps multiple variants of an object in the same bucket, so you can preserve, retrieve and restore every version of every object."
                >
                  Bucket Versioning
                </Header>
              }
            >
              <SpaceBetween size="s">
                <RadioGroup
                  value={versioningEnabled ? 'enable' : 'disable'}
                  onChange={({ detail }) => setVersioning(detail.value)}
                  items={[
                    { value: 'disable', label: 'Disable', disabled: lockOn },
                    { value: 'enable', label: 'Enable', disabled: lockOn },
                  ]}
                />
                {lockOn && (
                  <Box color="text-body-secondary" fontSize="body-s">
                    Object Lock works only in versioned buckets, so enabling it
                    enabled Versioning with it.
                  </Box>
                )}
              </SpaceBetween>
            </Container>

            <Container
              header={
                <Header
                  variant="h2"
                  description="Bucket tags are key-value pairs used to analyze, manage and specify permissions for a bucket."
                  counter={`(${tags.length}/${MAX_TAGS})`}
                >
                  Tags - optional
                </Header>
              }
            >
              <SpaceBetween size="m">
                {tags.length === 0 ? (
                  <Box color="text-body-secondary">
                    No tags associated with this bucket.
                  </Box>
                ) : (
                  <SpaceBetween size="s">
                    {tags.map((tag, index) => (
                      <ColumnLayout key={index} columns={3}>
                        <Input
                          value={tag.Key}
                          onChange={({ detail }) => setTag(index, 'Key', detail.value)}
                          placeholder="Key"
                          ariaLabel={`Tag ${index + 1} key`}
                        />
                        <Input
                          value={tag.Value}
                          onChange={({ detail }) => setTag(index, 'Value', detail.value)}
                          placeholder="Value"
                          ariaLabel={`Tag ${index + 1} value`}
                        />
                        <Box>
                          <Button variant="link" onClick={() => removeTag(index)}>
                            Remove
                          </Button>
                        </Box>
                      </ColumnLayout>
                    ))}
                  </SpaceBetween>
                )}
                <Box>
                  <Button onClick={addTag} disabled={tags.length >= MAX_TAGS}>
                    Add new tag
                  </Button>
                </Box>
              </SpaceBetween>
            </Container>

            <Container
              header={
                <Header
                  variant="h2"
                  description="Server-side encryption is automatically applied to new objects stored in this bucket."
                >
                  Default encryption
                </Header>
              }
            >
              <SpaceBetween size="l">
                <FormField label="Encryption type">
                  <RadioGroup
                    value={encryption}
                    onChange={({ detail }) => setEncryption(detail.value)}
                    items={ENCRYPTION.map(([value, label]) => ({ value, label }))}
                  />
                </FormField>
                <FormField
                  label="Bucket Key"
                  description="A bucket key lowers the calls a KMS-encrypted bucket makes to KMS. It applies to SSE-KMS and DSSE-KMS only, so SSE-S3 does not send it."
                >
                  <RadioGroup
                    value={bucketKey}
                    onChange={({ detail }) => setBucketKey(detail.value)}
                    items={[
                      { value: 'disable', label: 'Disable' },
                      { value: 'enable', label: 'Enable' },
                    ]}
                  />
                </FormField>
              </SpaceBetween>
            </Container>

            <ExpandableSection
              variant="container"
              headerText="Advanced settings"
              headerDescription="Object Lock, and the settings only a create can carry."
            >
              <FormField
                label="Object Lock"
                description="Object Lock stores objects using a write-once-read-many (WORM) model, so they cannot be deleted or overwritten for a fixed amount of time or indefinitely."
              >
                <SpaceBetween size="s">
                  <RadioGroup
                    value={objectLock}
                    onChange={({ detail }) => setObjectLock(detail.value)}
                    items={[
                      { value: 'disable', label: 'Disable' },
                      {
                        value: 'enable',
                        label: 'Enable',
                        description:
                          'Permanently allows objects in this bucket to be locked. It can only be turned on now, at creation.',
                      },
                    ]}
                  />
                  <Alert type="info">
                    Object Lock works only in versioned buckets. Enabling Object
                    Lock automatically enables Versioning.
                  </Alert>
                </SpaceBetween>
              </FormField>
            </ExpandableSection>

            <Alert type="info">
              After creating the bucket, you can upload files and folders to it,
              and configure additional bucket settings.
            </Alert>
          </SpaceBetween>
        </Form>
      </ContentLayout>
    </Shell>
  )
}
