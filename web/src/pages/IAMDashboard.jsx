// IAM Dashboard: security recommendations for the signed-in identity, the account card, and the resource counts.

import { useCallback, useEffect, useMemo, useState } from 'react'
import Alert from '@cloudscape-design/components/alert'
import Badge from '@cloudscape-design/components/badge'
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
import Modal from '@cloudscape-design/components/modal'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import Table from '@cloudscape-design/components/table'
import qrcode from 'qrcode-generator'
import { api } from '../api'
import { useSession } from '../context'
import { Shell } from '../components/Shell'
import { members, parseIam, summary, text } from '../iam'

async function call(account, region, operation, params = {}) {
  const result = await api.exec({ account, region, service: 'iam', operation, params })
  if (!result.ok) throw new Error(result.error || `IAM ${operation} failed`)
  return parseIam(result.body)
}

export default function IAMDashboard() {
  const { account, region, meta, me } = useSession()
  const [facts, setFacts] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [aliasOpen, setAliasOpen] = useState(false)
  const [aliasDraft, setAliasDraft] = useState('')
  const [mfaOpen, setMfaOpen] = useState(false)
  const [mfa, setMfa] = useState(null)
  const [code, setCode] = useState('')

  const iam = useCallback(
    (operation, params) => call(account, region, operation, params),
    [account, region],
  )
  const isRoot = (me?.role || '') === 'root'
  const consoleBase = (meta?.console || window.location.origin).replace(/\/$/, '')
  const consoleUrl = facts?.alias
    ? `${consoleBase}/login?account=${encodeURIComponent(facts.alias)}`
    : `${consoleBase}/login`

  const qrSrc = useMemo(() => {
    if (!mfa?.seed) return ''
    const uri = `otpauth://totp/${encodeURIComponent(`Emuplane:${me?.user || ''}`)}?secret=${encodeURIComponent(
      mfa.seed,
    )}&issuer=Emuplane`
    try {
      const qr = qrcode(0, 'M')
      qr.addData(uri)
      qr.make()
      return qr.createDataURL(4, 8)
    } catch {
      return ''
    }
  }, [mfa, me?.user])

  const load = useCallback(async () => {
    try {
      const [summaryDoc, aliasDoc, users, groups, roles, policies, oidc, saml, mfaStatus] =
        await Promise.all([
          iam('get-account-summary'),
          iam('list-account-aliases').catch(() => null),
          iam('list-users'),
          iam('list-groups'),
          iam('list-roles'),
          iam('list-policies'),
          iam('list-open-id-connect-providers'),
          iam('list-saml-providers'),
          api.mfa().catch(() => null),
        ])
      let keyCount = 0
      if (!isRoot && me?.user) {
        const keysDoc = await iam('list-access-keys', { UserName: me.user }).catch(
          () => null,
        )
        keyCount = members(keysDoc, 'AccessKeyMetadata').length
      }
      const aliasBox = aliasDoc?.getElementsByTagName('AccountAliases')[0]
      const alias = aliasBox
        ? [...aliasBox.children]
            .map((child) => child.textContent || '')
            .filter(Boolean)[0] || ''
        : ''
      setFacts({
        summary: summary(summaryDoc),
        alias,
        keyCount,
        mfa: mfaStatus || { enabled: false, serial: '', devices: [] },
        counts: {
          users: members(users, 'Users').length,
          groups: members(groups, 'Groups').length,
          roles: members(roles, 'Roles').length,
          policies: members(policies, 'Policies').length,
          providers:
            members(oidc, 'OpenIDConnectProviderList').length +
            members(saml, 'SAMLProviderList').length,
        },
      })
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [iam, isRoot, me?.user])

  useEffect(() => {
    load()
  }, [load])

  const saveAlias = async () => {
    setBusy(true)
    setError('')
    try {
      await iam('create-account-alias', { AccountAlias: aliasDraft.trim() })
      setAliasOpen(false)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const removeAlias = async () => {
    setBusy(true)
    setError('')
    try {
      await iam('delete-account-alias', { AccountAlias: facts.alias })
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const startMfa = async () => {
    setBusy(true)
    setError('')
    try {
      const device = await api.startMfa()
      setMfa(device)
      setCode('')
      setMfaOpen(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const enableMfa = async () => {
    setBusy(true)
    setError('')
    try {
      await api.enrolMfa({ serial: mfa.serial, seed: mfa.seed, code })
      setMfaOpen(false)
      setMfa(null)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const removeMfa = async (serial) => {
    setBusy(true)
    setError('')
    try {
      await api.disableMfa(serial)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const rootMfa = facts?.summary?.AccountMFAEnabled === '1'
  const rows = []
  if (isRoot) {
    rows.push({
      type: rootMfa ? 'success' : 'warning',
      title: rootMfa ? 'Root user has MFA' : 'Root user has no MFA',
      text: 'Multi-factor authentication (MFA) for the root user improves security for this account.',
    })
  } else {
    rows.push({
      type: rootMfa ? 'success' : 'warning',
      title: rootMfa ? 'Root user has MFA' : 'Root user has no MFA',
      text: 'The account summary reports whether an MFA device is in use for the root user.',
    })
    rows.push({
      type: facts?.mfa?.enabled ? 'success' : 'warning',
      title: facts?.mfa?.enabled
        ? 'MFA is enabled for your user'
        : 'Add MFA for yourself',
      text: 'Add multi-factor authentication (MFA) for yourself to improve security for this account.',
      action: facts?.mfa?.enabled ? (
        <Button loading={busy} onClick={() => removeMfa()}>
          Remove MFA
        </Button>
      ) : (
        <Button onClick={startMfa} loading={busy}>
          Add MFA
        </Button>
      ),
    })
  }
  if (!isRoot) {
    rows.push({
      type: 'info',
      title: `Your user, ${me?.user || ''}, holds ${facts?.keyCount ?? 0} access key(s)`,
      text: 'The emulator does not report per-key usage, so unused-key advice is unavailable.',
    })
  } else {
    rows.push({
      type: facts?.summary?.AccountAccessKeysPresent === '0' ? 'success' : 'warning',
      title:
        facts?.summary?.AccountAccessKeysPresent === '0'
          ? 'Root user has no active access keys'
          : 'Root user has active access keys',
      text: 'Using access keys attached to an IAM user instead of the root user improves security.',
    })
  }
  const warnings = rows.filter((row) => row.type === 'warning').length

  const counts = [
    ['User groups', facts?.counts?.groups],
    ['Users', facts?.counts?.users],
    ['Roles', facts?.counts?.roles],
    ['Policies', facts?.counts?.policies],
    ['Identity providers', facts?.counts?.providers],
  ]
  const devices = facts?.mfa?.devices || []

  return (
    <Shell
      activeHref="/iam/dashboard"
      breadcrumbs={[
        { text: 'IAM', href: '/iam/dashboard' },
        { text: 'IAM Dashboard' },
      ]}
    >
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="Security recommendations, the account behind this console, and what IAM holds."
          >
            IAM Dashboard
          </Header>
        }
      >
        <SpaceBetween size="l">
          {error && <Alert type="error">{error}</Alert>}
          <ColumnLayout columns={3}>
            <div style={{ gridColumn: 'span 2' }}>
              <SpaceBetween size="l">
                <Container
                  header={
                    <Header
                      variant="h2"
                      counter={
                        <Badge color={warnings ? 'red' : 'green'}>{warnings}</Badge>
                      }
                      description="What the emulator reports for this account."
                      actions={
                        <Button
                          iconName="refresh"
                          variant="icon"
                          ariaLabel="Refresh"
                          onClick={load}
                        />
                      }
                    >
                      Security recommendations
                    </Header>
                  }
                >
                  <SpaceBetween size="l">
                    {rows.map((row) => (
                      <SpaceBetween key={row.title} size="xs">
                        <SpaceBetween direction="horizontal" size="m">
                          <StatusIndicator type={row.type}>{row.title}</StatusIndicator>
                          {row.action}
                        </SpaceBetween>
                        <Box color="text-body-secondary" fontSize="body-s">
                          {row.text}
                        </Box>
                      </SpaceBetween>
                    ))}
                  </SpaceBetween>
                </Container>

                <Container header={<Header variant="h2">IAM resources</Header>}>
                  <ColumnLayout columns={5} variant="text-grid">
                    {counts.map(([label, value]) => (
                      <div key={label}>
                        <Box variant="awsui-key-label">{label}</Box>
                        <Box fontSize="display-l">{value ?? '—'}</Box>
                      </div>
                    ))}
                  </ColumnLayout>
                </Container>
              </SpaceBetween>
            </div>

            <SpaceBetween size="l">
              <Container header={<Header variant="h2">AWS account</Header>}>
                <SpaceBetween size="m">
                  <div>
                    <Box variant="awsui-key-label">Account ID</Box>
                    <CopyToClipboard
                      variant="inline"
                      textToCopy={account || ''}
                      textToDisplay={<span className="mono">{account}</span>}
                      copyButtonAriaLabel="Copy account ID"
                      copySuccessText="Account ID copied"
                      copyErrorText="Could not copy the account ID"
                      wrapText={false}
                    />
                  </div>
                  <div>
                    <Box variant="awsui-key-label">Account alias</Box>
                    <SpaceBetween direction="horizontal" size="xs">
                      <Box>{facts?.alias || '—'}</Box>
                      <Button
                        variant="inline-link"
                        onClick={() => {
                          setAliasDraft(facts?.alias || '')
                          setAliasOpen(true)
                        }}
                      >
                        Edit
                      </Button>
                      {facts?.alias && (
                        <Button variant="inline-link" onClick={removeAlias} loading={busy}>
                          Delete
                        </Button>
                      )}
                    </SpaceBetween>
                    <Box color="text-body-secondary" fontSize="body-s">
                      The emulator's IAM alias; Emuplane's sign-in uses the account name in
                      the top bar.
                    </Box>
                  </div>
                  <div>
                    <Box variant="awsui-key-label">
                      Sign-in URL for IAM users in this account
                    </Box>
                    <CopyToClipboard
                      variant="inline"
                      textToCopy={consoleUrl}
                      textToDisplay={<span className="mono">{consoleUrl}</span>}
                      copyButtonAriaLabel="Copy sign-in URL"
                      copySuccessText="Sign-in URL copied"
                      copyErrorText="Could not copy the sign-in URL"
                      wrapText={false}
                    />
                  </div>
                </SpaceBetween>
              </Container>

              <Container
                header={
                  <Header
                    variant="h2"
                    description="Virtual devices the emulator holds. Unassigned devices can be removed."
                  >
                    MFA devices
                  </Header>
                }
              >
                <Table
                  items={devices}
                  trackBy="serial"
                  variant="embedded"
                  columnDefinitions={[
                    {
                      id: 'serial',
                      header: 'Serial number',
                      cell: (device) => <span className="mono">{device.serial}</span>,
                    },
                    {
                      id: 'user',
                      header: 'Assigned to',
                      cell: (device) => device.user || '—',
                      width: 130,
                    },
                    {
                      id: 'action',
                      header: '',
                      cell: (device) =>
                        device.user ? (
                          <Box color="text-body-secondary" fontSize="body-s">
                            {device.user === me?.user ? 'This user' : 'Another user'}
                          </Box>
                        ) : (
                          <Button
                            variant="inline-link"
                            loading={busy}
                            onClick={() => removeMfa(device.serial)}
                          >
                            Remove
                          </Button>
                        ),
                      width: 120,
                    },
                  ]}
                  empty={<Box color="text-body-secondary">No virtual MFA devices.</Box>}
                />
              </Container>
            </SpaceBetween>
          </ColumnLayout>
        </SpaceBetween>
      </ContentLayout>

      <Modal
        visible={aliasOpen}
        onDismiss={() => setAliasOpen(false)}
        header="Account alias"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setAliasOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                loading={busy}
                disabled={!aliasDraft.trim()}
                onClick={saveAlias}
              >
                Save
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Form>
          <FormField
            label="Alias"
            description="The emulator stores one alias; saving replaces the current one."
          >
            <Input
              value={aliasDraft}
              onChange={({ detail }) => setAliasDraft(detail.value)}
              placeholder="platform-team"
            />
          </FormField>
        </Form>
      </Modal>

      <Modal
        visible={mfaOpen}
        onDismiss={() => setMfaOpen(false)}
        header="Add MFA device"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setMfaOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                loading={busy}
                disabled={!/^\d{6}$/.test(code)}
                onClick={enableMfa}
              >
                Add device
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <Form>
          <SpaceBetween size="m">
            <Box>
              Add <strong>{mfa?.serial}</strong> to your authenticator app by scanning
              the QR code, or by entering the seed by hand when the app cannot scan it.
            </Box>
            <div>
              <Box variant="awsui-key-label">Serial number</Box>
              <CopyToClipboard
                variant="inline"
                textToCopy={mfa?.serial || ''}
                textToDisplay={<span className="mono">{mfa?.serial}</span>}
                copyButtonAriaLabel="Copy serial number"
                copySuccessText="Serial number copied"
                copyErrorText="Could not copy the serial number"
                wrapText={false}
              />
            </div>
            {qrSrc && (
              <div>
                <Box variant="awsui-key-label">QR code</Box>
                <img
                  src={qrSrc}
                  alt="QR code for the virtual MFA device"
                  width="180"
                  height="180"
                />
              </div>
            )}
            <div>
              <Box variant="awsui-key-label">Base32 seed</Box>
              <CopyToClipboard
                variant="inline"
                textToCopy={mfa?.seed || ''}
                textToDisplay={<span className="mono">{mfa?.seed}</span>}
                copyButtonAriaLabel="Copy seed"
                copySuccessText="Seed copied"
                copyErrorText="Could not copy the seed"
                wrapText={false}
              />
            </div>
            <FormField
              label="Code"
              description="The six-digit code from the app after you add the device."
            >
              <Input
                value={code}
                onChange={({ detail }) => setCode(detail.value)}
                placeholder="123456"
              />
            </FormField>
            <Box color="text-body-secondary" fontSize="body-s">
              The code is checked here, and the emulator records the device. A sign-in
              for this user then asks for a code before it finishes.
            </Box>
          </SpaceBetween>
        </Form>
      </Modal>
    </Shell>
  )
}
