import { useCallback, useEffect, useState } from 'react'
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
import ExpandableSection from '@cloudscape-design/components/expandable-section'
import Input from '@cloudscape-design/components/input'
import Modal from '@cloudscape-design/components/modal'
import SpaceBetween from '@cloudscape-design/components/space-between'
import Table from '@cloudscape-design/components/table'
import Toggle from '@cloudscape-design/components/toggle'
import { api } from '../api'
import { useSession } from '../context'
import { Shell } from '../components/Shell'
import { downloadCredentials } from '../download'

export default function Settings() {
  const { meta, me, account, refresh } = useSession()
  const [error, setError] = useState('')
  const [savingRegion, setSavingRegion] = useState('')
  const [settings, setSettings] = useState(null)
  const [savingSignup, setSavingSignup] = useState(false)

  const [keys, setKeys] = useState([])
  const [maxKeys, setMaxKeys] = useState(2)
  const [loadingKeys, setLoadingKeys] = useState(true)
  const [creating, setCreating] = useState(false)
  const [created, setCreated] = useState(null)
  const [creatingKey, setCreatingKey] = useState(false)
  const [keyName, setKeyName] = useState('')
  const [keyNameError, setKeyNameError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const loadKeys = useCallback(async () => {
    setLoadingKeys(true)
    try {
      const payload = await api.credentials()
      setKeys(payload.keys || [])
      setMaxKeys(payload.max_keys || 2)
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoadingKeys(false)
    }
  }, [])

  useEffect(() => {
    loadKeys()
  }, [loadKeys])

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

  const createKey = async () => {
    const name = keyName.trim()
    if (!name) {
      setKeyNameError('Enter a name for this key.')
      return
    }
    setCreatingKey(true)
    setKeyNameError('')
    setError('')
    try {
      const payload = await api.createAccessKey(name)
      setCreated(payload)
      setKeys(payload.keys || [])
      setMaxKeys(payload.max_keys || 2)
      setCreating(false)
      setKeyName('')
      refresh()
    } catch (err) {
      setKeyNameError(err.message)
    } finally {
      setCreatingKey(false)
    }
  }

  const removeKey = async () => {
    if (!confirmDelete) return
    setDeleting(true)
    setError('')
    try {
      const payload = await api.deleteAccessKey(confirmDelete.access_key_id)
      setKeys(payload.keys || [])
      setMaxKeys(payload.max_keys || 2)
      setConfirmDelete(null)
      if (created?.key?.access_key_id === confirmDelete.access_key_id) {
        setCreated(null)
      }
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setDeleting(false)
    }
  }

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
    locked: name === 'us-east-1',
  }))

  const atCap = keys.length >= maxKeys

  return (
    <Shell activeHref="/settings" breadcrumbs={[{ text: 'Settings', href: '/settings' }]}>
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="Session, access keys, sign-up and the regions this account can use."
          >
            Settings
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

          <Container
            header={
              <Header
                variant="h2"
                description={`Up to ${maxKeys} IAM access keys per account. The secret is shown once, when the key is created.`}
                counter={`(${keys.length}/${maxKeys})`}
                actions={
                  <SpaceBetween direction="horizontal" size="xs">
                    <Button iconName="refresh" onClick={loadKeys} loading={loadingKeys}>
                      Refresh
                    </Button>
                    <Button
                      variant="primary"
                      disabled={atCap || loadingKeys}
                      onClick={() => {
                        setKeyName('')
                        setKeyNameError('')
                        setCreating(true)
                      }}
                    >
                      Create access key
                    </Button>
                  </SpaceBetween>
                }
              >
                Access keys
              </Header>
            }
          >
            <SpaceBetween size="m">
              {created?.key && (
                <Alert
                  type="success"
                  header="Access key created"
                  dismissible
                  onDismiss={() => setCreated(null)}
                >
                  <SpaceBetween size="m">
                    <Box>
                      This is the only time the secret is shown. Copy it or download
                      the CSV now.
                    </Box>
                    <ColumnLayout columns={2} variant="text-grid">
                      <div>
                        <Box variant="awsui-key-label">aws_access_key_id</Box>
                        <CopyToClipboard
                          variant="inline"
                          textToCopy={created.key.access_key_id}
                          textToDisplay={
                            <span className="mono">{created.key.access_key_id}</span>
                          }
                          copyButtonAriaLabel="Copy aws_access_key_id"
                          copySuccessText="aws_access_key_id copied"
                          copyErrorText="Could not copy the key ID"
                          wrapText={false}
                        />
                      </div>
                      <div>
                        <Box variant="awsui-key-label">aws_secret_access_key</Box>
                        <CopyToClipboard
                          variant="inline"
                          textToCopy={created.key.secret_access_key}
                          textToDisplay={
                            <span className="mono">{created.key.secret_access_key}</span>
                          }
                          copyButtonAriaLabel="Copy aws_secret_access_key"
                          copySuccessText="aws_secret_access_key copied"
                          copyErrorText="Could not copy the secret"
                          wrapText={false}
                        />
                      </div>
                    </ColumnLayout>
                    <Button
                      iconName="download"
                      onClick={() =>
                        downloadCredentials({
                          account: created.account,
                          accessKeyId: created.key.access_key_id,
                          secretAccessKey: created.key.secret_access_key,
                          region: created.region,
                          username: created.user,
                        })
                      }
                    >
                      Download .csv
                    </Button>
                  </SpaceBetween>
                </Alert>
              )}

              <Table
                items={keys}
                loading={loadingKeys}
                loadingText="Reading access keys"
                trackBy="access_key_id"
                columnDefinitions={[
                  {
                    id: 'name',
                    header: 'Name',
                    cell: (item) => item.name,
                    sortingField: 'name',
                  },
                  {
                    id: 'access_key_id',
                    header: 'Access key ID',
                    cell: (item) => <span className="mono">{item.masked}</span>,
                  },
                  {
                    id: 'secret',
                    header: 'Secret access key',
                    cell: (item) => <span className="mono">{item.masked_secret}</span>,
                  },
                  {
                    id: 'created',
                    header: 'Created',
                    cell: (item) => item.created_at || '—',
                    width: 220,
                  },
                  {
                    id: 'actions',
                    header: '',
                    cell: (item) => (
                      <Button
                        variant="inline-link"
                        onClick={() => setConfirmDelete(item)}
                      >
                        Delete
                      </Button>
                    ),
                    width: 90,
                  },
                ]}
                empty={
                  <Box textAlign="center">
                    No access keys. Create one to sign AWS clients against this
                    account.
                  </Box>
                }
              />

              {atCap && (
                <Box color="text-body-secondary">
                  This account already holds {maxKeys} keys. Delete one before
                  creating another.
                </Box>
              )}
            </SpaceBetween>
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
                  cell: (item) => <span className="mono">{item.name}</span>,
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

          <Modal
            visible={creating}
            onDismiss={() => setCreating(false)}
            header="Create access key"
            footer={
              <Box float="right">
                <SpaceBetween direction="horizontal" size="xs">
                  <Button variant="link" onClick={() => setCreating(false)}>
                    Cancel
                  </Button>
                  <Button variant="primary" loading={creatingKey} onClick={createKey}>
                    Create
                  </Button>
                </SpaceBetween>
              </Box>
            }
          >
            <Form>
              <FormField
                label="Key name"
                description="A label for this key, so you can tell the two apart later — for example the machine or pipeline that uses it."
                errorText={keyNameError}
              >
                <Input
                  value={keyName}
                  onChange={({ detail }) => {
                    setKeyName(detail.value)
                    setKeyNameError('')
                  }}
                  placeholder="laptop-cli"
                  autoFocus
                />
              </FormField>
            </Form>
          </Modal>

          <Modal
            visible={Boolean(confirmDelete)}
            onDismiss={() => setConfirmDelete(null)}
            header="Delete access key?"
            footer={
              <Box float="right">
                <SpaceBetween direction="horizontal" size="xs">
                  <Button variant="link" onClick={() => setConfirmDelete(null)}>
                    Cancel
                  </Button>
                  <Button variant="primary" loading={deleting} onClick={removeKey}>
                    Delete key
                  </Button>
                </SpaceBetween>
              </Box>
            }
          >
            <SpaceBetween size="s">
              <Box>
                This deletes <strong>{confirmDelete?.name}</strong> (
                <span className="mono">{confirmDelete?.masked}</span>).
              </Box>
              <Box color="text-status-warning">
                The key stops working immediately. Anything that still uses it
                will fail.
              </Box>
            </SpaceBetween>
          </Modal>
        </SpaceBetween>
      </ContentLayout>
    </Shell>
  )
}
