import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import Checkbox from '@cloudscape-design/components/checkbox'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import ContentLayout from '@cloudscape-design/components/content-layout'
import FormField from '@cloudscape-design/components/form-field'
import Header from '@cloudscape-design/components/header'
import Input from '@cloudscape-design/components/input'
import Modal from '@cloudscape-design/components/modal'
import Multiselect from '@cloudscape-design/components/multiselect'
import Select from '@cloudscape-design/components/select'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import Table from '@cloudscape-design/components/table'
import Tabs from '@cloudscape-design/components/tabs'
import Textarea from '@cloudscape-design/components/textarea'
import { api } from '../api'
import { useSession } from '../context'
import { regionName } from '../regionNames'
import { Shell } from '../components/Shell'

// The Access Points page: three tabs (no directory buckets); Multi-Region creates are asynchronous, Object Lambda keeps its configuration as a document.
const SECTIONS = {
  general: {
    tab: 'General purpose buckets',
    title: (count) => `Access Points for general purpose buckets (${count})`,
    empty: (region) =>
      `You don't have any access points in the ${regionName(region)} ${region} Region`,
  },
  'multi-region': {
    tab: 'Multi-Region',
    title: (count) => `Multi-Region Access Points (${count})`,
    empty: () => "You don't have any Multi-Region access points.",
  },
  'object-lambda': {
    tab: 'Object Lambda',
    title: (count) => `Object Lambda Access Points (${count})`,
    empty: (region) =>
      `You don't have any Object Lambda access points in the ${regionName(region)} ${region} Region`,
  },
}

const dash = '\u2014'

// S3 Control's asynchronous operations walk NEW → INPROGRESS → SUCCEEDED/FAILED; the emulator settles at once.
const STATUS = {
  NEW: 'pending',
  INPROGRESS: 'in-progress',
  SUCCEEDED: 'success',
  FAILED: 'error',
}

const statusOf = (status) => (
  <StatusIndicator type={STATUS[status] || 'info'}>{status || dash}</StatusIndicator>
)

// Each traffic dial is 0 or 100 per member; S3 refuses a request where every member is 0.
const DIALS = [
  { value: '100', label: 'Active (100%)' },
  { value: '0', label: 'Inactive (0%)' },
]

const pretty = (text) => {
  if (!text) return ''
  try {
    return JSON.stringify(JSON.parse(text), null, 2)
  } catch {
    return text
  }
}

const COLUMNS = {
  general: [
    { id: 'name', header: 'Name', cell: (row) => row.name, sortingField: 'name' },
    { id: 'type', header: 'Data source type', cell: () => 'Bucket', width: 150 },
    {
      id: 'source',
      header: 'Data source ID',
      cell: (row) => row.bucket || dash,
      sortingField: 'bucket',
    },
    {
      id: 'alias',
      header: 'Access Point alias',
      cell: (row) => <span className="mono">{row.alias || dash}</span>,
    },
    {
      id: 'origin',
      header: 'Network origin',
      cell: (row) => row.network_origin || 'Internet',
      width: 150,
    },
    {
      id: 'vpc',
      header: 'VPC ID',
      cell: (row) => (row.vpc_id ? <span className="mono">{row.vpc_id}</span> : dash),
      width: 200,
    },
  ],
  'multi-region': [
    { id: 'name', header: 'Name', cell: (row) => row.name, sortingField: 'name' },
    { id: 'alias', header: 'Alias', cell: (row) => <span className="mono">{row.alias}</span> },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => <StatusIndicator type="success">{row.status || 'READY'}</StatusIndicator>,
      width: 130,
    },
    {
      id: 'regions',
      header: 'Buckets and Regions',
      cell: (row) =>
        (row.buckets || []).length
          ? row.buckets.map((item) => `${item.bucket} · ${item.region}`).join(', ')
          : dash,
    },
    { id: 'created', header: 'Created', cell: (row) => row.created || dash, width: 230 },
  ],
  'object-lambda': [
    { id: 'name', header: 'Name', cell: (row) => row.name, sortingField: 'name' },
    {
      id: 'alias',
      header: 'Access Point alias',
      cell: (row) => <span className="mono">{row.alias || dash}</span>,
    },
    {
      id: 'arn',
      header: 'ARN',
      cell: (row) => <span className="mono">{row.arn || dash}</span>,
    },
    {
      id: 'status',
      header: 'Alias status',
      cell: (row) => <StatusIndicator type="success">{row.status || 'READY'}</StatusIndicator>,
      width: 150,
    },
  ],
}

