import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Badge from '@cloudscape-design/components/badge'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import CollectionPreferences from '@cloudscape-design/components/collection-preferences'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Flashbar from '@cloudscape-design/components/flashbar'
import Form from '@cloudscape-design/components/form'
import FormField from '@cloudscape-design/components/form-field'
import Header from '@cloudscape-design/components/header'
import Input from '@cloudscape-design/components/input'
import Modal from '@cloudscape-design/components/modal'
import Pagination from '@cloudscape-design/components/pagination'
import Select from '@cloudscape-design/components/select'
import SideNavigation from '@cloudscape-design/components/side-navigation'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import Table from '@cloudscape-design/components/table'

import Textarea from '@cloudscape-design/components/textarea'
import TextFilter from '@cloudscape-design/components/text-filter'
import Toggle from '@cloudscape-design/components/toggle'
import { useCollection } from '@cloudscape-design/collection-hooks'
import { api } from '../api'
import { useSession } from '../context'
import { useFavorites, useRecent } from '../prefs'
import { ServiceIcon } from '../serviceIcons'
import { serviceLabel } from '../serviceLabels'
import { Shell, loadCatalogue } from '../components/Shell'

const FIELD_DEFAULTS = (fields) =>
  Object.fromEntries((fields || []).map((item) => [item.name, item.default || '']))

function pretty(body) {
  if (!body) return ''
  try {
    return JSON.stringify(JSON.parse(body), null, 2)
  } catch {
    return body
  }
}

