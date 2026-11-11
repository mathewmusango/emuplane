import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import ContentLayout from '@cloudscape-design/components/content-layout'
import CopyToClipboard from '@cloudscape-design/components/copy-to-clipboard'
import Header from '@cloudscape-design/components/header'
import Modal from '@cloudscape-design/components/modal'
import SpaceBetween from '@cloudscape-design/components/space-between'
import Tabs from '@cloudscape-design/components/tabs'
import Table from '@cloudscape-design/components/table'
import Link from '@cloudscape-design/components/link'
import { api } from '../api'
import { useSession } from '../context'
import { Shell } from '../components/Shell'

const mask = (key) => (key ? `${key.slice(0, 4)}••••${key.slice(-2)}` : '—')

export default function Accounts() {
  const navigate = useNavigate()
  const { account, setAccount, meta, refresh } = useSession()
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [confirming, setConfirming] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const [savingAdmin, setSavingAdmin] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setAccounts(await api.users())
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  const remove = async () => {
    if (!confirming) return
    setDeleting(true)
    setError('')
    try {
      await api.deleteAccount(confirming.account_id)
      setConfirming(null)
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setDeleting(false)
    }
  }

  const toggleAdmin = async (item, enabled) => {
    setSavingAdmin(item.account_id)
    setError('')
    try {
      await api.setGlobalAdmin(item.account_id, enabled)
      await load()
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingAdmin('')
    }
  }

  const toggleDisabled = async (item, disabled) => {
    setSavingAdmin(item.account_id)
    setError('')
    try {
      await api.setAccountDisabled(item.account_id, disabled)
      await load()
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingAdmin('')
    }
  }

  const admins = accounts.filter((item) => item.global_admin)

  useEffect(() => {
    load()
  }, [load])

  const accountsTable = (
    <Table
      items={accounts}
      loading={loading}
      loadingText="Reading accounts"
      trackBy="account_id"
      columnDefinitions={[
        {
          id: 'account',
          header: 'Account ID',
          cell: (item) => (
            <CopyToClipboard
              variant="inline"
              textToCopy={item.account_id}
              textToDisplay={<span className="mono">{item.account_id}</span>}
              copyButtonAriaLabel={`Copy account ${item.account_id}`}
              copySuccessText="Account ID copied"
              copyErrorText="Could not copy the account ID"
              wrapText={false}
            />
          ),
          width: 170,
        },
        { id: 'alias', header: 'Alias', cell: (item) => item.alias },
        {
          id: 'name',
          header: 'Name',
          cell: (item) => item.name || <Box color="text-body-secondary">—</Box>,
        },
        {
          id: 'admin',
          header: 'Global admin',
          cell: (item) => (item.global_admin ? 'Yes' : 'No'),
          width: 130,
        },
        {
          id: 'state',
          header: 'Status',
          cell: (item) =>
            item.disabled
              ? 'Disabled'
              : item.default_admin
                ? 'Enabled · default'
                : 'Enabled',
          width: 160,
        },
        {
          id: 'regions',
          header: 'Regions',
          cell: (item) => (
            <Link
              href="/settings"
              onFollow={(event) => {
                event.preventDefault()
                navigate('/settings')
              }}
            >
              Manage regions ({(item.regions || []).length} enabled)
            </Link>
          ),
        },
        {
          id: 'users',
          header: 'Principals',
          cell: (item) => (item.users || []).length,
          width: 110,
        },
        {
          id: 'principals',
          header: 'Users',
          cell: (item) =>
            (item.users || [])
              .map((user) => `${user.username} (${user.role})`)
              .join(', '),
        },
        {
          id: 'use',
          header: '',
          cell: (item) =>
            item.account_id === account ? (
              <Box color="text-status-success">Selected</Box>
            ) : (
              <SpaceBetween direction="horizontal" size="xs">
                {meta?.platform_admin && (
                  <Button
                    variant="inline-link"
                    loading={savingAdmin === item.account_id}
                    onClick={() => toggleAdmin(item, !item.global_admin)}
                  >
                    {item.global_admin ? 'Remove global admin' : 'Make global admin'}
                  </Button>
                )}
                {meta?.platform_admin && (
                  <Button
                    variant="inline-link"
                    loading={savingAdmin === item.account_id}
                    onClick={() => toggleDisabled(item, !item.disabled)}
                  >
                    {item.disabled ? 'Enable account' : 'Disable account'}
                  </Button>
                )}
                {meta?.platform_admin && (
                  <Button
                    variant="inline-link"
                    onClick={() => setConfirming(item)}
                  >
                    Delete
                  </Button>
                )}
              </SpaceBetween>
            ),
          width: 340,
        },
      ]}
      header={<Header counter={`(${accounts.length})`}>Root accounts</Header>}
      empty={<Box textAlign="center">No accounts yet.</Box>}
    />
  )

  const adminsTable = (
    <Table
      items={admins}
      loading={loading}
      trackBy="account_id"
      columnDefinitions={[
        {
          id: 'account',
          header: 'Account ID',
          cell: (item) => (
            <CopyToClipboard
              variant="inline"
              textToCopy={item.account_id}
              textToDisplay={<span className="mono">{item.account_id}</span>}
              copyButtonAriaLabel={`Copy account ${item.account_id}`}
              copySuccessText="Account ID copied"
              copyErrorText="Could not copy the account ID"
              wrapText={false}
            />
          ),
          width: 170,
        },
        { id: 'alias', header: 'Alias', cell: (item) => item.alias },
        {
          id: 'name',
          header: 'Name',
          cell: (item) => item.name || <Box color="text-body-secondary">—</Box>,
        },
        {
          id: 'users',
          header: 'Users',
          cell: (item) =>
            (item.users || []).map((user) => user.username).join(', '),
        },
        {
          id: 'regions',
          header: 'Regions',
          cell: (item) => (
            <Link
              href="/settings"
              onFollow={(event) => {
                event.preventDefault()
                navigate('/settings')
              }}
            >
              Manage regions ({(item.regions || []).length} enabled)
            </Link>
          ),
        },
      ]}
      header={
        <Header counter={`(${admins.length})`} description="Global admins see every account and can create root accounts.">
          Global admins
        </Header>
      }
      empty={<Box textAlign="center">No global admins.</Box>}
    />
  )

  return (
    <Shell
      activeHref="/accounts"
      breadcrumbs={[{ text: 'Accounts', href: '/accounts' }]}
    >
      <ContentLayout
        header={
          <Header
            variant="h1"
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button iconName="refresh" onClick={load}>
                  Refresh
                </Button>
                {meta?.platform_admin && (
                  <Button variant="primary" onClick={() => navigate('/onboarding')}>
                    Provision account
                  </Button>
                )}
              </SpaceBetween>
            }
          >
            Accounts
          </Header>
        }
      >
        <SpaceBetween size="l">
          {error && <Alert type="error">{error}</Alert>}

          <Tabs
            tabs={[
              {
                id: 'accounts',
                label: `Root accounts (${accounts.length})`,
                content: accountsTable,
              },
              ...(meta?.platform_admin
                ? [
                    {
                      id: 'admins',
                      label: `Global admins (${admins.length})`,
                      content: adminsTable,
                    },
                  ]
                : []),
            ]}
          />

          <Modal
            visible={Boolean(confirming)}
            onDismiss={() => setConfirming(null)}
            header="Delete account?"
            footer={
              <Box float="right">
                <SpaceBetween direction="horizontal" size="xs">
                  <Button variant="link" onClick={() => setConfirming(null)}>
                    Cancel
                  </Button>
                  <Button variant="primary" loading={deleting} onClick={remove}>
                    Delete account
                  </Button>
                </SpaceBetween>
              </Box>
            }
          >
            <SpaceBetween size="s">
              <Box>
                This removes account <code>{confirming?.account_id}</code> (
                {confirming?.alias}), its local logins and its IAM users.
              </Box>
              <Box>
                Deleting a root account also deletes all the resources attached to it.
              </Box>
              <Box color="text-status-warning">This cannot be undone.</Box>
            </SpaceBetween>
          </Modal>
        </SpaceBetween>
      </ContentLayout>
    </Shell>
  )
}
