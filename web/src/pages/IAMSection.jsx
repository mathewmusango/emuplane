// The IAM console: dashboard, identities, policies and reports, each backed by the emulator's own API.

import { useCallback, useEffect, useMemo, useState } from 'react'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import Checkbox from '@cloudscape-design/components/checkbox'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Form from '@cloudscape-design/components/form'
import FormField from '@cloudscape-design/components/form-field'
import Header from '@cloudscape-design/components/header'
import Input from '@cloudscape-design/components/input'
import Modal from '@cloudscape-design/components/modal'
import Select from '@cloudscape-design/components/select'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import Table from '@cloudscape-design/components/table'
import Textarea from '@cloudscape-design/components/textarea'
import { api } from '../api'
import { useSession } from '../context'
import { Shell } from '../components/Shell'
import IAMDashboard from './IAMDashboard'
import { column, documentText, members, parseIam, text, values } from '../iam'

const TRUST = JSON.stringify(
  {
    Version: '2012-10-17',
    Statement: [
      {
        Effect: 'Allow',
        Principal: { Service: 'lambda.amazonaws.com' },
        Action: 'sts:AssumeRole',
      },
    ],
  },
  null,
  2,
)

const POLICY = JSON.stringify(
  {
    Version: '2012-10-17',
    Statement: [{ Effect: 'Allow', Action: 's3:GetObject', Resource: '*' }],
  },
  null,
  2,
)

const DESCRIPTIONS = {
  dashboard: 'Security recommendations, the account behind this console, and what IAM holds.',
  users: 'An IAM user is an identity with long-term credentials inside this account.',
  groups: 'A user group is a collection of IAM users, so permissions can be granted once.',
  roles: 'A role is an identity with temporary credentials that a trusted entity can assume.',
  policies: 'A policy is a JSON document that defines what an identity may do.',
  providers:
    'Identity providers trust OpenID Connect or SAML identities from outside the account.',
  settings: 'The emulator password policy and its account alias.',
  report: 'The credential report lists every IAM user and the state of its credentials.',
}

const TITLES = {
  dashboard: 'IAM Dashboard',
  users: 'IAM users',
  groups: 'IAM user groups',
  roles: 'Roles',
  policies: 'Policies',
  providers: 'Identity providers',
  settings: 'Account settings',
  report: 'Credential report',
}

async function call(account, region, operation, params = {}) {
  const result = await api.exec({ account, region, service: 'iam', operation, params })
  if (!result.ok) throw new Error(result.error || `IAM ${operation} failed`)
  return parseIam(result.body)
}

function Page({ section, counter, actions, children }) {
  const title = TITLES[section]
  return (
    <Shell
      activeHref={`/iam/${section}`}
      breadcrumbs={[
        { text: 'IAM', href: '/iam/dashboard' },
        { text: title },
      ]}
    >
      <ContentLayout
        header={
          <Header
            variant="h1"
            counter={counter}
            description={DESCRIPTIONS[section]}
            actions={actions}
          >
            {title}
          </Header>
        }
      >
        <SpaceBetween size="l">{children}</SpaceBetween>
      </ContentLayout>
    </Shell>
  )
}

function ErrorAlert({ error }) {
  return error ? <Alert type="error">{error}</Alert> : null
}

function useIam() {
  const { account, region } = useSession()
  return useCallback(
    (operation, params) => call(account, region, operation, params),
    [account, region],
  )
}

// ---------------------------------------------------------------------- users

const EMPTY_USER = { username: '', email: '', password: '' }