// One asynchronous Multi-Region operation; the token is the only handle, so the status is shown beside it.
const OperationDetail = ({ operation }) => (
  <SpaceBetween size="m">
    <ColumnLayout columns={3} variant="text-grid">
      <div>
        <Box variant="awsui-key-label">Operation</Box>
        {operation.operation || dash}
      </div>
      <div>
        <Box variant="awsui-key-label">Request status</Box>
        {statusOf(operation.status)}
      </div>
      <div>
        <Box variant="awsui-key-label">Requested</Box>
        {operation.created || dash}
      </div>
    </ColumnLayout>
    <div>
      <Box variant="awsui-key-label">Request token ARN</Box>
      <span className="mono">{operation.token || dash}</span>
    </div>
    {operation.error && (
      <Alert type="error" header="The operation ended in error">
        {operation.error.message || operation.error.code}
      </Alert>
    )}
    <Table
      items={operation.results || []}
      header={<Header variant="h3">Regions</Header>}
      empty={<Box color="text-body-secondary">No Region was reported.</Box>}
      columnDefinitions={[
        { id: 'region', header: 'Region', cell: (row) => row.region || dash },
        {
          id: 'status',
          header: 'Request status',
          width: 200,
          cell: (row) => statusOf(row.status),
        },
      ]}
    />
  </SpaceBetween>
)

