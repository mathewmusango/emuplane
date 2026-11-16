import { useNavigate } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Header from '@cloudscape-design/components/header'
import SpaceBetween from '@cloudscape-design/components/space-between'
import { useSession } from '../context'
import { regionName } from '../regionNames'
import { Shell } from '../components/Shell'

// The S3 console's other tabs. They are children of S3 — the sidebar keeps them
// under *Buckets* and *Files* — and each says what this instance can do with it
// rather than showing an empty table that reads like "you have none".
const SECTIONS = {
  'directory-buckets': {
    title: 'Directory buckets',
    summary:
      'Directory buckets (S3 Express One Zone) use a single Availability Zone and their own storage class.',
    state: 'unserved',
    note: 'This emulator serves general purpose buckets only, so there are no directory buckets to list.',
  },
  'vector-buckets': {
    title: 'Vector buckets',
    summary:
      'Vector buckets hold embeddings for similarity search and are addressed through the S3 Vectors API.',
    state: 'unserved',
    note: 'The emulator does not serve S3 Vectors, so there are no vector buckets to list.',
  },
  'table-buckets': {
    title: 'Table buckets',
    summary:
      'Table buckets are the S3 Tables container for Apache Iceberg tables, their namespaces and policies.',
    state: 'unlisted',
    note: 'The emulator serves the S3 Tables API (39 operations: table buckets, namespaces, tables, policies), but this console has no table view yet — this page is not a list of table buckets.',
  },
  files: {
    title: 'File systems',
    summary:
      'S3 Files exposes file systems that S3 data can be mounted and shared through.',
    state: 'unlisted',
    note: 'The emulator serves the S3 Files API (21 operations: file systems, mounts and access points), but this console has no file-system view yet — this page is not a list of file systems.',
  },
}

export default function S3Section({ section }) {
  const navigate = useNavigate()
  const { region } = useSession()
  const detail = SECTIONS[section]

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
            <Alert type={detail.state === 'unserved' ? 'info' : 'warning'}>
              {detail.note}
            </Alert>
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