function Users() {
  const { account } = useSession()
  const iam = useIam()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState([])
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_USER)
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null)
  const [detail, setDetail] = useState(null)
  const [passwordFor, setPasswordFor] = useState(null)
  const [password, setPassword] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [doc, accounts] = await Promise.all([iam('list-users'), api.users()])
      const principals = (
        accounts.find((entry) => entry.account_id === account)?.users || []
      ).filter((user) => user.role !== 'root')
      const consoleNames = new Set(principals.map((user) => user.username))
      const listed = await Promise.all(
        members(doc, 'Users').map(async (user) => {
          const name = text(user, 'UserName')
          const [groups, mfa] = await Promise.all([
            iam('list-groups-for-user', { UserName: name }).catch(() => null),
            iam('list-mfa-devices', { UserName: name }).catch(() => null),
          ])
          return {
            name,
            path: text(user, 'Path') || '/',
            created: text(user, 'CreateDate'),
            groups: members(groups, 'Groups').length,
            mfa: members(mfa, 'MFADevices').length,
            console: consoleNames.has(name),
          }
        }),
      )
      const seen = new Set(listed.map((row) => row.name))
      const consoleOnly = principals
        .filter((user) => !seen.has(user.username))
        .map((user) => ({
          name: user.username,
          path: '/',
          created: '',
          groups: 0,
          mfa: 0,
          console: true,
        }))
      setRows([...listed, ...consoleOnly].sort((a, b) => a.name.localeCompare(b.name)))
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [account, iam])

  useEffect(() => {
    load()
  }, [load])

  const create = async () => {
    setBusy(true)
    setError('')
    try {
      await api.createUser({
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password,
        account,
      })
      setCreateOpen(false)
      setForm(EMPTY_USER)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!confirm) return
    setBusy(true)
    setError('')
    try {
      await api.deleteUser(confirm.name, account)
      setConfirm(null)
      setSelected([])
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const setPasswordNow = async () => {
    setBusy(true)
    setError('')
    try {
      await api.setUserPassword(passwordFor, password, account)
      setPasswordFor(null)
      setPassword('')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const openDetail = async (row) => {
    setDetail({ row, loading: true })
    try {
      const [groups, attached, inline, keys] = await Promise.all([
        iam('list-groups-for-user', { UserName: row.name }).catch(() => null),
        iam('list-attached-user-policies', { UserName: row.name }).catch(() => null),
        iam('list-user-policies', { UserName: row.name }).catch(() => null),
        iam('list-access-keys', { UserName: row.name }).catch(() => null),
      ])
      setDetail({
        row,
        loading: false,
        groups: column(groups, 'Groups', 'GroupName'),
        attached: column(attached, 'AttachedPolicies', 'PolicyName'),
        inline: values(inline, 'PolicyNames'),
        keys: members(keys, 'AccessKeyMetadata').map((key) => ({
          id: text(key, 'AccessKeyId'),
          status: text(key, 'Status'),
        })),
      })
    } catch (err) {
      setDetail({ row, loading: false, error: err.message })
    }
  }

  const item = selected[0]

  return (
    <Page
      section="users"
      counter={`(${rows.length})`}
      actions={
        <SpaceBetween direction="horizontal" size="xs">
          <Button iconName="refresh" onClick={load} loading={loading}>
            Refresh
          </Button>
          <Button
            disabled={!item || !item.console}
            onClick={() => item && item.console && setPasswordFor(item.name)}
          >
            Set password
          </Button>
          <Button disabled={!item} onClick={() => item && setConfirm(item)}>
            Delete user
          </Button>
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            Create user
          </Button>
        </SpaceBetween>
      }
    >
      <ErrorAlert error={error} />
      <Table
        items={rows}
        loading={loading}
        loadingText="Reading IAM users"
        trackBy="name"
        selectionType="single"
        selectedItems={selected}
        onSelectionChange={({ detail: change }) => setSelected(change.selectedItems)}
        columnDefinitions={[
          {
            id: 'name',
            header: 'User name',
            cell: (row) => (
              <Button variant="link" onClick={() => openDetail(row)}>
                {row.name}
              </Button>
            ),
            sortingField: 'name',
          },
          { id: 'path', header: 'Path', cell: (row) => row.path, width: 140 },
          { id: 'groups', header: 'Groups', cell: (row) => row.groups, width: 100 },
          {
            id: 'mfa',
            header: 'MFA',
            cell: (row) => (row.mfa ? `${row.mfa} device(s)` : '—'),
            width: 140,
          },
          {
            id: 'console',
            header: 'Sign-in',
            cell: (row) => (row.console ? 'Console' : 'Outside Emuplane'),
            width: 170,
          },
          { id: 'created', header: 'Creation time', cell: (row) => row.created || '—' },
        ]}
        empty={
          <Box textAlign="center">
            No IAM users. Create one to give a person its own credentials.
          </Box>
        }
      />

      <Modal
        visible={createOpen}
        onDismiss={() => setCreateOpen(false)}
        header="Create user"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={create}>
                Create user
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Form>
          <SpaceBetween size="m">
            <FormField
              label="User name"
              description="3-32 letters, digits, dot, dash or underscore."
            >
              <Input
                value={form.username}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, username: detail.value }))
                }
                placeholder="deploy-bot"
              />
            </FormField>
            <FormField
              label="Email address"
              description="Optional; used by password reset."
            >
              <Input
                value={form.email}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, email: detail.value }))
                }
                placeholder="owner@example.com"
              />
            </FormField>
            <FormField
              label="Console password"
              description="At least 8 characters. The user signs in to this console with it."
            >
              <Input
                type="password"
                value={form.password}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, password: detail.value }))
                }
              />
            </FormField>
          </SpaceBetween>
        </Form>
      </Modal>

      <Modal
        visible={Boolean(confirm)}
        onDismiss={() => setConfirm(null)}
        header="Delete user?"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setConfirm(null)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={remove}>
                Delete user
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          <Box>
            This deletes <strong>{confirm?.name}</strong>, its access keys and its
            policies.
          </Box>
          <Box color="text-status-warning">
            Credentials that still use this identity stop working immediately.
          </Box>
        </SpaceBetween>
      </Modal>

      <Modal
        visible={Boolean(passwordFor)}
        onDismiss={() => setPasswordFor(null)}
        header="Set console password"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setPasswordFor(null)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={setPasswordNow}>
                Set password
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Form>
          <FormField
            label={`New password for ${passwordFor || ''}`}
            description="At least 8 characters; open sessions for this user are revoked."
          >
            <Input
              type="password"
              value={password}
              onChange={({ detail }) => setPassword(detail.value)}
            />
          </FormField>
        </Form>
      </Modal>

      <Modal
        visible={Boolean(detail)}
        onDismiss={() => setDetail(null)}
        header={`User ${detail?.row?.name || ''}`}
        size="large"
      >
        {!detail ? null : detail.loading ? (
          <Box>Reading the user's details…</Box>
        ) : detail.error ? (
          <Alert type="error">{detail.error}</Alert>
        ) : (
          <SpaceBetween size="m">
            <ColumnLayout columns={3} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Path</Box>
                <Box>{detail.row.path}</Box>
              </div>
              <div>
                <Box variant="awsui-key-label">Created</Box>
                <Box>{detail.row.created || '—'}</Box>
              </div>
              <div>
                <Box variant="awsui-key-label">Sign-in</Box>
                <Box>{detail.row.console ? 'Console principal' : 'Outside Emuplane'}</Box>
              </div>
            </ColumnLayout>
            <div>
              <Box variant="awsui-key-label">Groups</Box>
              <Box>{detail.groups?.join(', ') || '—'}</Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Attached policies</Box>
              <Box>{detail.attached?.join(', ') || '—'}</Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Inline policies</Box>
              <Box>{detail.inline?.join(', ') || '—'}</Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Access keys</Box>
              <Box>
                {detail.keys?.length
                  ? detail.keys.map((key) => `${key.id} (${key.status})`).join(', ')
                  : '—'}
              </Box>
            </div>
          </SpaceBetween>
        )}
      </Modal>
    </Page>
  )
}

