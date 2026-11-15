import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import Header from '@cloudscape-design/components/header'
import Link from '@cloudscape-design/components/link'
import {
  BarChart3,
  Box as BoxIcon,
  Brain,
  Briefcase,
  Cpu,
  Database,
  Film,
  Globe,
  Layout,
  Server,
  Settings,
  Share2,
  ShieldCheck,
  Star,
  Store,
  Truck,
  Wrench,
} from 'lucide-react'
import { useSession } from '../context'
import { useFavorites } from '../prefs'
import { serviceLabel } from '../serviceLabels'
import { groupByCategory } from '../serviceCatalogue'
import { Shell, loadCatalogue } from '../components/Shell'
import './services.css'

// All services: one card, three flowing columns, one block per category and a
// plain alphabetical run of links inside it — the shape the console's own
// Services page takes. No view switcher: there is one way to read this page.

const CATEGORY_ICON = {
  Analytics: BarChart3,
  'Application Integration': Share2,
  'Business Applications': Briefcase,
  'Compute': Server,
  'Containers': BoxIcon,
  'Database': Database,
  'Developer Tools': Wrench,
  'Front-end Web & Mobile': Layout,
  'Internet of Things': Cpu,
  'Machine Learning': Brain,
  'Management & Governance': Settings,
  'Media Services': Film,
  'Migration & Transfer': Truck,
  'Networking & Content Delivery': Globe,
  'Security, Identity & Compliance': ShieldCheck,
  'Storage': Store,
  'Other': BoxIcon,
}

export default function Services() {
  const navigate = useNavigate()
  const { meta } = useSession()
  const { toggleFavorite, isFavorite } = useFavorites(meta?.me?.account)
  const [catalogue, setCatalogue] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    loadCatalogue()
      .then(setCatalogue)
      .catch((err) => setError(err.message))
  }, [])

  const groups = useMemo(() => {
    const names = new Set(Object.keys(catalogue?.services || {}))
    for (const group of catalogue?.groups || []) {
      for (const name of group.services) names.add(name)
    }
    return groupByCategory(names)
  }, [catalogue])

  const open = (name) => navigate(`/resources/${name}`)

  return (
    <Shell
      activeHref="/services"
      breadcrumbs={[
        { text: 'Home', href: '/' },
        { text: 'All services', href: '/services' },
      ]}
    >
      <ContentLayout
        header={<Header variant="h1">All services</Header>}
      >
        {error && <Alert type="error">{error}</Alert>}
        <Container header={<Header variant="h2">Services by category</Header>}>
          <div className="services-columns">
            {groups.map(({ category, services }) => {
              const Icon = CATEGORY_ICON[category] || BoxIcon
              return (
                <section key={category} className="services-group">
                  <h3 className="services-group__title">
                    <Icon size={17} aria-hidden="true" />
                    {category}
                  </h3>
                  <ul className="services-group__list">
                    {services.map((name) => (
                      <li key={name}>
                        <button
                          type="button"
                          className={`services-star${isFavorite(name) ? ' is-favorite' : ''}`}
                          aria-pressed={isFavorite(name)}
                          aria-label={
                            isFavorite(name)
                              ? `Remove ${serviceLabel(name)} from favorites`
                              : `Add ${serviceLabel(name)} to favorites`
                          }
                          title={
                            isFavorite(name)
                              ? 'Remove from favorites'
                              : 'Add to favorites'
                          }
                          onClick={() => toggleFavorite(name)}
                        >
                          <Star
                            size={13}
                            fill={isFavorite(name) ? 'currentColor' : 'none'}
                          />
                        </button>
                        <Link
                          href={`/resources/${name}`}
                          onFollow={(event) => {
                            event.preventDefault()
                            open(name)
                          }}
                        >
                          {serviceLabel(name)}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              )
            })}
            {groups.length === 0 && (
              <Box color="text-body-secondary">Reading the service catalogue…</Box>
            )}
          </div>
        </Container>
      </ContentLayout>
    </Shell>
  )
}
