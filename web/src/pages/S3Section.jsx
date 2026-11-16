import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Header from '@cloudscape-design/components/header'
import SpaceBetween from '@cloudscape-design/components/space-between'
import Table from '@cloudscape-design/components/table'
import { api } from '../api'
import { useSession } from '../context'
import { regionName } from '../regionNames'
import { Shell } from '../components/Shell'

// The S3 console's other tabs, and only the ones this emulator backs: S3 Tables
// and S3 Files are separate APIs on the same instance. Directory buckets (S3
// Express One Zone) and vector buckets have no backend here, so they are not
// tabs at all rather than empty ones.
const SECTIONS = {
  'table-buckets': {
    title: 'Table buckets',
    summary:
      'Table buckets are the S3 Tables container for Apache Iceberg tables, their namespaces and policies.',
    source: 'tables',
    columns: [
      { id: 'name', header: 'Name', cell: (item) => item.name, sortingField: 'name' },
      {
        id: 'arn',
        header: 'ARN',
        cell: (item) => <span className="mono">{item.arn}</span>,
      },
      {
        id: 'created',
        header: 'Creation date',
        cell: (item) => item.createdAt || '\u2014',
        width: 230,
      },
    ],
  },
  files: {
    title: 'File systems',
    summary:
      'File systems let S3 data be mounted and shared; each one names the bucket behind it.',
    source: 'files',
    columns: [
      { id: 'name', header: 'Name', cell: (item) => item.name || item.fileSystemId },
      {
        id: 'id',
        header: 'File system ID',
        cell: (item) => <span className="mono">{item.fileSystemId}</span>,
      },
      { id: 'bucket', header: 'Bucket', cell: (item) => item.bucket },
      { id: 'status', header: 'Status', cell: (item) => item.status, width: 140 },
      {
        id: 'created',
        header: 'Creation date',
        cell: (item) => stamp(item.creationTime),
        width: 230,
      },
    ],
  },
}

// S3 Files reports `creationTime` as epoch seconds.
const stamp = (value) => {
  if (!value) return '\u2014'
  const at = new Date(Number(value) * 1000)
  return Number.isNaN(at.getTime())
    ? String(value)
    : at.toISOString().replace('T', ' ').slice(0, 19)
}

export default function S3Section({ section }) {
  const navigate = useNavigate()
  const { account, region } = useSession()
  const detail = SECTIONS[section]

  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!account) return undefined
    let live = true
    const read = section === 'table-buckets' ? api.s3TableBuckets : api.s3FileSystems
    setLoading(true)
    read(account, region)
      .then((answer) => {
        if (!live) return
        setRows(answer?.items || [])
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
  }, [section, account, region])

  if (!detail) return null

  return (
    <Shell
      breadcrumbs={[
        { text: 'Amazon S3', href: '/s3/home' },
        { text: 'Buckets', href: '/s3/home' },
        { text: detail.title },
      ]}
    >
      <ContentLayout
        header={
          <Header variant="h1" description={detail.summary}>
            {detail.title}
          </Header>
        }
      >
        <Container>
          <SpaceBetween size="m">
            {error && (
              <Alert type="error" header="Could not read this listing">
                {error}
              </Alert>
            )}
            <Table
              items={rows}
              loading={loading}
              loadingText={`Reading ${detail.title.toLowerCase()}`}
              columnDefinitions={detail.columns}
              trackBy={(item) => item.arn || item.fileSystemId || item.name}
              header={<Header counter={`(${rows.length})`}>{detail.title}</Header>}
              empty={
                <Box textAlign="center" color="text-body-secondary">
                  No {detail.title.toLowerCase()} in this account and region.
                </Box>
              }
            />
            <Box color="text-body-secondary" fontSize="body-s">
              Region <strong>{regionName(region)}</strong>{' '}
              <span className="mono">{region}</span>
            </Box>
            <Box>
              <Button variant="link" onClick={() => navigate('/s3/home')}>
                General purpose buckets
              </Button>
            </Box>
          </SpaceBetween>
        </Container>
      </ContentLayout>
    </Shell>
  )
}