// --------------------------------------------------------------------- groups

const EMPTY_GROUP = { name: '', path: '/' }

function Groups() {
  const iam = useIam()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState([])
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_GROUP)
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const doc = await iam('list-groups')
      const listed = await Promise.all(
        members(doc, 'Groups').map(async (group) => {
          const name = text(group, 'GroupName')
          const [detail, attached, inline] = await Promise.all([
            iam('get-group', { GroupName: name }).catch(() => null),
            iam('list-attached-group-policies', { GroupName: name }).catch(() => null),
            iam('list-group-policies', { GroupName: name }).catch(() => null),
          ])
          return {
            name,
            path: text(group, 'Path') || '/',
            created: text(group, 'CreateDate'),
            users: members(detail, 'Users').length,
            policies:
              members(attached, 'AttachedPolicies').length +
              members(inline, 'PolicyNames').length,
          }
        }),
      )
      setRows(listed.sort((a, b) => a.name.localeCompare(b.name)))
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [iam])

  useEffect(() => {
    load()
  }, [load])

  const create = async () => {
    setBusy(true)
    setError('')
    try {
      await iam('create-group', { GroupName: form.name.trim(), Path: form.path.trim() })
      setCreateOpen(false)
      setForm(EMPTY_GROUP)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    setError('')
    try {
      await iam('delete-group', { GroupName: confirm.name })
      setConfirm(null)
      setSelected([])
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const item = selected[0]

  return (
    <Page
      section="groups"
      counter={`(${rows.length})`}
      actions={
        <SpaceBetween direction="horizontal" size="xs">
          <Button iconName="refresh" onClick={load} loading={loading}>
            Refresh
          </Button>
          <Button disabled={!item} onClick={() => item && setConfirm(item)}>
            Delete
          </Button>
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            Create group
          </Button>
        </SpaceBetween>
      }
    >
      <ErrorAlert error={error} />
      <Table
        items={rows}
        loading={loading}
        loadingText="Reading IAM user groups"
        trackBy="name"
        selectionType="single"
        selectedItems={selected}
        onSelectionChange={({ detail: change }) => setSelected(change.selectedItems)}
        columnDefinitions={[
          { id: 'name', header: 'Group name', cell: (row) => row.name, sortingField: 'name' },
          { id: 'path', header: 'Path', cell: (row) => row.path, width: 140 },
          { id: 'users', header: 'Users', cell: (row) => row.users, width: 100 },
          { id: 'policies', header: 'Policies', cell: (row) => row.policies, width: 110 },
          { id: 'created', header: 'Creation time', cell: (row) => row.created || '—' },
        ]}
        empty={<Box textAlign="center">No user groups. Create one to grant permissions once.</Box>}
      />

      <Modal
        visible={createOpen}
        onDismiss={() => setCreateOpen(false)}
        header="Create group"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={create}>
                Create group
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Form>
          <SpaceBetween size="m">
            <FormField label="Group name">
              <Input
                value={form.name}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, name: detail.value }))
                }
                placeholder="platform"
              />
            </FormField>
            <FormField label="Path">
              <Input
                value={form.path}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, path: detail.value }))
                }
                placeholder="/"
              />
            </FormField>
          </SpaceBetween>
        </Form>
      </Modal>

      <Modal
        visible={Boolean(confirm)}
        onDismiss={() => setConfirm(null)}
        header="Delete group?"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setConfirm(null)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={remove}>
                Delete group
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Box>
          This deletes <strong>{confirm?.name}</strong> and its inline policies. Its
          members keep their own identities.
        </Box>
      </Modal>
    </Page>
  )
}

