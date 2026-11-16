import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams, useLocation, Navigate } from 'react-router-dom'
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
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import Table from '@cloudscape-design/components/table'

import Textarea from '@cloudscape-design/components/textarea'
import TextFilter from '@cloudscape-design/components/text-filter'
import Toggle from '@cloudscape-design/components/toggle'
import { useCollection } from '@cloudscape-design/collection-hooks'
import { api } from '../api'
import { useSession } from '../context'
import { useRecent } from '../prefs'
import { regionName } from '../regionNames'
import { ServiceIcon } from '../serviceIcons'
import { serviceLabel, serviceLongName } from '../serviceLabels'
import { Shell, loadCatalogue } from '../components/Shell'

const FIELD_DEFAULTS = (fields) =>
  Object.fromEntries((fields || []).map((item) => [item.name, item.default || '']))

// A listing is capped, so emptying re-lists after each pass. This bounds the loop
// in case a bucket never reports itself empty.
const EMPTY_PASSES = 100

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
  const location = useLocation()
  const { account, region, setRegion, meta } = useSession()
  const [searchParams, setSearchParams] = useSearchParams()
  const urlRegion = searchParams.get('region') || ''
  const { addRecent } = useRecent(meta?.me?.account)

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
  // A link carries the region it was made in: adopt it **once**, when the page
  // mounts. Re-adopting on every region change made the picker's choice get
  // undone by the URL a moment later, which read as "switching does nothing".
  const adopted = useRef(false)
  useEffect(() => {
    if (adopted.current) return
    adopted.current = true
    if (urlRegion && urlRegion !== region) setRegion(urlRegion)
    // Mount only: the URL seeds the page, it does not own it afterwards.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // From then on the URL follows the selection, so a copied link reproduces it.
  useEffect(() => {
    if (urlRegion === region) return
    setSearchParams({ region }, { replace: true })
  }, [region, urlRegion, setSearchParams])

  const [regions, setRegions] = useState([])
  const [bucket, setBucket] = useState('')
  const [objects, setObjects] = useState([])
  const [objectsLoading, setObjectsLoading] = useState(false)
  const [selected, setSelected] = useState([])
  const [confirmingDelete, setConfirmingDelete] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [confirmingEmpty, setConfirmingEmpty] = useState(null)
  const [emptyConfirm, setEmptyConfirm] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    loadCatalogue().then(setCatalogue).catch(() => setCatalogue(null))
  }, [])

  const spec = catalogue?.services?.[service]
  const operations = spec?.operations || []
  // `/:service/home` is a catch-all: any name renders. Only a service the
  // catalogue reports is a page — `/s3files/home`, `/s3tables/home` and the rest
  // of the upstream catalogue answer `unknown service` and are not ours to show.
  const unknown = Boolean(catalogue) && !spec

  useEffect(() => {
    setOperation(operations[0] || null)
    setParams(FIELD_DEFAULTS(operations[0]?.params))
    setResult(null)
  }, [service, catalogue])

  const load = useCallback(async () => {
    // A phantom service is redirected the moment the catalogue answers, so this
    // still runs once for it; gating on `catalogue` here would refetch every real
    // page a second time when the catalogue lands.
    if (!account) return
    setLoading(true)
    try {
      const payload = await api.browse(account, 'all', service)
      setRows(payload.resources || [])
      setRegions(payload.regions || [])
      setError('')
    } catch (err) {
      setError(err.message)
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [account, region, service])

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
        // The table lists every enabled region, so the action follows the row.
        region: selected[0]?.region || region,
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

  // Emptying is the console's own loop: the catalogue has no single call for it,
  // so each listed object goes through `delete-object`.
  const emptyBucket = async () => {
    if (!confirmingEmpty) return
    const { name, region: targetRegion } = confirmingEmpty
    setBusy(true)
    let removed = 0
    try {
      for (let pass = 0; pass < EMPTY_PASSES; pass += 1) {
        const listing = await api.s3Objects(account, targetRegion, name)
        const keys = (listing.objects || []).map((item) => item.key)
        if (keys.length === 0) break
        for (const key of keys) {
          const answer = await api.exec({
            account,
            region: targetRegion,
            service: 's3',
            operation: 'delete-object',
            params: { Bucket: name, Key: key },
          })
          if (!answer.ok) {
            throw new Error(answer.error || `Could not delete ${key}.`)
          }
          removed += 1
        }
      }
      addFlash('success', `Bucket ${name} emptied (${removed} objects deleted).`)
      setConfirmingEmpty(null)
      if (bucket === name) setObjects([])
      load()
    } catch (err) {
      addFlash('error', `${err.message}${removed ? ` (${removed} already deleted)` : ''}`)
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

  const visible = rows

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

  // The create page hands back the name it made, so the list says so — once.
  useEffect(() => {
    const created = location.state?.created
    if (!created) return
    addFlash('success', `Bucket ${created} created.`)
    navigate(`${location.pathname}${location.search}`, { replace: true, state: null })
    // Mount only: the flash belongs to the navigation that brought us here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  // Copy an S3 ARN the way the console does, straight from the selection.
  const copyArn = async () => {
    const name = selected[0]?.name
    if (!name) return
    try {
      await navigator.clipboard.writeText(`arn:aws:s3:::${name}`)
      addFlash('success', `Copied arn:aws:s3:::${name}`)
    } catch {
      // clipboard denied: the ARN is derivable from the name on screen
      addFlash('error', `Could not copy. The ARN is arn:aws:s3:::${name}`)
    }
  }

  const actionsPanel =
    operations.length > 0 ? (
      <Container
        header={
          <Header
            variant="h2"
            description="Each action is the API call the CLI would make, signed as this account's root."
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
        Browse stays available. Add an entry to <code>control/console.py</code> to
        give it a form.
      </Alert>
    )

  const resourceTable = (
    <Table
      {...collectionProps}
      items={visibleRows}
      loading={loading}
      loadingText="Reading resources"
      trackBy={(item) => `${item.region || ''}/${item.kind}/${item.name}`}
      columnDefinitions={[
        ...(service === 's3'
          ? []
          : [
              {
                id: 'kind',
                header: 'Kind',
                cell: (item) => item.kind,
                sortingField: 'kind',
                width: 130,
              },
            ]),
        {
          id: 'name',
          header: 'Name',
          cell: (item) =>
            service === 's3' ? (
              <Button variant="inline-link" onClick={() => openBucket(item.name)}>
                {item.name}
              </Button>
            ) : (
              <span className="mono">{item.name}</span>
            ),
          sortingField: 'name',
        },
        {
          id: 'region',
          header: service === 's3' ? 'AWS Region' : 'Region',
          cell: (item) =>
            item.region ? (
              <span>
                {regionName(item.region)}{' '}
                <span className="mono">{item.region}</span>
              </span>
            ) : (
              '\u2014'
            ),
          sortingField: 'region',
          width: 240,
        },
        ...(service === 's3'
          ? [
              {
                id: 'created',
                header: 'Creation date',
                cell: (item) => item.detail?.created || '\u2014',
                width: 230,
              },
            ]
          : [
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
            ]),
        ...(service === 's3'
          ? []
          : [
              {
                id: 'open',
                header: '',
                cell: (item) =>
                  item.kind === 'bucket' ? (
                    <Button
                      variant="inline-link"
                      onClick={() => openBucket(item.name)}
                    >
                      Open
                    </Button>
                  ) : null,
                width: 90,
              },
            ]),
      ]}
      filter={
        <TextFilter
          {...filterProps}
          filteringPlaceholder={
            service === 's3' ? 'Find buckets by name' : 'Find a resource'
          }
        />
      }
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
          description={
            service === 's3'
              ? 'Buckets are containers for data stored in S3.'
              : spec?.description
          }
          actions={
            service === 's3' ? (
              <SpaceBetween direction="horizontal" size="xs">
                <Button iconName="refresh" ariaLabel="Refresh" onClick={load} />
                <Button disabled={!selected.length} onClick={copyArn}>
                  Copy ARN
                </Button>
                <Button
                  disabled={!selected.length}
                  onClick={() => {
                    setEmptyConfirm('')
                    setConfirmingEmpty({
                      name: selected[0].name,
                      region: selected[0].region || region,
                    })
                  }}
                >
                  Empty
                </Button>
                <Button
                  disabled={!selected.length}
                  onClick={() => {
                    setDeleteConfirm('')
                    setConfirmingDelete(selected[0].name)
                  }}
                >
                  Delete
                </Button>
                <Button variant="primary" onClick={() => navigate('/s3/create')}>
                  Create bucket
                </Button>
              </SpaceBetween>
            ) : undefined
          }
        >
          {service === 's3'
            ? 'General purpose buckets'
            : `${serviceLabel(service)} resources`}
        </Header>
      }
      empty={
        <Box textAlign="center">
          <SpaceBetween size="s">
            <Box color="text-body-secondary">
              Nothing in this account yet.
            </Box>
            <Button iconName="refresh" onClick={load}>
              Refresh
            </Button>
          </SpaceBetween>
        </Box>
      }
    />
  )

  if (unknown) {
    // Nothing to read, no actions to offer: send the caller to the services that
    // do exist rather than leaving a page-shaped error behind.
    return <Navigate to="/services" replace />
  }

  return (
    <Shell
      breadcrumbs={[
        { text: serviceLongName(service), href: `/${service}/home` },
        { text: service === 's3' ? 'Buckets' : 'Resources' },
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
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <ServiceIcon name={service} size={22} />
              {service === 's3' ? 'Buckets' : serviceLabel(service)}
            </span>
          </Header>
        }
      >
        <SpaceBetween size="l">
          {flash.length > 0 && <Flashbar items={flash} />}
          {/* The console's S3 page has no service chooser: the service menu in
              the bar is how you move between services. */}
          {service !== 's3' && (
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
                <Box color="text-body-secondary" fontSize="body-s">
                  Account <code>{account}</code> · read across every enabled region
                  {' · '}
                  <code>{regions.join(', ') || '—'}</code>
                </Box>
              </SpaceBetween>
            </Container>
          )}

          {error && (
            <Alert type="error" header="Could not read this service">
              {error}
            </Alert>
          )}

          {service === 'iam' && (
            <Alert type="info" header="The account root is not an IAM user">
              The 12-digit account identity is the root of the account. IAM users
              below are separate principals created inside it.
            </Alert>
          )}

          {resourceTable}

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

          {/* S3's actions are the table's own (Empty / Delete / Create bucket);
              the API explorer stays on the services that have no table actions. */}
          {service !== 's3' && actionsPanel}

          <Modal
            visible={Boolean(confirmingEmpty)}
            onDismiss={() => setConfirmingEmpty(null)}
            header="Empty bucket?"
            footer={
              <Box float="right">
                <SpaceBetween direction="horizontal" size="xs">
                  <Button variant="link" onClick={() => setConfirmingEmpty(null)}>
                    Cancel
                  </Button>
                  <Button
                    variant="primary"
                    loading={busy}
                    disabled={emptyConfirm !== confirmingEmpty?.name}
                    onClick={emptyBucket}
                  >
                    Empty
                  </Button>
                </SpaceBetween>
              </Box>
            }
          >
            <SpaceBetween size="m">
              <Box>
                Delete every object in <code>{confirmingEmpty?.name}</code>? The
                bucket itself stays, and this cannot be undone.
              </Box>
              <FormField
                label="Type the bucket name to confirm"
                constraintText={`Expected: ${confirmingEmpty?.name || ''}`}
              >
                <Input
                  value={emptyConfirm}
                  onChange={({ detail }) => setEmptyConfirm(detail.value)}
                  placeholder={confirmingEmpty?.name || ''}
                />
              </FormField>
            </SpaceBetween>
          </Modal>

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
