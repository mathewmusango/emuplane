import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import Cards from '@cloudscape-design/components/cards'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Header from '@cloudscape-design/components/header'
import Link from '@cloudscape-design/components/link'
import SegmentedControl from '@cloudscape-design/components/segmented-control'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import Table from '@cloudscape-design/components/table'
import { useFavorites } from '../prefs'
import { api } from '../api'
import { useSession } from '../context'
import { ServiceIcon } from '../serviceIcons'
import { serviceLabel } from '../serviceLabels'
import { Shell, loadCatalogue } from '../components/Shell'

const views = [
  { id: 'grid', text: 'Grid' },
  { id: 'list', text: 'List' },
]

export default function Favorites() {
  const navigate = useNavigate()
  const { account, region, meta } = useSession()
  const { favorites, toggleFavorite } = useFavorites(meta?.me?.account)
  const [catalogue, setCatalogue] = useState(null)
  const [services, setServices] = useState({})
  const [counts, setCounts] = useState({})
  const [view, setView] = useState('grid')

  useEffect(() => {
    loadCatalogue().then(setCatalogue).catch(() => setCatalogue(null))
    api.services().then((data) => setServices(data || {})).catch(() => {})
    if (account && region) {
      api.counts(account, region).then((data) => setCounts(data?.counts || {})).catch(() => {})
    }
  }, [account, region])

  const groupOf = useMemo(() => {
    const map = {}
    for (const group of catalogue?.groups || []) {
      for (const name of group.services) map[name] = group.label
    }
    return map
  }, [catalogue])

  const items = favorites.map((name) => ({
    name,
    label: serviceLabel(name),
    group: groupOf[name] || 'Other',
    available: Object.values(services[name] || {}).some(Boolean),
    resources: counts[name] ?? null,
  }))

  const open = (name) => (
    <Link
      href={`/resources/${name}`}
      onFollow={(event) => {
        event.preventDefault()
        navigate(`/resources/${name}`)
      }}
    >
      {serviceLabel(name)}
    </Link>
  )

  const nameCell = (item) => (
    <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <ServiceIcon name={item.name} />
      {open(item.name)}
    </span>
  )

  const star = (item) => (
    <Button
      variant="icon"
      iconName="star-filled"
      ariaLabel={`Unfavorite ${item.name}`}
      onClick={() => toggleFavorite(item.name)}
    />
  )

  const resourcesOf = (item) =>
    item.resources === null
      ? '—'
      : `${item.resources} resource${item.resources === 1 ? '' : 's'}`

  const statusOf = (item) => (
    <StatusIndicator type={item.available ? 'success' : 'stopped'}>
      {item.available ? 'available' : 'not seen'}
    </StatusIndicator>
  )

  const empty = (
    <Box textAlign="center" color="text-body-secondary">
      <SpaceBetween size="s">
        <Box>No favorites yet.</Box>
        <Button onClick={() => navigate('/services')}>Pick one from Services</Button>
      </SpaceBetween>
    </Box>
  )

  const table = (
    <Table
      items={items}
      trackBy="name"
      columnDefinitions={[
        { id: 'name', header: 'Service', cell: nameCell },
        { id: 'group', header: 'Group', cell: (item) => item.group },
        { id: 'status', header: 'Status', cell: statusOf },
        { id: 'resources', header: 'Resources', cell: resourcesOf },
        { id: 'star', header: '', cell: star, width: 60 },
      ]}
      header={<Header counter={`(${items.length})`}>Pinned services</Header>}
      empty={empty}
    />
  )

  return (
    <Shell activeHref="/favorites" breadcrumbs={[{ text: 'Favorites', href: '/favorites' }]}>
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="Services pinned in this browser."
            actions={
              <SegmentedControl
                selectedId={view}
                onChange={({ detail }) => setView(detail.selectedId)}
                options={views}
              />
            }
          >
            Favorites
          </Header>
        }
      >
        {view === 'grid' ? (
          <Cards
            items={items}
            trackBy="name"
            cardDefinition={{
              header: (item) => (
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  {nameCell(item)}
                  {star(item)}
                </div>
              ),
              sections: [
                {
                  id: 'group',
                  content: (item) => <Box color="text-body-secondary">{item.group}</Box>,
                },
                { id: 'status', content: statusOf },
                {
                  id: 'resources',
                  content: (item) => (
                    <Box color="text-body-secondary" fontSize="body-s">
                      {resourcesOf(item)}
                    </Box>
                  ),
                },
              ],
            }}
            header={<Header counter={`(${items.length})`}>Pinned services</Header>}
            empty={empty}
          />
        ) : (
          table
        )}
      </ContentLayout>
    </Shell>
  )
}