// ---------------------------------------------------------------------- roles

const EMPTY_ROLE = { name: '', description: '', trust: TRUST }

function trustedEntity(role) {
  try {
    const doc = JSON.parse(documentText(text(role, 'AssumeRolePolicyDocument')))
    const statement = Array.isArray(doc.Statement) ? doc.Statement[0] : doc.Statement
    const principal = statement?.Principal
    if (!principal) return '—'
    if (principal.Service) return `AWS service: ${principal.Service}`
    if (principal.Federated) return `Federated: ${principal.Federated}`
    if (principal.AWS) return `AWS: ${principal.AWS}`
    return '—'
  } catch {
    return '—'
  }
}

function Roles() {
  const iam = useIam()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState([])
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_ROLE)
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const doc = await iam('list-roles')
      setRows(
        members(doc, 'Roles')
          .map((role) => ({
            name: text(role, 'RoleName'),
            path: text(role, 'Path') || '/',
            created: text(role, 'CreateDate'),
            max: text(role, 'MaxSessionDuration') || '3600',
            trusted: trustedEntity(role),
          }))
          .sort((a, b) => a.name.localeCompare(b.name)),
      )
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [iam])

  useEffect(() => {
    load()
  }, [load])

  const create = async () => {
    setBusy(true)
    setError('')
    try {
      await iam('create-role', {
        RoleName: form.name.trim(),
        Description: form.description.trim(),
        AssumeRolePolicyDocument: form.trust,
      })
      setCreateOpen(false)
      setForm(EMPTY_ROLE)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    setError('')
    try {
      await iam('delete-role', { RoleName: confirm.name })
      setConfirm(null)
      setSelected([])
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const item = selected[0]

  return (
    <Page
      section="roles"
      counter={`(${rows.length})`}
      actions={
        <SpaceBetween direction="horizontal" size="xs">
          <Button iconName="refresh" onClick={load} loading={loading}>
            Refresh
          </Button>
          <Button disabled={!item} onClick={() => item && setConfirm(item)}>
            Delete
          </Button>
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            Create role
          </Button>
        </SpaceBetween>
      }
    >
      <ErrorAlert error={error} />
      <Table
        items={rows}
        loading={loading}
        loadingText="Reading IAM roles"
        trackBy="name"
        selectionType="single"
        selectedItems={selected}
        onSelectionChange={({ detail: change }) => setSelected(change.selectedItems)}
        columnDefinitions={[
          { id: 'name', header: 'Role name', cell: (row) => row.name, sortingField: 'name' },
          { id: 'trusted', header: 'Trusted entities', cell: (row) => row.trusted },
          { id: 'path', header: 'Path', cell: (row) => row.path, width: 160 },
          {
            id: 'max',
            header: 'Max session',
            cell: (row) => `${row.max}s`,
            width: 130,
          },
          { id: 'created', header: 'Creation time', cell: (row) => row.created || '—' },
        ]}
        empty={<Box textAlign="center">No roles. Create one to delegate access.</Box>}
      />

      <Modal
        visible={createOpen}
        onDismiss={() => setCreateOpen(false)}
        header="Create role"
        size="large"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={create}>
                Create role
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Form>
          <SpaceBetween size="m">
            <FormField label="Role name">
              <Input
                value={form.name}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, name: detail.value }))
                }
                placeholder="metrics-reader"
              />
            </FormField>
            <FormField label="Description">
              <Input
                value={form.description}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, description: detail.value }))
                }
              />
            </FormField>
            <FormField
              label="Trust policy (JSON)"
              description="The entities allowed to assume this role."
            >
              <Textarea
                rows={8}
                value={form.trust}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, trust: detail.value }))
                }
              />
            </FormField>
          </SpaceBetween>
        </Form>
      </Modal>

      <Modal
        visible={Boolean(confirm)}
        onDismiss={() => setConfirm(null)}
        header="Delete role?"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setConfirm(null)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={remove}>
                Delete role
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Box>
          This deletes <strong>{confirm?.name}</strong>. The emulator refuses while a
          policy or instance profile still references it.
        </Box>
      </Modal>
    </Page>
  )
}