export default function AccessPoints() {
  const navigate = useNavigate()
  const { account, region } = useSession()
  const [section, setSection] = useState('general')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [selected, setSelected] = useState([])
  const [filter, setFilter] = useState({ tokens: [], operation: 'and' })
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)
  const [policy, setPolicy] = useState(null)
  const [policyText, setPolicyText] = useState('')
  const [policyError, setPolicyError] = useState('')
  const [detailRow, setDetailRow] = useState(null)
  const [detailView, setDetailView] = useState(null)
  const [detailError, setDetailError] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [members, setMembers] = useState([])
  const [bucketOptions, setBucketOptions] = useState([])
  const [bucketsError, setBucketsError] = useState('')
  const [createError, setCreateError] = useState('')
  const [createResult, setCreateResult] = useState(null)
  // The operations this page created, by access point name: the token exists only in the answer that carried it.
  const [operations, setOperations] = useState({})
  const [routeDials, setRouteDials] = useState(null)
  const [routesBusy, setRoutesBusy] = useState(false)
  const [routesError, setRoutesError] = useState('')
  const [lambdaCreateOpen, setLambdaCreateOpen] = useState(false)
  const [lambdaName, setLambdaName] = useState('')
  const [lambdaSupport, setLambdaSupport] = useState(null)
  const [lambdaFunction, setLambdaFunction] = useState('')
  const [lambdaActions, setLambdaActions] = useState({ GetObject: true, HeadObject: true })
  const [lambdaMetrics, setLambdaMetrics] = useState(false)
  const [lambdaOptions, setLambdaOptions] = useState([])
  const [lambdaError, setLambdaError] = useState('')
  const [lambdaCreating, setLambdaCreating] = useState(false)
  const [configEdit, setConfigEdit] = useState(null)
  const [configError, setConfigError] = useState('')
  const [configBusy, setConfigBusy] = useState(false)
  const detail = SECTIONS[section]

  const load = () => {
    if (!account) return undefined
    let live = true
    setLoading(true)
    api
      .accessPoints(account, region, section)
      .then((answer) => {
        if (!live) return
        setRows(answer?.access_points || [])
        setError('')
      })
      .catch((err) => {
        if (!live) return
        setRows([])
        setError(err.message)
      })
      .finally(() => {
        if (live) setLoading(false)
      })
    return () => {
      live = false
    }
  }

  useEffect(load, [account, region, section])

  useEffect(() => {
    setSelected([])
    setFilter({ tokens: [], operation: 'and' })
  }, [section])

  const visible = useMemo(() => {
    const tokens = filter.tokens.map((token) => token.value.toLowerCase())
    if (!tokens.length) return rows
    const fields = (row) =>
      [row.name, row.alias, row.bucket, row.arn]
        .filter(Boolean)
        .map((value) => String(value).toLowerCase())
    const matches = (row, token) => fields(row).some((value) => value.includes(token))
    return rows.filter((row) =>
      filter.operation === 'or'
        ? tokens.some((token) => matches(row, token))
        : tokens.every((token) => matches(row, token)),
    )
  }, [rows, filter])

  const copyArn = async () => {
    const arn = selected[0]?.arn
    if (!arn) return
    try {
      await navigator.clipboard?.writeText(arn)
      setNotice('ARN copied')
    } catch {
      setNotice(`Copy failed. The ARN is ${arn}`)
    }
  }

  // A listing row has no policy, routes or configuration, so the row view reads the instance resources themselves.
  const openDetail = async (row = selected[0]) => {
    if (!row) return
    setDetailRow(row)
    setDetailView(null)
    setDetailError('')
    setRoutesError('')
    setRouteDials(null)
    try {
      setDetailView(await api.accessPointDetail(account, region, section, row.name))
    } catch (err) {
      setDetailError(err.message)
    }
  }

  const openPolicy = async () => {
    const row = selected[0]
    if (!row) return
    setPolicy({ name: row.name, section })
    setPolicyText('')
    setPolicyError('')
    try {
      const answer = await api.accessPointPolicy(account, region, row.name, section)
      setPolicyText(pretty(answer.policy))
    } catch (err) {
      setPolicyError(err.message)
    }
  }

  const savePolicy = async (next) => {
    const multiRegion = policy.section === 'multi-region'
    setBusy(true)
    setPolicyError('')
    try {
      const answer = multiRegion
        ? await api.editMultiRegionPolicy({
            account,
            region,
            name: policy.name,
            policy: next,
          })
        : await api.editAccessPointPolicy({
            account,
            region,
            name: policy.name,
            policy: next,
            section: policy.section === 'object-lambda' ? 'object-lambda' : 'general',
          })
      // A FAILED Multi-Region policy write means the old policy is still in force, so keep the editor open.
      if (answer.operation) {
        setOperations((held) => ({ ...held, [policy.name]: answer.operation }))
        if (answer.created === false) {
          setPolicyError(answer.error || 'the operation did not succeed')
          return
        }
      }
      setPolicy(null)
      setNotice(multiRegion || next ? 'Access point policy saved' : 'Access point policy removed')
      load()
    } catch (err) {
      setPolicyError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    const kind = deleting.section
    setBusy(true)
    try {
      const answer =
        kind === 'multi-region'
          ? await api.deleteMultiRegionAccessPoint({
              account,
              region,
              name: deleting.name,
            })
          : kind === 'object-lambda'
            ? await api.deleteObjectLambdaAccessPoint({
                account,
                region,
                name: deleting.name,
              })
            : await api.deleteAccessPoint({
                account,
                region,
                name: deleting.name,
              })
      setDeleting(null)
      if (answer.operation) {
        setOperations((held) => ({ ...held, [deleting.name]: answer.operation }))
      }
      if (answer.created === false) {
        // The delete was accepted and did not happen; the operation says why.
        setError(answer.error || 'the delete did not succeed')
        return
      }
      setSelected([])
      setNotice(`Deleted access point ${deleting.name}`)
      load()
    } catch (err) {
      setError(err.message)
      setDeleting(null)
    } finally {
      setBusy(false)
    }
  }

  // The traffic dials are the one Multi-Region write S3 answers synchronously, so they are edited in place.
  const startRoutes = () => {
    const dials = {}
    for (const route of detailView?.routes || []) {
      dials[route.bucket] = String(route.traffic || '100')
    }
    setRouteDials(dials)
    setRoutesError('')
  }

  const saveRoutes = async () => {
    setRoutesBusy(true)
    setRoutesError('')
    try {
      await api.submitMultiRegionRoutes({
        account,
        region,
        arn: detailView.arn,
        routes: (detailView.routes || []).map((route) => ({
          bucket: route.bucket,
          traffic: String(routeDials[route.bucket]),
        })),
      })
      setNotice(`Traffic dials saved for ${detailRow.name}`)
      setRouteDials(null)
      await openDetail(detailRow)
    } catch (err) {
      setRoutesError(err.message)
    } finally {
      setRoutesBusy(false)
    }
  }

  // A Multi-Region create is asynchronous, so the form reads the account's buckets, each labelled with its Region.
  const openCreate = () => {
    setCreateOpen(true)
    setNewName('')
    setMembers([])
    setCreateError('')
    setCreateResult(null)
    setBucketsError('')
    setBucketOptions([])
    if (!account) return
    api
      .browse(account, 'all', 's3')
      .then((payload) =>
        setBucketOptions(
          (payload.resources || []).map((row) => ({
            label: `${row.name} · ${row.region || region}`,
            value: row.name,
            region: row.region || region,
          })),
        ),
      )
      .catch((err) => setBucketsError(err.message))
  }

  // Two members in one Region is the create S3 refuses, so the form says so before the request.
  const memberProblem = useMemo(() => {
    if (members.length < 2) return ''
    const seen = new Set()
    for (const member of members) {
      if (seen.has(member.region)) {
        return `A Multi-Region access point takes one bucket per Region, and two are in ${member.region}.`
      }
      seen.add(member.region)
    }
    return ''
  }, [members])

  const createMultiRegion = async () => {
    setCreateError('')
    setCreateResult(null)
    setBusy(true)
    try {
      const answer = await api.createMultiRegionAccessPoint({
        account,
        region,
        name: newName.trim(),
        buckets: members.map((member) => member.value),
      })
      setCreateResult(answer)
      if (answer.operation) {
        setOperations((held) => ({ ...held, [answer.name]: answer.operation }))
      }
      if (answer.created) {
        setNotice(`Multi-Region access point ${answer.name} is ready`)
        load()
      }
    } catch (err) {
      setCreateError(err.message)
    } finally {
      setBusy(false)
    }
  }

  // An Object Lambda access point reads through a supporting access point, so the form lists the general ones first.
  const openObjectLambdaCreate = () => {
    setLambdaCreateOpen(true)
    setLambdaName('')
    setLambdaSupport(null)
    setLambdaFunction('')
    setLambdaActions({ GetObject: true, HeadObject: true })
    setLambdaMetrics(false)
    setLambdaError('')
    setLambdaOptions([])
    if (!account) return
    api
      .accessPoints(account, region, 'general')
      .then((answer) =>
        setLambdaOptions(
          (answer?.access_points || []).map((row) => ({
            label: row.bucket ? `${row.name} · ${row.bucket}` : row.name,
            value: row.arn,
          })),
        ),
      )
      .catch((err) => setLambdaError(err.message))
  }

  const createObjectLambda = async () => {
    setLambdaError('')
    setLambdaCreating(true)
    try {
      await api.createObjectLambdaAccessPoint({
        account,
        region,
        name: lambdaName.trim(),
        supporting_access_point: lambdaSupport?.value || '',
        function_arn: lambdaFunction.trim(),
        actions: Object.keys(lambdaActions).filter((action) => lambdaActions[action]),
        cloudwatch_metrics: lambdaMetrics,
      })
      setLambdaCreateOpen(false)
      setNotice(`Object Lambda access point ${lambdaName.trim()} created`)
      load()
    } catch (err) {
      setLambdaError(err.message)
    } finally {
      setLambdaCreating(false)
    }
  }

  const saveConfiguration = async () => {
    if (!configEdit) return
    setConfigBusy(true)
    setConfigError('')
    try {
      await api.editObjectLambdaConfiguration({
        account,
        region,
        name: configEdit.name,
        configuration: configEdit.text,
      })
      setConfigEdit(null)
      setNotice(`Configuration saved for ${configEdit.name}`)
      if (detailRow) await openDetail(detailRow)
    } catch (err) {
      setConfigError(err.message)
    } finally {
      setConfigBusy(false)
    }
  }

  const general = section === 'general'

  const table = (
    <Table
      items={visible}
      loading={loading}
      loadingText="Reading access points"
      columnDefinitions={COLUMNS[section]}
      trackBy={(row) => row.arn || row.name}
      selectionType="single"
      selectedItems={selected}
      onSelectionChange={({ detail: changed }) => setSelected(changed.selectedItems)}
      filter={
        <div>
          <Input
            type="search"
            value={filter.tokens[0]?.value || ''}
            onChange={({ detail: changed }) =>
              setFilter({
                tokens: changed.value ? [{ value: changed.value }] : [],
                operation: 'and',
              })
            }
            placeholder="Search for access points by name"
            ariaLabel="Search for access points by name"
          />
        </div>
      }
      header={
        <Header
          description={
            general
              ? 'Access points are named network endpoints that are attached to buckets which simplify managing data access at scale in S3.'
              : section === 'multi-region'
                ? 'Multi-Region Access Points span buckets in several Regions; S3 Control manages them from us-west-2.'
                : 'Object Lambda Access Points run a Lambda function over each request; S3 Control manages them in the bucket’s Region.'
          }
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button iconName="refresh" ariaLabel="Refresh" onClick={load} />
              <Button disabled={!selected.length || !selected[0]?.arn} onClick={copyArn}>
                Copy ARN
              </Button>
              {!general && (
                <Button disabled={selected.length !== 1} onClick={() => openDetail()}>
                  View details
                </Button>
              )}
              <Button disabled={selected.length !== 1} onClick={openPolicy}>
                Edit policy
              </Button>
              <Button
                disabled={selected.length !== 1}
                onClick={() =>
                  setDeleting(selected[0] ? { name: selected[0].name, section } : null)
                }
              >
                Delete
              </Button>
              {general && (
                <Button
                  variant="primary"
                  onClick={() => navigate(`/s3/access-points/create?region=${region}`)}
                >
                  Create access point
                </Button>
              )}
              {section === 'object-lambda' && (
                <Button variant="primary" onClick={openObjectLambdaCreate}>
                  Create Object Lambda access point
                </Button>
              )}
              {section === 'multi-region' && (
                <Button variant="primary" onClick={openCreate}>
                  Create Multi-Region access point
                </Button>
              )}
            </SpaceBetween>
          }
        >
          {detail.title(visible.length)}
        </Header>
      }
      empty={
        loading ? undefined : (
          <Box textAlign="center">
            <SpaceBetween size="s">
              <Box color="text-body-secondary">{detail.empty(region)}</Box>
              {general && (
                <Button
                  variant="primary"
                  onClick={() => navigate(`/s3/access-points/create?region=${region}`)}
                >
                  Create access point
                </Button>
              )}
              {section === 'multi-region' && (
                <Button variant="primary" onClick={openCreate}>
                  Create Multi-Region access point
                </Button>
              )}
            </SpaceBetween>
          </Box>
        )
      }
    />
  )

  return (
    <Shell
      breadcrumbs={[{ text: 'Amazon S3', href: '/s3/home' }, { text: 'Access Points' }]}
    >
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="Access points are named network endpoints that are attached to buckets which simplify managing data access at scale in S3."
          >
            Access Points
          </Header>
        }
      >
        <SpaceBetween size="m">
          {notice && (
            <Alert type="success" dismissible onDismiss={() => setNotice('')}>
              {notice}
            </Alert>
          )}
          {error && (
            <Alert type="error" header="Could not read this page">
              {error}
            </Alert>
          )}
          {!general && !error && (
            <Alert type="info">
              {section === 'multi-region'
                ? 'A Multi-Region access point is created by an asynchronous request: S3 Control answers with a request token, and the operation it names is shown as soon as it is read. Deleting one, and changing its policy or routes, is done with the S3 Control API for now.'
                : 'An Object Lambda access point reads through a supporting access point and a Lambda function. Creating and deleting one, and editing its configuration and policy, are done on this page.'}
            </Alert>
          )}
          <Tabs
            activeTabId={section}
            onChange={({ detail: changed }) => setSection(changed.activeTabId)}
            tabs={Object.entries(SECTIONS).map(([id, spec]) => ({
              id,
              label: spec.tab,
              content: id === section ? table : null,
            }))}
          />
          <Box color="text-body-secondary" fontSize="body-s">
            Region <strong>{regionName(region)}</strong> <span className="mono">{region}</span>
            {section === 'multi-region' && (
              <>
                {' '}
                · Multi-Region management is served from{' '}
                <span className="mono">us-west-2</span>
              </>
            )}
          </Box>
        </SpaceBetween>
      </ContentLayout>

      <Modal
        visible={Boolean(policy)}
        onDismiss={() => setPolicy(null)}
        header={`Edit policy: ${policy?.name || ''}`}
        size="large"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setPolicy(null)}>
                Cancel
              </Button>
              {/* S3 Control has no DeleteMultiRegionAccessPointPolicy: a Multi-Region policy is replaced, never removed. */}
              {policy?.section !== 'multi-region' && (
                <Button
                  loading={busy}
                  disabled={!policyText.trim()}
                  onClick={() => savePolicy(null)}
                >
                  Remove policy
                </Button>
              )}
              <Button variant="primary" loading={busy} onClick={() => savePolicy(policyText)}>
                Save
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          {policyError && <Alert type="error">{policyError}</Alert>}
          <Textarea
            value={policyText}
            onChange={({ detail: changed }) => setPolicyText(changed.value)}
            rows={14}
            placeholder='{"Version": "2012-10-17", "Statement": [...]}'
          />
        </SpaceBetween>
      </Modal>

      <Modal
        visible={Boolean(deleting)}
        onDismiss={() => setDeleting(null)}
        header={
          deleting?.section === 'multi-region'
            ? 'Delete Multi-Region access point'
            : deleting?.section === 'object-lambda'
              ? 'Delete Object Lambda access point'
              : 'Delete access point'
        }
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setDeleting(null)}>
                Cancel
              </Button>
              <Button variant="primary" loading={busy} onClick={remove}>
                Delete
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          <Box>
            Delete <strong>{deleting?.name}</strong>?{' '}
            {deleting?.section === 'multi-region'
              ? 'Requests made through its alias stop working. The member buckets and their objects are not touched, and S3 Control answers the delete asynchronously.'
              : deleting?.section === 'object-lambda'
                ? 'Requests made through this Object Lambda access point stop working. The supporting access point and its bucket are not touched.'
                : 'Requests made through this access point stop working. The bucket and its objects are not touched.'}
          </Box>
          {deleting?.section === 'multi-region' ? (
            <Alert type="warning">
              A Multi-Region access point is deleted by an asynchronous request. Its operation is
              shown once S3 Control reports what became of it.
            </Alert>
          ) : (
            <Alert type="warning">
              A bucket with access points attached cannot be deleted until every one of them is
              deleted.
            </Alert>
          )}
        </SpaceBetween>
      </Modal>

      <Modal
        visible={createOpen}
        onDismiss={() => setCreateOpen(false)}
        header="Create Multi-Region access point"
        size="large"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setCreateOpen(false)}>
                {createResult ? 'Close' : 'Cancel'}
              </Button>
              <Button
                variant="primary"
                loading={busy}
                disabled={
                  Boolean(createResult?.created) ||
                  !newName.trim() ||
                  members.length < 2 ||
                  Boolean(memberProblem)
                }
                onClick={createMultiRegion}
              >
                Create
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          {createError && (
            <Alert type="error" header="Could not create the access point">
              {createError}
            </Alert>
          )}
          {bucketsError && (
            <Alert type="error" header="Could not read the buckets">
              {bucketsError}
            </Alert>
          )}
          {createResult && (
            <Alert
              type={createResult.created ? 'success' : 'error'}
              header={
                createResult.created
                  ? `Created ${createResult.name}`
                  : `The operation did not create ${createResult.name}`
              }
            >
              {createResult.created
                ? 'S3 Control answered the request with a token, and the operation it names ended SUCCEEDED.'
                : createResult.error}
            </Alert>
          )}
          <FormField
            label="Name"
            description="3 to 50 characters: lowercase letters, digits and hyphens, beginning and ending with a letter or number."
          >
            <Input
              value={newName}
              onChange={({ detail: changed }) => setNewName(changed.value)}
              placeholder="my-world-point"
              disabled={Boolean(createResult)}
            />
          </FormField>
          <FormField
            label="Member buckets"
            description="One bucket per Region, at least two. Each request is routed to the bucket in its own Region."
            errorText={memberProblem}
            constraintText={
              members.length < 2 && !createResult
                ? 'Choose at least two buckets, in different Regions.'
                : undefined
            }
          >
            <Multiselect
              selectedOptions={members}
              onChange={({ detail: changed }) => setMembers(changed.selectedOptions)}
              options={bucketOptions}
              placeholder="Choose buckets"
              empty="No buckets in this account"
              disabled={Boolean(createResult)}
            />
          </FormField>
          {createResult?.operation && (
            <SpaceBetween size="xs">
              <Header
                variant="h3"
                description="DescribeMultiRegionAccessPointOperation, read on the token the create answered with. The token is kept in this answer only."
              >
                Operation
              </Header>
              <OperationDetail operation={createResult.operation} />
            </SpaceBetween>
          )}
        </SpaceBetween>
      </Modal>

      <Modal
        visible={Boolean(detailRow)}
        onDismiss={() => setDetailRow(null)}
        header={detailRow ? `Access point ${detailRow.name}` : ''}
        size="large"
        footer={
          <Box float="right">
            <Button onClick={() => setDetailRow(null)}>Close</Button>
          </Box>
        }
      >
        {detailError ? (
          <Alert type="error">{detailError}</Alert>
        ) : !detailView ? (
          <Box color="text-body-secondary">Reading the access point…</Box>
        ) : (
          <SpaceBetween size="l">
            <ColumnLayout columns={3} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">State</Box>
                {detailView.state || dash}
              </div>
              <div>
                <Box variant="awsui-key-label">Alias</Box>
                <span className="mono">{detailView.alias || dash}</span>
              </div>
              <div>
                <Box variant="awsui-key-label">Created</Box>
                {detailView.created || dash}
              </div>
            </ColumnLayout>

            {detailView.section === 'multi-region' ? (
              <SpaceBetween size="l">
                <Table
                  items={detailView.buckets || []}
                  header={<Header variant="h3">Buckets</Header>}
                  columnDefinitions={[
                    { id: 'bucket', header: 'Bucket', cell: (row) => row.bucket },
                    { id: 'region', header: 'Region', cell: (row) => row.region },
                  ]}
                />
                {detailView.errors?.routes && (
                  <Alert type="error" header="Could not read the routes">
                    {detailView.errors.routes}
                  </Alert>
                )}
                {routesError && <Alert type="error">{routesError}</Alert>}
                <Table
                  items={detailView.routes || []}
                  header={
                    <Header
                      variant="h3"
                      description="Traffic dials decide how much of the request load each bucket takes."
                      actions={
                        <SpaceBetween direction="horizontal" size="xs">
                          {routeDials ? (
                            <>
                              <Button variant="link" onClick={() => setRouteDials(null)}>
                                Cancel
                              </Button>
                              <Button
                                variant="primary"
                                loading={routesBusy}
                                disabled={Object.values(routeDials).every(
                                  (dial) => dial === '0',
                                )}
                                onClick={saveRoutes}
                              >
                                Save
                              </Button>
                            </>
                          ) : (
                            <Button
                              onClick={startRoutes}
                              disabled={!(detailView.routes || []).length}
                            >
                              Edit traffic dials
                            </Button>
                          )}
                        </SpaceBetween>
                      }
                    >
                      Routes
                    </Header>
                  }
                  columnDefinitions={[
                    { id: 'bucket', header: 'Bucket', cell: (row) => row.bucket },
                    { id: 'region', header: 'Region', cell: (row) => row.region },
                    {
                      id: 'traffic',
                      header: 'Traffic dial',
                      width: 200,
                      cell: (row) =>
                        routeDials ? (
                          <Select
                            selectedOption={DIALS.find(
                              (dial) => dial.value === String(routeDials[row.bucket]),
                            )}
                            onChange={({ detail: changed }) =>
                              setRouteDials((held) => ({
                                ...held,
                                [row.bucket]: changed.selectedOption.value,
                              }))
                            }
                            options={DIALS}
                            ariaLabel={`Traffic dial for ${row.bucket}`}
                          />
                        ) : (
                          `${row.traffic}%`
                        ),
                    },
                  ]}
                />
                {routeDials &&
                  Object.values(routeDials).every((dial) => dial === '0') && (
                    <Alert type="warning">
                      At least one Region has to stay Active: set one dial back to 100 before
                      saving.
                    </Alert>
                  )}
                {operations[detailRow?.name] && (
                  <SpaceBetween size="xs">
                    <Header
                      variant="h3"
                      description="The create was asynchronous: this is the operation whose token it answered with, as read on this page."
                    >
                      Creation operation
                    </Header>
                    <OperationDetail operation={operations[detailRow.name]} />
                  </SpaceBetween>
                )}
              </SpaceBetween>
            ) : (
              <div>
                <Box variant="awsui-key-label">Configuration</Box>
                {detailView.errors?.configuration && (
                  <Alert type="error" header="Could not read the configuration">
                    {detailView.errors.configuration}
                  </Alert>
                )}
                {detailView.configuration ? (
                  <pre className="result-body">{detailView.configuration}</pre>
                ) : (
                  <Box color="text-body-secondary">Not configured.</Box>
                )}
                {detailView.configuration && (
                  <Button
                    onClick={() => {
                      setConfigError('')
                      setConfigEdit({ name: detailRow.name, text: detailView.configuration })
                    }}
                  >
                    Edit configuration
                  </Button>
                )}
              </div>
            )}

            {detailView.errors?.policy && (
              <Alert type="error" header="Could not read the policy">
                {detailView.errors.policy}
              </Alert>
            )}
            <div>
              <Box variant="awsui-key-label">Access point policy</Box>
              {detailView.policy ? (
                <pre className="result-body">{detailView.policy}</pre>
              ) : (
                <Box color="text-body-secondary">No policy on this access point.</Box>
              )}
            </div>
          </SpaceBetween>
        )}
      </Modal>

      <Modal
        visible={lambdaCreateOpen}
        onDismiss={() => setLambdaCreateOpen(false)}
        header="Create Object Lambda access point"
        size="medium"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setLambdaCreateOpen(false)}>
                Cancel
              </Button>
              <Button variant="primary" loading={lambdaCreating} onClick={createObjectLambda}>
                Create
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          {lambdaError && <Alert type="error">{lambdaError}</Alert>}
          <FormField
            label="Name"
            description="3 to 50 lowercase letters, digits and hyphens, without `--`."
          >
            <Input
              value={lambdaName}
              onChange={({ detail: changed }) => setLambdaName(changed.value)}
              placeholder="my-object-lambda"
            />
          </FormField>
          <FormField
            label="Supporting access point"
            description="The general purpose access point the Lambda transformations read through."
          >
            <Select
              selectedOption={lambdaSupport}
              onChange={({ detail: changed }) => setLambdaSupport(changed.selectedOption)}
              options={lambdaOptions}
              placeholder="Choose an access point"
              empty="No general purpose access points in this Region"
            />
          </FormField>
          <FormField
            label="Lambda function ARN"
            description="It has to be in the same account and Region as the access point."
          >
            <Input
              value={lambdaFunction}
              onChange={({ detail: changed }) => setLambdaFunction(changed.value)}
              placeholder={`arn:aws:lambda:${region}:${account}:function:my-transform`}
            />
          </FormField>
          <FormField label="Transformations">
            <SpaceBetween size="xs">
              <Checkbox
                checked={lambdaActions.GetObject}
                onChange={({ detail: changed }) =>
                  setLambdaActions((held) => ({ ...held, GetObject: changed.checked }))
                }
              >
                GetObject
              </Checkbox>
              <Checkbox
                checked={lambdaActions.HeadObject}
                onChange={({ detail: changed }) =>
                  setLambdaActions((held) => ({ ...held, HeadObject: changed.checked }))
                }
              >
                HeadObject
              </Checkbox>
            </SpaceBetween>
          </FormField>
          <Checkbox
            checked={lambdaMetrics}
            onChange={({ detail: changed }) => setLambdaMetrics(changed.checked)}
          >
            Publish CloudWatch metrics
          </Checkbox>
        </SpaceBetween>
      </Modal>

      <Modal
        visible={Boolean(configEdit)}
        onDismiss={() => setConfigEdit(null)}
        header={`Edit configuration: ${configEdit?.name || ''}`}
        size="large"
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setConfigEdit(null)}>
                Cancel
              </Button>
              <Button variant="primary" loading={configBusy} onClick={saveConfiguration}>
                Save
              </Button>
            </SpaceBetween>
          </Box>
        }
      >
        <SpaceBetween size="m">
          {configError && <Alert type="error">{configError}</Alert>}
          <Textarea
            value={configEdit?.text || ''}
            onChange={({ detail: changed }) =>
              setConfigEdit((held) => ({ ...held, text: changed.value }))
            }
            rows={14}
            placeholder="<Configuration>...</Configuration>"
          />
        </SpaceBetween>
      </Modal>
    </Shell>
  )
}
