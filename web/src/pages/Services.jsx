import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
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
import TextFilter from '@cloudscape-design/components/text-filter'
import { api } from '../api'
import { useSession } from '../context'
import { useFavorites } from '../prefs'
import { ServiceIcon } from '../serviceIcons'
import { serviceLabel } from '../serviceLabels'
import { Shell, loadCatalogue } from '../components/Shell'

export default function Services() {
  const navigate = useNavigate()
  const { account, region } = useSession()
  const { toggleFavorite, isFavorite } = useFavorites()
  const [services, setServices] = useState({})
  const [counts, setCounts] = useState({})
  const [catalogue, setCatalogue] = useState(null)
  const [filter, setFilter] = useState('')
  const [view, setView] = useState('grid')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [states, cat, countData] = await Promise.all([
        api.services(),
        loadCatalogue(),
        account && region ? api.counts(account, region) : Promise.resolve({ counts: {} }),
      ])
      setServices(states || {})
      setCatalogue(cat)
      setCounts(countData?.counts || {})
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [account, region])

  useEffect(() => {
    load()
  }, [load])

  const groupOf = useMemo(() => {
    const map = {}
    for (const group of catalogue?.groups || []) {
      for (const name of group.services) map[name] = group.label
    }
    return map
  }, [catalogue])

  const items = useMemo(() => {
    const names = new Set()
    for (const group of catalogue?.groups || []) {
      for (const name of group.services) names.add(name)
    }
    for (const name of Object.keys(catalogue?.services || {})) names.add(name)
    return [...names]
      .map((name) => ({
        name,
        label: serviceLabel(name),
        group: groupOf[name] || 'Other',
        operations: catalogue?.services?.[name]?.operations?.length || 0,
        resources: counts[name] ?? null,
        available: Object.values(services[name] || {}).some(Boolean),
        favorite: isFavorite(name),
      }))
      .filter((item) =>
        `${item.name} ${item.label}`.toLowerCase().includes(filter.toLowerCase()),
      )
      .sort(
        (a, b) =>
          Number(b.favorite) - Number(a.favorite) ||
          Number(b.available) - Number(a.available) ||
          a.label.localeCompare(b.label),
      )
  }, [catalogue, services, counts, filter, isFavorite, groupOf])

  return (
    <Shell activeHref="/services" breadcrumbs={[{ text: 'Services', href: '/services' }]}>
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="Every service the emulator answers, with favorites pinned first."
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <SegmentedControl
                  selectedId={view}
                  onChange={({ detail }) => setView(detail.selectedId)}
                  options={[
                    { id: 'grid', text: 'Grid' },
                    { id: 'list', text: 'List' },
                  ]}
                />
                <Button iconName="refresh" onClick={load}>
                  Refresh
                </Button>
              </SpaceBetween>
            }
          >
            Services
          </Header>
        }
      >
        {error && <Alert type="error">{error}</Alert>}
        {view === 'grid' ? (
        <Cards
          items={items}
          loading={loading}
          loadingText="Reading services"
          trackBy="name"
          cardDefinition={{
            header: (item) => (
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <ServiceIcon name={item.name} />
                  <Link
                    fontSize="heading-m"
                    href={`/resources/${item.name}`}
                    onFollow={(event) => {
                      event.preventDefault()
                      navigate(`/resources/${item.name}`)
                    }}
                  >
                    {item.label}
                  </Link>
                </span>
                <Button
                  variant="icon"
                  iconName={item.favorite ? 'star-filled' : 'star'}
                  ariaLabel={item.favorite ? `Unfavorite ${item.name}` : `Favorite ${item.name}`}
                  onClick={() => toggleFavorite(item.name)}
                />
              </div>
            ),
            sections: [
              {
                id: 'group',
                content: (item) => <Box color="text-body-secondary">{item.group}</Box>,
              },
              {
                id: 'status',
                content: (item) => (
                  <StatusIndicator type={item.available ? 'success' : 'stopped'}>
                    {item.available ? 'available' : 'not seen'}
                  </StatusIndicator>
                ),
              },
              {
                id: 'resources',
                content: (item) => (
                  <Box color="text-body-secondary" fontSize="body-s">
                    {item.resources === null
                      ? '—'
                      : `${item.resources} resource${item.resources === 1 ? '' : 's'}`}
                  </Box>
                ),
              },
            ],
          }}
          header={<Header counter={`(${items.length})`}>Services</Header>}
          filter={
            <TextFilter
              filteringText={filter}
              filteringPlaceholder="Find a service"
              onChange={({ detail }) => setFilter(detail.filteringText)}
            />
          }
          empty={<Box textAlign="center">No service matches this filter.</Box>}
        />
        ) : (
          <Table
            items={items}
            trackBy="name"
            columnDefinitions={[
              {
                id: 'name',
                header: 'Service',
                cell: (item) => (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <ServiceIcon name={item.name} />
                    <Link
                      href={`/resources/${item.name}`}
                      onFollow={(event) => {
                        event.preventDefault()
                        navigate(`/resources/${item.name}`)
                      }}
                    >
                      {item.label}
                    </Link>
                  </span>
                ),
              },
              { id: 'group', header: 'Group', cell: (item) => item.group },
              {
                id: 'status',
                header: 'Status',
                cell: (item) => (
                  <StatusIndicator type={item.available ? 'success' : 'stopped'}>
                    {item.available ? 'available' : 'not seen'}
                  </StatusIndicator>
                ),
              },
              {
                id: 'resources',
                header: 'Resources',
                cell: (item) =>
                  item.resources === null
                    ? '—'
                    : `${item.resources} resource${item.resources === 1 ? '' : 's'}`,
              },
              {
                id: 'star',
                header: '',
                cell: (item) => (
                  <Button
                    variant="icon"
                    iconName={item.favorite ? 'star-filled' : 'star'}
                    ariaLabel={item.favorite ? `Unfavorite ${item.name}` : `Favorite ${item.name}`}
                    onClick={() => toggleFavorite(item.name)}
                  />
                ),
                width: 60,
              },
            ]}
            header={<Header counter={`(${items.length})`}>Services</Header>}
            filter={
              <TextFilter
                filteringText={filter}
                filteringPlaceholder="Find a service"
                onChange={({ detail }) => setFilter(detail.filteringText)}
              />
            }
            empty={<Box textAlign="center">No service matches this filter.</Box>}
          />
        )}
      </ContentLayout>
    </Shell>
  )
}