// ------------------------------------------------------------------- policies

const EMPTY_POLICY = { name: '', description: '', document: POLICY }

function isAwsManaged(arn) {
  return arn.includes(':policy/') && arn.includes('::aws:')
}

function Policies() {
  const iam = useIam()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState([])
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_POLICY)
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const doc = await iam('list-policies')
      setRows(
        members(doc, 'Policies')
          .map((policy) => {
            const arn = text(policy, 'Arn')
            return {
              name: text(policy, 'PolicyName'),
              arn,
              type: isAwsManaged(arn) ? 'AWS managed' : 'Customer managed',
              attachments: text(policy, 'AttachmentCount') || '0',
              description: text(policy, 'Description'),
            }
          })
          .sort((a, b) => a.name.localeCompare(b.name)),
      )
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [iam])

  useEffect(() => {
    load()
  }, [load])

  const create = async () => {
    setBusy(true)
    setError('')
    try {
      await iam('create-policy', {
        PolicyName: form.name.trim(),
        Description: form.description.trim(),
        PolicyDocument: form.document,
      })
      setCreateOpen(false)
      setForm(EMPTY_POLICY)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    setError('')
    try {
      await iam('delete-policy', { PolicyArn: confirm.arn })
      setConfirm(null)
      setSelected([])
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const item = selected[0]
  const deletable = item && item.type === 'Customer managed'

  return (
    <Page
      section="policies"
      counter={`(${rows.length})`}
      actions={
        <SpaceBetween direction="horizontal" size="xs">
          <Button iconName="refresh" onClick={load} loading={loading}>
            Refresh
          </Button>
          <Button disabled={!deletable} onClick={() => deletable && setConfirm(item)}>
            Delete
          </Button>
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            Create policy
          </Button>
        </SpaceBetween>
      }
    >
      <ErrorAlert error={error} />
      <Table
        items={rows}
        loading={loading}
        loadingText="Reading IAM policies"
        trackBy="arn"
        selectionType="single"
        selectedItems={selected}
        onSelectionChange={({ detail: change }) => setSelected(change.selectedItems)}
        columnDefinitions={[
          { id: 'name', header: 'Policy name', cell: (row) => row.name, sortingField: 'name' },
          { id: 'type', header: 'Type', cell: (row) => row.type, width: 170 },
          { id: 'attachments', header: 'Attachments', cell: (row) => row.attachments, width: 130 },
          { id: 'description', header: 'Description', cell: (row) => row.description || '—' },
        ]}
        empty={<Box textAlign="center">No policies.</Box>}
      />

      <Modal
        visible={createOpen}
        onDismiss={() => setCreateOpen(false)}
        header="Create policy"
        size="large"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={create}>
                Create policy
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Form>
          <SpaceBetween size="m">
            <FormField label="Policy name">
              <Input
                value={form.name}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, name: detail.value }))
                }
                placeholder="read-logs"
              />
            </FormField>
            <FormField label="Description">
              <Input
                value={form.description}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, description: detail.value }))
                }
              />
            </FormField>
            <FormField label="Policy document (JSON)">
              <Textarea
                rows={10}
                value={form.document}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, document: detail.value }))
                }
              />
            </FormField>
          </SpaceBetween>
        </Form>
      </Modal>

      <Modal
        visible={Boolean(confirm)}
        onDismiss={() => setConfirm(null)}
        header="Delete policy?"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setConfirm(null)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={remove}>
                Delete policy
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Box>
          This deletes <strong>{confirm?.name}</strong>. Detach it from every identity
          first.
        </Box>
      </Modal>
    </Page>
  )
}

// ---------------------------------------------------------- identity providers

const EMPTY_PROVIDER = {
  type: { label: 'OpenID Connect', value: 'oidc' },
  url: '',
  clientId: '',
  thumbprint: '',
  name: '',
  metadata: '',
}

