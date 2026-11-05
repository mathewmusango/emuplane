import { useState } from 'react'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import CopyToClipboard from '@cloudscape-design/components/copy-to-clipboard'
import Form from '@cloudscape-design/components/form'
import FormField from '@cloudscape-design/components/form-field'
import Header from '@cloudscape-design/components/header'
import Input from '@cloudscape-design/components/input'
import SpaceBetween from '@cloudscape-design/components/space-between'
import { api } from '../api'
import { useSession } from '../context'
import { Shell } from '../components/Shell'
import { downloadCredentials } from '../download'

const EMPTY = { username: '', name: '', email: '', password: '' }

export default function Onboarding() {
  const { meta, refresh } = useSession()
  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [created, setCreated] = useState(null)

  const set = (name) => ({ detail }) =>
    setForm((prev) => ({ ...prev, [name]: detail.value }))

  const validate = () => {
    const next = {}
    if (!/^[A-Za-z0-9._-]{3,32}$/.test(form.username)) {
      next.username =
        'Use 3-32 characters: letters, digits, dot, dash or underscore.'
    }
    if (form.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(form.email)) {
      next.email = 'That email address does not look right.'
    }
    if (form.password.length < 8) {
      next.password = 'Use at least 8 characters.'
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    setCreated(null)
    if (!validate()) return
    setLoading(true)
    try {
      const payload = await api.provision({
        username: form.username,
        name: form.name,
        email: form.email,
        password: form.password,
      })
      setCreated(payload)
      setForm(EMPTY)
      setErrors({})
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (meta && !meta.platform_admin) {
    return (
      <Shell
        activeHref="/onboarding"
        breadcrumbs={[{ text: 'Onboarding', href: '/onboarding' }]}
      >
        <ContentLayout header={<Header variant="h1">Onboarding</Header>}>
          <Alert type="warning">
            Only a global admin can provision accounts.
          </Alert>
        </ContentLayout>
      </Shell>
    )
  }

  return (
    <Shell
      activeHref="/onboarding"
      breadcrumbs={[
        { text: 'Accounts', href: '/accounts' },
        { text: 'Onboarding', href: '/onboarding' },
      ]}
    >
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="Provisions an account, a local login and one IAM access key. The account ID then works in every region. Signing in with Keycloak for the first time mints an account the same way."
          >
            Onboard an account
          </Header>
        }
      >
        <SpaceBetween size="l">
          {error && <Alert type="error">{error}</Alert>}

          {created && (
            <Container
              header={
                <Header variant="h2" description="The secret is shown once, on this screen only.">
                  Account provisioned
                </Header>
              }
            >
              <SpaceBetween size="m">
                <ColumnLayout columns={2} variant="text-grid">
                  <div>
                    <Box variant="awsui-key-label">Account ID</Box>
                    <CopyToClipboard
                      variant="inline"
                      textToCopy={created.account_id}
                      copyButtonAriaLabel="Copy account ID"
                      copySuccessText="Account ID copied"
                      copyErrorText="Could not copy the account ID"
                      wrapText={false}
                    />
                  </div>
                  <div>
                    <Box variant="awsui-key-label">IAM user</Box>
                    <Box variant="code">{created.iam_user}</Box>
                  </div>
                  <div>
                    <Box variant="awsui-key-label">aws_access_key_id</Box>
                    <CopyToClipboard
                      variant="inline"
                      textToCopy={created.aws_access_key_id || ''}
                      copyButtonAriaLabel="Copy aws_access_key_id"
                      copySuccessText="aws_access_key_id copied"
                      copyErrorText="Could not copy the access key ID"
                      wrapText={false}
                    />
                  </div>
                  <div>
                    <Box variant="awsui-key-label">aws_secret_access_key</Box>
                    <CopyToClipboard
                      variant="inline"
                      textToCopy={created.aws_secret_access_key || ''}
                      copyButtonAriaLabel="Copy aws_secret_access_key"
                      copySuccessText="aws_secret_access_key copied"
                      copyErrorText="Could not copy the secret"
                      wrapText={false}
                    />
                  </div>
                </ColumnLayout>
                <SpaceBetween direction="horizontal" size="xs">
                  <Button
                    iconName="download"
                    onClick={() =>
                      downloadCredentials({
                        account: created.account_id,
                        accessKeyId: created.aws_access_key_id,
                        secretAccessKey: created.aws_secret_access_key,
                        region: created.region,
                        username: created.iam_user || created.username,
                      })
                    }
                  >
                    Download .csv
                  </Button>
                </SpaceBetween>
                <Alert type="warning">
                  Store the secret now. It is not retrievable from the console.
                </Alert>
              </SpaceBetween>
            </Container>
          )}

          <Container header={<Header variant="h2">New account</Header>}>
            <form onSubmit={submit}>
              <Form
                actions={
                  <Button variant="primary" formAction="submit" loading={loading}>
                    Provision account
                  </Button>
                }
              >
                <SpaceBetween size="m">
                  <ColumnLayout columns={2}>
                    <FormField label="Name" errorText={errors.name}>
                      <Input value={form.name} onChange={set('name')} placeholder="Engineer One" />
                    </FormField>
                    <FormField
                      label="Username"
                      errorText={errors.username}
                    >
                      <Input value={form.username} onChange={set('username')} placeholder="engineer-01" />
                    </FormField>
                  </ColumnLayout>
                  <FormField
                    label="Email"
                    description="Optional, used only for the local login."
                    errorText={errors.email}
                  >
                    <Input type="email" value={form.email} onChange={set('email')} placeholder="engineer@example.com" />
                  </FormField>
                  <FormField
                    label="Password"
                    constraintText="At least 8 characters."
                    errorText={errors.password}
                  >
                    <Input type="password" value={form.password} onChange={set('password')} />
                  </FormField>
                  <Box color="text-body-secondary" fontSize="body-s">
                    Creates a new 12-digit account ID, a local login for this console and
                    one IAM user with an admin policy. The inviter stays signed in.
                  </Box>
                </SpaceBetween>
              </Form>
            </form>
          </Container>
        </SpaceBetween>
      </ContentLayout>
    </Shell>
  )
}