export default function Resources() {
  const { service: routeService } = useParams()
  const navigate = useNavigate()
  const { account, region, meta } = useSession()
  const { toggleFavorite, isFavorite } = useFavorites()
  const { addRecent } = useRecent()

  const service = routeService || 's3'
  const [catalogue, setCatalogue] = useState(null)
  const [rows, setRows] = useState([])
  const [preferences, setPreferences] = useState({
    pageSize: 20,
    contentDensity: 'comfortable',
  })
  const [flash, setFlash] = useState([])
  const [confirming, setConfirming] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [operation, setOperation] = useState(null)
  const [params, setParams] = useState({})
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [activeTab, setActiveTab] = useState('')
  const [allRegions, setAllRegions] = useState(false)
  const [regions, setRegions] = useState([])
  const [bucket, setBucket] = useState('')
  const [objects, setObjects] = useState([])
  const [objectsLoading, setObjectsLoading] = useState(false)
  const [selected, setSelected] = useState([])
  const [confirmingDelete, setConfirmingDelete] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [creating, setCreating] = useState(false)
  const [newBucket, setNewBucket] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    loadCatalogue().then(setCatalogue).catch(() => setCatalogue(null))
  }, [])

  const spec = catalogue?.services?.[service]
  const operations = spec?.operations || []

  useEffect(() => {
    setOperation(operations[0] || null)
    setParams(FIELD_DEFAULTS(operations[0]?.params))
    setResult(null)
  }, [service, catalogue])

  const load = useCallback(async () => {
    if (!account) return
    setLoading(true)
    try {
      const payload = await api.browse(account, allRegions ? 'all' : region, service)
      setRows(payload.resources || [])
      setRegions(payload.regions || [])
      setError('')
    } catch (err) {
      setError(err.message)
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [account, allRegions, region, service])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    addRecent(service)
  }, [service, addRecent])

  const serviceOptions = useMemo(() => {
    const groups = catalogue?.groups || []
    return groups.map((group) => ({
      label: group.label,
      options: group.services.map((name) => ({
        label: catalogue?.services?.[name]
          ? `${serviceLabel(name)} · ${catalogue.services[name].operations.length} actions`
          : serviceLabel(name),
        value: name,
      })),
    }))
  }, [catalogue])

  const kinds = useMemo(() => [...new Set(rows.map((row) => row.kind))], [rows])
  const countsByKind = useMemo(() => {
    const map = {}
    for (const row of rows) map[row.kind] = (map[row.kind] || 0) + 1
    return map
  }, [rows])

  useEffect(() => {
    setActiveTab((current) => (current && !kinds.includes(current) ? '' : current))
  }, [kinds])

  useEffect(() => {
    setBucket('')
    setObjects([])
    setSelected([])
  }, [service])

  const removeBucket = async () => {
    if (!confirmingDelete) return
    setBusy(true)
    try {
      const payload = await api.exec({
        account,
        region,
        service: 's3',
        operation: 'delete-bucket',
        params: { Bucket: confirmingDelete },
      })
      if (payload.ok) {
        addFlash('success', `Bucket ${confirmingDelete} deleted.`)
        setConfirmingDelete(null)
        setSelected([])
        load()
      } else {
        addFlash('error', payload.error || 'Could not delete the bucket.')
      }
    } catch (err) {
      addFlash('error', err.message)
    } finally {
      setBusy(false)
    }
  }

  const createBucket = async () => {
    if (!newBucket.trim()) return
    setBusy(true)
    try {
      const payload = await api.exec({
        account,
        region,
        service: 's3',
        operation: 'create-bucket',
        params: { Bucket: newBucket.trim() },
      })
      if (payload.ok) {
        addFlash('success', `Bucket ${newBucket.trim()} created.`)
        setCreating(false)
        setNewBucket('')
        load()
      } else {
        addFlash('error', payload.error || 'Could not create the bucket.')
      }
    } catch (err) {
      addFlash('error', err.message)
    } finally {
      setBusy(false)
    }
  }

  const openBucket = async (name) => {
    setBucket(name)
    setObjectsLoading(true)
    try {
      const payload = await api.s3Objects(account, region, name)
      setObjects(payload.objects || [])
    } catch (err) {
      addFlash('error', err.message)
      setObjects([])
    } finally {
      setObjectsLoading(false)
    }
  }

  const visible = useMemo(
    () => (activeTab ? rows.filter((row) => row.kind === activeTab) : rows),
    [rows, activeTab],
  )

  const { items: visibleRows, collectionProps, paginationProps, filterProps } =
    useCollection(visible, {
      filtering: {},
      sorting: {},
      pagination: { pageSize: preferences.pageSize },
    })

  const selectOperation = (next) => {
    setOperation(next)
    setParams(FIELD_DEFAULTS(next?.params))
    setResult(null)
  }

  const addFlash = (type, content) => {
    const id = `flash-${Date.now()}-${Math.random().toString(16).slice(2)}`
    setFlash([
      {
        id,
        type,
        content,
        dismissible: true,
        onDismiss: () =>
          setFlash((current) => current.filter((item) => item.id !== id)),
      },
    ])
  }

  const run = async (target = operation) => {
    if (!target) return
    setRunning(true)
    try {
      const payload = await api.exec({
        account,
        region,
        service,
        operation: target.id,
        params,
      })
      setResult(payload)
      if (payload.ok) {
        addFlash('success', `${target.label} succeeded (HTTP ${payload.status}).`)
        load()
      } else {
        addFlash('error', `${target.label} failed: ${payload.error || `HTTP ${payload.status}`}.`)
      }
    } catch (err) {
      setResult({ ok: false, error: err.message })
      addFlash('error', err.message)
    } finally {
      setRunning(false)
    }
  }

  // Destructive operations follow the delete pattern: explicit confirmation.
  const requestRun = () => {
    if (!operation) return
    if (operation.destructive) {
      setConfirming(operation)
      return
    }
    run(operation)
  }

  const resourceTable = (
    <Table
      {...collectionProps}
      items={visibleRows}
      loading={loading}
      loadingText="Reading resources"
      trackBy={(item) => `${item.region || ''}/${item.kind}/${item.name}`}
      columnDefinitions={[
        {
          id: 'kind',
          header: 'Kind',
          cell: (item) => item.kind,
          sortingField: 'kind',
          width: 130,
        },
        {
          id: 'name',
          header: 'Name',
          cell: (item) => <span className="mono">{item.name}</span>,
          sortingField: 'name',
        },
        ...(allRegions
          ? [
              {
                id: 'region',
                header: 'Region',
                cell: (item) => <span className="mono">{item.region || '—'}</span>,
                sortingField: 'region',
                width: 150,
              },
            ]
          : []),
        {
          id: 'detail',
          header: 'Detail',
          cell: (item) =>
            [
              ...Object.entries(item.detail || {})
                .filter(([, value]) => value)
                .map(([key, value]) => `${key}=${value}`),
              item.owner?.user ? `created by ${item.owner.user}` : '',
            ]
              .filter(Boolean)
              .join(' · '),
        },
        {
          id: 'open',
          header: '',
          cell: (item) =>
            item.kind === 'bucket' ? (
              <Button variant="inline-link" onClick={() => openBucket(item.name)}>
                Open
              </Button>
            ) : null,
          width: 90,
        },
      ]}
      filter={<TextFilter {...filterProps} filteringPlaceholder="Find a resource" />}
      pagination={<Pagination {...paginationProps} />}
      preferences={
        <CollectionPreferences
          title="Resource preferences"
          confirmLabel="Confirm"
          cancelLabel="Cancel"
          preferences={preferences}
          onConfirm={({ detail }) => setPreferences(detail)}
          pageSizePreference={{
            title: 'Page size',
            options: [10, 20, 50].map((value) => ({
              value,
              label: `${value} resources`,
            })),
          }}
          contentDensityPreference={{
            title: 'Content density',
            description: 'Use compact mode to fit more resources on screen.',
          }}
        />
      }
      contentDensity={preferences.contentDensity}
      {...(service === 's3'
        ? {
            selectionType: 'single',
            selectedItems: selected,
            onSelectionChange: ({ detail }) => setSelected(detail.selectedItems),
          }
        : {})}
      header={
        <Header
          counter={`(${visible.length})`}
          description={spec?.description}
          actions={
            service === 's3' ? (
              <SpaceBetween direction="horizontal" size="xs">
                <Button
                  disabled={!selected.length}
                  onClick={() => {
                    setDeleteConfirm('')
                    setConfirmingDelete(selected[0].name)
                  }}
                >
                  Delete
                </Button>
                <Button
                  variant="primary"
                  onClick={() => {
                    setNewBucket('')
                    setCreating(true)
                  }}
                >
                  Create bucket
                </Button>
              </SpaceBetween>
            ) : undefined
          }
        >
          {serviceLabel(service)} resources
        </Header>
      }
      empty={
        <Box textAlign="center">
          <SpaceBetween size="s">
            <Box color="text-body-secondary">
              Nothing in this account{allRegions ? '' : ' and region'} yet.
            </Box>
            <Button iconName="refresh" onClick={load}>
              Refresh
            </Button>
          </SpaceBetween>
        </Box>
      }
    />
  )

  return (
    <Shell
      activeHref="/resources"
      breadcrumbs={[
        { text: 'Resources', href: '/resources' },
        { text: service, href: `/resources/${service}` },
      ]}
    >
      <ContentLayout
        header={
          <Header
            variant="h1"
            description={
              spec?.description ||
              'Read-only view. This service has no GUI actions defined yet.'
            }
            info={
              operations.length === 0 ? <Badge color="grey">Read-only</Badge> : undefined
            }
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button
                  variant="icon"
                  iconName={isFavorite(service) ? 'star-filled' : 'star'}
                  ariaLabel={isFavorite(service) ? 'Unfavorite service' : 'Favorite service'}
                  onClick={() => toggleFavorite(service)}
                />
                <Button iconName="refresh" onClick={load}>
                  Refresh
                </Button>
              </SpaceBetween>
            }
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <ServiceIcon name={service} size={22} />
              {serviceLabel(service)}
            </span>
          </Header>
        }
      >
        <SpaceBetween size="l">
          {flash.length > 0 && <Flashbar items={flash} />}
          <Container>
            <SpaceBetween size="s">
              <Select
                selectedOption={
                  serviceOptions
                    .flatMap((group) => group.options)
                    .find((option) => option.value === service) || null
                }
                onChange={({ detail }) =>
                  detail.selectedOption?.value &&
                  navigate(`/resources/${detail.selectedOption.value}`)
                }
                options={serviceOptions}
                placeholder="Choose a service"
                ariaLabel="Service"
              />
              <Toggle
                checked={allRegions}
                onChange={({ detail }) => setAllRegions(detail.checked)}
                description="List this service across every region this account has enabled. Actions and bucket contents still use the region selected in the header."
              >
                View from all regions
              </Toggle>
              <Box color="text-body-secondary" fontSize="body-s">
                Account <code>{account}</code> ·{' '}
                {allRegions ? (
                  <>
                    regions <code>{regions.join(', ') || '—'}</code>
                  </>
                ) : (
                  <>
                    region <code>{region}</code>
                  </>
                )}
                {meta?.accounts_scope === 'global' &&
                  ' · the account spans every region'}
              </Box>
            </SpaceBetween>
          </Container>

          {error && (
            <Alert type="error" header="Could not read this service">
              {error}
            </Alert>
          )}

          {service === 's3' && (
            <Alert type="info" header="S3 bucket names are global">
              MiniStack does not isolate S3 per region, so a bucket created in one
              region is visible from every region of the same account. The region
              shown against a bucket is the one recorded when its name was claimed,
              not the region being queried. Every other service is
              region-isolated.
            </Alert>
          )}

          {service === 'iam' && (
            <Alert type="info" header="The account root is not an IAM user">
              The 12-digit account identity is the root of the account. IAM users
              below are separate principals created inside it.
            </Alert>
          )}

          {operations.length > 0 ? (
            <Container
              header={
                <Header
                  variant="h2"
                  description="Each action is the AWS API call the CLI would make, signed as this account's root."
                >
                  Actions
                </Header>
              }
            >
              <Form
                actions={
                  <SpaceBetween direction="horizontal" size="xs">
                    <Button
                      variant="primary"
                      onClick={requestRun}
                      loading={running}
                      disabled={!operation}
                    >
                      Run
                    </Button>
                    {operation?.cli && (
                      <Box color="text-body-secondary" fontSize="body-s">
                        <code>{operation.cli}</code>
                      </Box>
                    )}
                  </SpaceBetween>
                }
              >
                <SpaceBetween size="m">
                  <FormField label="Operation">
                    <Select
                      selectedOption={
                        operation
                          ? { label: operation.label, value: operation.id }
                          : null
                      }
                      onChange={({ detail }) =>
                        selectOperation(
                          operations.find(
                            (item) => item.id === detail.selectedOption?.value,
                          ) || null,
                        )
                      }
                      options={operations.map((item) => ({
                        label: item.label,
                        value: item.id,
                      }))}
                      ariaLabel="Operation"
                    />
                  </FormField>

                  {operation?.params?.length > 0 && (
                    <ColumnLayout columns={2}>
                      {operation.params.map((field) => (
                        <FormField
                          key={field.name}
                          label={field.label}
                          description={field.placeholder}
                          constraintText={field.required ? 'Required' : undefined}
                        >
                          {field.type === 'textarea' ? (
                            <Textarea
                              value={params[field.name] || ''}
                              onChange={({ detail }) =>
                                setParams((prev) => ({
                                  ...prev,
                                  [field.name]: detail.value,
                                }))
                              }
                              placeholder={field.placeholder}
                            />
                          ) : field.type === 'checkbox' ? (
                            <Toggle
                              checked={Boolean(params[field.name])}
                              onChange={({ detail }) =>
                                setParams((prev) => ({
                                  ...prev,
                                  [field.name]: detail.checked,
                                }))
                              }
                            />
                          ) : (
                            <Input
                              type={field.type === 'number' ? 'number' : 'text'}
                              value={params[field.name] || ''}
                              onChange={({ detail }) =>
                                setParams((prev) => ({
                                  ...prev,
                                  [field.name]: detail.value,
                                }))
                              }
                              placeholder={field.placeholder}
                            />
                          )}
                        </FormField>
                      ))}
                    </ColumnLayout>
                  )}

                  {result && (
                    <SpaceBetween size="s">
                      <StatusIndicator type={result.ok ? 'success' : 'error'}>
                        {result.ok
                          ? `HTTP ${result.status}`
                          : result.error || `HTTP ${result.status || '0'}`}
                      </StatusIndicator>
                      {result.body && (
                        <pre className="result-body">{pretty(result.body)}</pre>
                      )}
                    </SpaceBetween>
                  )}
                </SpaceBetween>
              </Form>
            </Container>
          ) : (
            <Alert type="info" header="No GUI actions for this service yet">
              Browse stays available. Add an entry to{' '}
              <code>control/console.py</code> to give it a form.
            </Alert>
          )}

          {bucket && (
            <Container
              header={
                <Header
                  variant="h2"
                  counter={`(${objects.length})`}
                  description={`Objects in ${bucket}`}
                  actions={
                    <Button
                      variant="link"
                      onClick={() => {
                        setBucket('')
                        setObjects([])
                      }}
                    >
                      Close
                    </Button>
                  }
                >
                  Bucket objects
                </Header>
              }
            >
              <Table
                items={objects}
                loading={objectsLoading}
                loadingText="Reading objects"
                trackBy="key"
                columnDefinitions={[
                  {
                    id: 'key',
                    header: 'Key',
                    cell: (item) => <span className="mono">{item.key}</span>,
                    sortingField: 'key',
                  },
                  { id: 'size', header: 'Size', cell: (item) => item.size, width: 110 },
                  {
                    id: 'modified',
                    header: 'Last modified',
                    cell: (item) => item.modified,
                    width: 230,
                  },
                ]}
                empty={
                  <Box textAlign="center" color="text-body-secondary">
                    No objects in this bucket.
                  </Box>
                }
              />
            </Container>
          )}

          {kinds.length > 0 ? (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '220px minmax(0, 1fr)',
                gap: 16,
                alignItems: 'start',
              }}
            >
              <SideNavigation
                activeHref={`#${activeTab || 'all'}`}
                items={[
                  { type: 'link', text: `All (${rows.length})`, href: '#all' },
                  ...kinds.map((kind) => ({
                    type: 'link',
                    text: `${kind.charAt(0).toUpperCase()}${kind.slice(1)} (${countsByKind[kind] || 0})`,
                    href: `#${kind}`,
                  })),
                ]}
                onFollow={({ detail }) => {
                  const next = detail.href.replace('#', '')
                  setActiveTab(next === 'all' ? '' : next)
                }}
              />
              {resourceTable}
            </div>
          ) : (
            resourceTable
          )}

          <Modal
            visible={Boolean(confirmingDelete)}
            onDismiss={() => setConfirmingDelete(null)}
            header="Delete bucket?"
            footer={
              <Box float="right">
                <SpaceBetween direction="horizontal" size="xs">
                  <Button variant="link" onClick={() => setConfirmingDelete(null)}>
                    Cancel
                  </Button>
                  <Button
                    variant="primary"
                    loading={busy}
                    disabled={deleteConfirm !== confirmingDelete}
                    onClick={removeBucket}
                  >
                    Delete
                  </Button>
                </SpaceBetween>
              </Box>
            }
          >
            <SpaceBetween size="m">
              <Box>
                Delete <code>{confirmingDelete}</code> from account{' '}
                <code>{account}</code>? This cannot be undone.
              </Box>
              <FormField
                label="Type the bucket name to confirm"
                constraintText={`Expected: ${confirmingDelete}`}
              >
                <Input
                  value={deleteConfirm}
                  onChange={({ detail }) => setDeleteConfirm(detail.value)}
                  placeholder={confirmingDelete || ''}
                />
              </FormField>
            </SpaceBetween>
          </Modal>

          <Modal
            visible={creating}
            onDismiss={() => setCreating(false)}
            header="Create bucket"
            footer={
              <Box float="right">
                <SpaceBetween direction="horizontal" size="xs">
                  <Button variant="link" onClick={() => setCreating(false)}>
                    Cancel
                  </Button>
                  <Button
                    variant="primary"
                    loading={busy}
                    disabled={!newBucket.trim()}
                    onClick={createBucket}
                  >
                    Create bucket
                  </Button>
                </SpaceBetween>
              </Box>
            }
          >
            <FormField
              label="Bucket name"
              constraintText="Lowercase letters, digits, dots and dashes; globally unique."
            >
              <Input
                value={newBucket}
                onChange={({ detail }) => setNewBucket(detail.value)}
                placeholder="my-bucket"
              />
            </FormField>
          </Modal>

          <Modal
            visible={Boolean(confirming)}
            onDismiss={() => setConfirming(null)}
            header={`${confirming?.label || 'Run action'}?`}
            footer={
              <Box float="right">
                <SpaceBetween direction="horizontal" size="xs">
                  <Button variant="link" onClick={() => setConfirming(null)}>
                    Cancel
                  </Button>
                  <Button
                    variant="primary"
                    onClick={() => {
                      const target = confirming
                      setConfirming(null)
                      run(target)
                    }}
                  >
                    {confirming?.id?.startsWith('delete') ? 'Delete' : 'Run'}
                  </Button>
                </SpaceBetween>
              </Box>
            }
          >
            <SpaceBetween size="s">
              <Box>
                This runs <code>{confirming?.cli}</code> for account{' '}
                <code>{account}</code> in <code>{region}</code>.
              </Box>
              <Box color="text-status-warning">This operation cannot be undone.</Box>
            </SpaceBetween>
          </Modal>
        </SpaceBetween>
      </ContentLayout>
    </Shell>
  )
}