function Providers() {
  const iam = useIam()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState([])
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState(EMPTY_PROVIDER)
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [oidc, saml] = await Promise.all([
        iam('list-open-id-connect-providers'),
        iam('list-saml-providers'),
      ])
      const oidcRows = await Promise.all(
        column(oidc, 'OpenIDConnectProviderList', 'Arn').map(async (arn) => {
          const detail = await iam('get-open-id-connect-provider', {
            OpenIDConnectProviderArn: arn,
          }).catch(() => null)
          return {
            arn,
            name: arn.split('/').slice(1).join('/'),
            type: 'OpenID Connect',
            created: text(detail, 'CreateDate'),
          }
        }),
      )
      const samlRows = members(saml, 'SAMLProviderList').map((row) => {
        const arn = text(row, 'Arn')
        return {
          arn,
          name: arn.split('/').slice(1).join('/'),
          type: 'SAML',
          created: text(row, 'CreateDate'),
        }
      })
      setRows([...oidcRows, ...samlRows].sort((a, b) => a.name.localeCompare(b.name)))
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [iam])

  useEffect(() => {
    load()
  }, [load])

  const create = async () => {
    setBusy(true)
    setError('')
    try {
      if (form.type.value === 'oidc') {
        await iam('create-open-id-connect-provider', {
          Url: form.url.trim(),
          'ClientIDList.member.1': form.clientId.trim(),
          'ThumbprintList.member.1': form.thumbprint.trim(),
        })
      } else {
        await iam('create-saml-provider', {
          Name: form.name.trim(),
          SAMLMetadataDocument: form.metadata,
        })
      }
      setCreateOpen(false)
      setForm(EMPTY_PROVIDER)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setBusy(true)
    setError('')
    try {
      if (confirm.arn.includes(':oidc-provider/')) {
        await iam('delete-open-id-connect-provider', {
          OpenIDConnectProviderArn: confirm.arn,
        })
      } else {
        await iam('delete-saml-provider', { SAMLProviderArn: confirm.arn })
      }
      setConfirm(null)
      setSelected([])
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const item = selected[0]

  return (
    <Page
      section="providers"
      counter={`(${rows.length})`}
      actions={
        <SpaceBetween direction="horizontal" size="xs">
          <Button iconName="refresh" onClick={load} loading={loading}>
            Refresh
          </Button>
          <Button disabled={!item} onClick={() => item && setConfirm(item)}>
            Delete
          </Button>
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            Add provider
          </Button>
        </SpaceBetween>
      }
    >
      <ErrorAlert error={error} />
      <Table
        items={rows}
        loading={loading}
        loadingText="Reading identity providers"
        trackBy="arn"
        selectionType="single"
        selectedItems={selected}
        onSelectionChange={({ detail: change }) => setSelected(change.selectedItems)}
        columnDefinitions={[
          { id: 'name', header: 'Provider name', cell: (row) => row.name, sortingField: 'name' },
          { id: 'type', header: 'Type', cell: (row) => row.type, width: 170 },
          { id: 'created', header: 'Creation time', cell: (row) => row.created || '—' },
          {
            id: 'arn',
            header: 'ARN',
            cell: (row) => <span className="mono">{row.arn}</span>,
          },
        ]}
        empty={<Box textAlign="center">No identity providers.</Box>}
      />

      <Modal
        visible={createOpen}
        onDismiss={() => setCreateOpen(false)}
        header="Add identity provider"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={create}>
                Add provider
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Form>
          <SpaceBetween size="m">
            <FormField label="Provider type">
              <Select
                selectedOption={form.type}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, type: detail.selectedOption }))
                }
                options={[
                  { label: 'OpenID Connect', value: 'oidc' },
                  { label: 'SAML', value: 'saml' },
                ]}
              />
            </FormField>
            {form.type.value === 'oidc' ? (
              <>
                <FormField label="Provider URL">
                  <Input
                    value={form.url}
                    onChange={({ detail }) =>
                      setForm((current) => ({ ...current, url: detail.value }))
                    }
                    placeholder="https://oidc.example.com"
                  />
                </FormField>
                <FormField label="Client ID">
                  <Input
                    value={form.clientId}
                    onChange={({ detail }) =>
                      setForm((current) => ({ ...current, clientId: detail.value }))
                    }
                  />
                </FormField>
                <FormField label="Thumbprint">
                  <Input
                    value={form.thumbprint}
                    onChange={({ detail }) =>
                      setForm((current) => ({ ...current, thumbprint: detail.value }))
                    }
                  />
                </FormField>
              </>
            ) : (
              <>
                <FormField label="Provider name">
                  <Input
                    value={form.name}
                    onChange={({ detail }) =>
                      setForm((current) => ({ ...current, name: detail.value }))
                    }
                    placeholder="corporate-saml"
                  />
                </FormField>
                <FormField label="SAML metadata XML">
                  <Textarea
                    rows={8}
                    value={form.metadata}
                    onChange={({ detail }) =>
                      setForm((current) => ({ ...current, metadata: detail.value }))
                    }
                  />
                </FormField>
              </>
            )}
          </SpaceBetween>
        </Form>
      </Modal>

      <Modal
        visible={Boolean(confirm)}
        onDismiss={() => setConfirm(null)}
        header="Delete identity provider?"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setConfirm(null)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={remove}>
                Delete
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Box>
          This deletes <strong>{confirm?.name}</strong>. Roles that trust it keep their
          trust policy but can no longer assume it.
        </Box>
      </Modal>
    </Page>
  )
}

