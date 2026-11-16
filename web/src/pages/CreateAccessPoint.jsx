import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import Checkbox from '@cloudscape-design/components/checkbox'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Form from '@cloudscape-design/components/form'
import FormField from '@cloudscape-design/components/form-field'
import Header from '@cloudscape-design/components/header'
import Input from '@cloudscape-design/components/input'
import RadioGroup from '@cloudscape-design/components/radio-group'
import Select from '@cloudscape-design/components/select'
import SpaceBetween from '@cloudscape-design/components/space-between'
import Textarea from '@cloudscape-design/components/textarea'
import { api } from '../api'
import { useSession } from '../context'
import { regionName } from '../regionNames'
import { Shell } from '../components/Shell'

// Block Public Access, in the console's own wording.
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

const allPublic = (value) =>
  Object.fromEntries(PUBLIC_ACCESS.map(([field]) => [field, value]))

export default function CreateAccessPoint() {
  const navigate = useNavigate()
  const { account, region } = useSession()
  const [name, setName] = useState('')
  const [buckets, setBuckets] = useState([])
  const [bucket, setBucket] = useState(null)
  const [origin, setOrigin] = useState('Internet')
  const [vpcId, setVpcId] = useState('')
  const [publicAccess, setPublicAccess] = useState(allPublic(true))
  const [blockAll, setBlockAll] = useState(true)
  const [policy, setPolicy] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const back = () => navigate(`/s3/access-points?region=${region}`)

  // An access point must be in the same Region as its bucket, so the picker offers this Region's buckets and names each one's Region.
  useEffect(() => {
    if (!account) return undefined
    let live = true
    api
      .browse(account, 'all', 's3')
      .then((payload) => {
        if (!live) return
        setBuckets(
          (payload.resources || [])
            .filter((row) => (row.region || region) === region)
            .map((row) => ({
              label: `${row.name} · ${row.region || region}`,
              value: row.name,
            })),
        )
      })
      .catch(() => {
        if (live) setBuckets([])
      })
    return () => {
      live = false
    }
  }, [account, region])

  const submit = async () => {
    setError('')
    if (!name.trim()) {
      setError('An access point name is required.')
      return
    }
    if (!bucket) {
      setError('Choose the bucket this access point is attached to.')
      return
    }
    setBusy(true)
    try {
      await api.createAccessPoint({
        account,
        region,
        name: name.trim(),
        bucket: bucket.value,
        vpc_id: origin === 'VPC' ? vpcId.trim() : '',
        block_public_access: publicAccess,
        policy: policy.trim(),
      })
      navigate(`/s3/access-points?region=${region}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Shell
      breadcrumbs={[
        { text: 'Amazon S3', href: '/s3/home' },
        { text: 'Access Points', href: `/s3/access-points?region=${region}` },
        { text: 'Create access point' },
      ]}
    >
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="Access points are named network endpoints that are attached to buckets which simplify managing data access at scale in S3."
          >
            Create access point
          </Header>
        }
      >
        <Form
          actions={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={back}>
                  Cancel
                </Button>
                <Button variant="primary" loading={busy} onClick={submit}>
                  Create access point
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="l">
            {error && (
              <Alert type="error" header="Could not create the access point">
                {error}
              </Alert>
            )}

            <Container header={<Header variant="h2">General configuration</Header>}>
              <SpaceBetween size="l">
                <Box color="text-body-secondary">
                  Region <strong>{regionName(region)}</strong>{' '}
                  <span className="mono">{region}</span> — picked in the region menu at the top
                  of the console. An access point is created in the Region of its bucket.
                </Box>

                <FormField
                  label="Access point name"
                  description="3 to 50 characters: lowercase letters, digits and hyphens, beginning and ending with a letter or number."
                >
                  <Input
                    value={name}
                    onChange={({ detail }) => setName(detail.value)}
                    placeholder="my-access-point"
                  />
                </FormField>

                <FormField
                  label="Bucket name"
                  description="The bucket this access point is attached to, in this Region."
                >
                  <Select
                    selectedOption={bucket}
                    onChange={({ detail }) => setBucket(detail.selectedOption)}
                    options={buckets}
                    placeholder="Choose bucket"
                    empty="No buckets in this Region"
                  />
                </FormField>
              </SpaceBetween>
            </Container>

            <Container header={<Header variant="h2">Network origin</Header>}>
              <SpaceBetween size="l">
                <RadioGroup
                  value={origin}
                  onChange={({ detail }) => setOrigin(detail.value)}
                  items={[
                    {
                      value: 'Internet',
                      label: 'Internet',
                      description:
                        'Requests can come from anywhere on the internet, subject to the bucket and access point policies.',
                    },
                    {
                      value: 'VPC',
                      label: 'VPC',
                      description:
                        'Requests come through a VPC endpoint; the access point refuses internet traffic.',
                    },
                  ]}
                />
                {origin === 'VPC' && (
                  <FormField
                    label="VPC ID"
                    description="The VPC the endpoint lives in, as `vpc-` and 8 to 17 hex digits."
                  >
                    <Input
                      value={vpcId}
                      onChange={({ detail }) => setVpcId(detail.value)}
                      placeholder="vpc-0123456789abcdef0"
                    />
                  </FormField>
                )}
              </SpaceBetween>
            </Container>

            <Container header={<Header variant="h2">Block Public Access settings for this access point</Header>}>
              <SpaceBetween size="m">
                <Checkbox
                  checked={blockAll}
                  onChange={({ detail }) => {
                    setBlockAll(detail.checked)
                    setPublicAccess(allPublic(detail.checked))
                  }}
                >
                  Block <i>all</i> public access
                </Checkbox>
                <Box color="text-body-secondary" fontSize="body-s">
                  These settings apply only to this access point.
                </Box>
                {PUBLIC_ACCESS.map(([field, label]) => (
                  <Checkbox
                    key={field}
                    checked={Boolean(publicAccess[field])}
                    onChange={({ detail }) => {
                      const next = { ...publicAccess, [field]: detail.checked }
                      setPublicAccess(next)
                      setBlockAll(PUBLIC_ACCESS.every(([key]) => next[key]))
                    }}
                  >
                    {label}
                  </Checkbox>
                ))}
              </SpaceBetween>
            </Container>

            <Container
              header={
                <Header variant="h2" description="Optional. Applied once the access point exists.">
                  Access point policy
                </Header>
              }
            >
              <Textarea
                value={policy}
                onChange={({ detail }) => setPolicy(detail.value)}
                rows={10}
                placeholder='{"Version": "2012-10-17", "Statement": [...]}'
              />
            </Container>
          </SpaceBetween>
        </Form>
      </ContentLayout>
    </Shell>
  )
}