// ------------------------------------------------------------------- settings

const EMPTY_POLICY_FORM = {
  length: '12',
  maxAge: '',
  reuse: '',
  symbols: true,
  numbers: true,
  upper: true,
  lower: true,
  change: true,
}

function Settings() {
  const iam = useIam()
  const [policy, setPolicy] = useState(null)
  const [aliases, setAliases] = useState([])
  const [alias, setAlias] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(EMPTY_POLICY_FORM)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [policyDoc, aliasDoc] = await Promise.all([
        iam('get-account-password-policy').catch(() => null),
        iam('list-account-aliases').catch(() => null),
      ])
      setPolicy(
        policyDoc
          ? {
              length: text(policyDoc, 'MinimumPasswordLength') || '6',
              maxAge: text(policyDoc, 'MaxPasswordAge'),
              reuse: text(policyDoc, 'PasswordReusePrevention'),
              symbols: text(policyDoc, 'RequireSymbols') === 'true',
              numbers: text(policyDoc, 'RequireNumbers') === 'true',
              upper: text(policyDoc, 'RequireUppercaseCharacters') === 'true',
              lower: text(policyDoc, 'RequireLowercaseCharacters') === 'true',
              change: text(policyDoc, 'AllowUsersToChangePassword') === 'true',
            }
          : null,
      )
      const box = aliasDoc?.getElementsByTagName('AccountAliases')[0]
      setAliases(
        box ? [...box.children].map((child) => child.textContent || '').filter(Boolean) : [],
      )
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [iam])

  useEffect(() => {
    load()
  }, [load])

  const save = async () => {
    setBusy(true)
    setError('')
    try {
      await iam('update-account-password-policy', {
        MinimumPasswordLength: form.length,
        MaxPasswordAge: form.maxAge,
        PasswordReusePrevention: form.reuse,
        RequireSymbols: String(form.symbols),
        RequireNumbers: String(form.numbers),
        RequireUppercaseCharacters: String(form.upper),
        RequireLowercaseCharacters: String(form.lower),
        AllowUsersToChangePassword: String(form.change),
      })
      setEditing(false)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const removePolicy = async () => {
    setBusy(true)
    setError('')
    try {
      await iam('delete-account-password-policy')
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const addAlias = async () => {
    setBusy(true)
    setError('')
    try {
      await iam('create-account-alias', { AccountAlias: alias.trim() })
      setAlias('')
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const removeAlias = async (name) => {
    setBusy(true)
    setError('')
    try {
      await iam('delete-account-alias', { AccountAlias: name })
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Page section="settings">
      <ErrorAlert error={error} />
      <Container
        header={
          <Header
            variant="h2"
            description="Configure the password requirements for IAM users. The emulator stores these; Emuplane's own sign-in still requires at least 8 characters."
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                {policy && (
                  <Button onClick={removePolicy} loading={busy}>
                    Delete policy
                  </Button>
                )}
                <Button
                  onClick={() => {
                    setForm(policy || EMPTY_POLICY_FORM)
                    setEditing(true)
                  }}
                >
                  Edit
                </Button>
              </SpaceBetween>
            }
          >
            Password policy
          </Header>
        }
      >
        {loading ? (
          <Box>Reading the account password policy…</Box>
        ) : policy ? (
          <ColumnLayout columns={2}>
            <div>
              <Box variant="awsui-key-label">Minimum password length</Box>
              <Box>{policy.length} characters</Box>
              <Box variant="awsui-key-label" margin={{ top: 'm' }}>
                Required character types
              </Box>
              <Box>
                {[
                  policy.upper && 'uppercase',
                  policy.lower && 'lowercase',
                  policy.numbers && 'numbers',
                  policy.symbols && 'non-alphanumeric',
                ]
                  .filter(Boolean)
                  .join(', ') || 'none'}
              </Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Other requirements</Box>
              <Box>
                {policy.maxAge ? `Expire after ${policy.maxAge} days` : 'Never expire'}
              </Box>
              <Box>
                {policy.reuse
                  ? `Password reuse prevented for ${policy.reuse} generations`
                  : 'Reuse not restricted'}
              </Box>
              <Box>
                {policy.change ? 'Users may change their own password' : 'Users cannot change it'}
              </Box>
            </div>
          </ColumnLayout>
        ) : (
          <Box color="text-body-secondary">
            No account password policy is set. The emulator's defaults apply.
          </Box>
        )}
      </Container>

      <Container
        header={
          <Header
            variant="h2"
            description="An IAM account alias stored by the emulator. Emuplane's sign-in keeps using the account name shown in the top bar."
          >
            Account alias
          </Header>
        }
      >
        <SpaceBetween size="m">
          {aliases.length ? (
            aliases.map((name) => (
              <SpaceBetween key={name} direction="horizontal" size="s">
                <Box>{name}</Box>
                <Button variant="inline-link" onClick={() => removeAlias(name)}>
                  Delete
                </Button>
              </SpaceBetween>
            ))
          ) : (
            <Box color="text-body-secondary">No alias.</Box>
          )}
          <SpaceBetween direction="horizontal" size="xs">
            <Input
              value={alias}
              onChange={({ detail }) => setAlias(detail.value)}
              placeholder="platform-team"
              ariaLabel="Account alias"
            />
            <Button variant="primary" onClick={addAlias} loading={busy} disabled={!alias.trim()}>
              Create alias
            </Button>
          </SpaceBetween>
        </SpaceBetween>
      </Container>

      <Modal
        visible={editing}
        onDismiss={() => setEditing(false)}
        header="Edit password policy"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setEditing(false)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={save}>
                Save
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Form>
          <SpaceBetween size="m">
            {[
              ['length', 'Minimum password length'],
              ['maxAge', 'Expire after (days)'],
              ['reuse', 'Prevent reuse (generations)'],
            ].map(([key, label]) => (
              <FormField key={key} label={label}>
                <Input
                  value={form[key]}
                  onChange={({ detail }) =>
                    setForm((current) => ({ ...current, [key]: detail.value }))
                  }
                />
              </FormField>
            ))}
            {[
              ['symbols', 'Require symbols'],
              ['numbers', 'Require numbers'],
              ['upper', 'Require uppercase characters'],
              ['lower', 'Require lowercase characters'],
              ['change', 'Allow users to change their password'],
            ].map(([key, label]) => (
              <Checkbox
                key={key}
                checked={form[key]}
                onChange={({ detail }) =>
                  setForm((current) => ({ ...current, [key]: detail.checked }))
                }
              >
                {label}
              </Checkbox>
            ))}
          </SpaceBetween>
        </Form>
      </Modal>
    </Page>
  )
}

// ------------------------------------------------------------------- report

function Report() {
  const { account } = useSession()
  const iam = useIam()
  const [state, setState] = useState(null)
  const [generated, setGenerated] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const download = async () => {
    setBusy(true)
    setError('')
    try {
      const generatedDoc = await iam('generate-credential-report')
      setState(text(generatedDoc, 'State') || 'COMPLETE')
      const report = await iam('get-credential-report')
      const content = text(report, 'Content')
      const csv = content ? atob(content) : ''
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `credential-report-${account}.csv`
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setGenerated(text(report, 'GeneratedTime'))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Page section="report">
      <ErrorAlert error={error} />
      <Container
        header={
          <Header
            variant="h2"
            description="Lists every IAM user in this account and the state of its credentials. The emulator regenerates it on every request."
          >
            Credentials report
          </Header>
        }
      >
        <SpaceBetween size="m">
          <Box>
            The emulator regenerates the report on every request and answers with the
            CSV download.
          </Box>
          <SpaceBetween direction="horizontal" size="s">
            <Button variant="primary" loading={busy} onClick={download}>
              Generate and download report
            </Button>
            {state && <StatusIndicator type="success">{state}</StatusIndicator>}
          </SpaceBetween>
          {generated && (
            <Box color="text-body-secondary">Generated {generated}.</Box>
          )}
        </SpaceBetween>
      </Container>
    </Page>
  )
}

// ---------------------------------------------------------------------- entry

const PAGES = {
  dashboard: IAMDashboard,
  users: Users,
  groups: Groups,
  roles: Roles,
  policies: Policies,
  providers: Providers,
  settings: Settings,
  report: Report,
}

export default function IAMSection({ section = 'dashboard' }) {
  const Chosen = useMemo(() => PAGES[section] || Dashboard, [section])
  return <Chosen />
}
