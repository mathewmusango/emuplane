import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import AppLayout from '@cloudscape-design/components/app-layout'
import Autosuggest from '@cloudscape-design/components/autosuggest'
import BreadcrumbGroup from '@cloudscape-design/components/breadcrumb-group'
import SideNavigation from '@cloudscape-design/components/side-navigation'
import TopNavigation from '@cloudscape-design/components/top-navigation'
import { useSession } from '../context'
import { api } from '../api'
import { useThemeToggle } from './themeToggle'
import { serviceLabel } from '../serviceLabels'

const navItems = () => [
  { type: 'link', text: 'Dashboard', href: '/' },
  { type: 'link', text: 'Favorites', href: '/favorites' },
  { type: 'link', text: 'Services', href: '/services' },
  { type: 'divider' },
  {
    type: 'section',
    text: 'System',
    items: [
      { type: 'link', text: 'Settings', href: '/settings' },
      { type: 'link', text: 'About', href: '/about' },
    ],
  },
]

// One cached catalogue shared by the shell search and every page.
let cataloguePromise = null
export function loadCatalogue() {
  if (!cataloguePromise) {
    cataloguePromise = api.actions().catch((err) => {
      cataloguePromise = null
      throw err
    })
  }
  return cataloguePromise
}

const REGION_NAMES = {
  'us-east-1': 'N. Virginia',
  'us-east-2': 'Ohio',
  'us-west-1': 'N. California',
  'us-west-2': 'Oregon',
  'ca-central-1': 'Canada Central',
  'ca-west-1': 'Calgary',
  'sa-east-1': 'São Paulo',
  'mx-central-1': 'Mexico Central',
  'eu-west-1': 'Ireland',
  'eu-west-2': 'London',
  'eu-west-3': 'Paris',
  'eu-central-1': 'Frankfurt',
  'eu-central-2': 'Zurich',
  'eu-north-1': 'Stockholm',
  'eu-south-1': 'Milan',
  'eu-south-2': 'Spain',
  'eusc-de-east-1': 'Brandenburg',
  'ap-south-1': 'Mumbai',
  'ap-south-2': 'Hyderabad',
  'ap-east-1': 'Hong Kong',
  'ap-east-2': 'Taipei',
  'ap-southeast-1': 'Singapore',
  'ap-southeast-2': 'Sydney',
  'ap-southeast-3': 'Jakarta',
  'ap-southeast-4': 'Melbourne',
  'ap-southeast-5': 'Malaysia',
  'ap-southeast-7': 'Thailand',
  'ap-northeast-1': 'Tokyo',
  'ap-northeast-2': 'Seoul',
  'ap-northeast-3': 'Osaka',
  'me-south-1': 'Bahrain',
  'me-central-1': 'UAE',
  'af-south-1': 'Cape Town',
  'il-central-1': 'Israel',
}

export function Shell({ activeHref, breadcrumbs = [], children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { meta, me, account, region, setRegion } = useSession()
  const themeToggle = useThemeToggle()
  const [navOpen, setNavOpen] = useState(true)
  const [search, setSearch] = useState('')
  const [catalogue, setCatalogue] = useState(null)

  useEffect(() => {
    loadCatalogue().then(setCatalogue).catch(() => setCatalogue(null))
  }, [])

  const serviceNames = useMemo(() => {
    const names = new Set(Object.keys(catalogue?.services || {}))
    for (const group of catalogue?.groups || []) {
      for (const name of group.services) names.add(name)
    }
    return [...names].sort()
  }, [catalogue])

  const go = (href) => {
    if (href.startsWith('http')) {
      window.location.assign(href)
      return
    }
    navigate(href)
  }

  const enabled = meta?.regions || []
  const missing = Math.max((meta?.all_regions || []).length - enabled.length, 0)
  const regionItems = [
    ...enabled.map((name) => ({
      id: name,
      text: `${REGION_NAMES[name] || name} · ${name}`,
    })),
    { id: 'divider', text: '-', disabled: true },
    {
      id: 'missing',
      text: `${missing} region${missing === 1 ? '' : 's'} not enabled`,
      disabled: true,
    },
    { id: 'manage', text: 'Manage regions' },
  ]

  return (
    <>
      <TopNavigation
        id="top-nav"
        identity={{
          href: '/',
          // The product owns the chrome: the mark is Emuplane's and the title is
          // the product name. Which backend is being fronted is operator
          // context, not branding — it lives in About and in `/api/meta`.
          title: 'Emuplane',
          logo: {
            src: '/emuplane.png',
            alt: 'Emuplane',
          },
          onFollow: (event) => {
            event.preventDefault()
            go('/')
          },
        }}
        search={
          <Autosuggest
            value={search}
            onChange={({ detail }) => setSearch(detail.value)}
            onSelect={({ detail }) => {
              if (!detail.value) return
              setSearch('')
              go(`/resources/${detail.value}`)
            }}
            options={serviceNames
              .filter((name) => name.includes(search.toLowerCase()))
              .slice(0, 12)
              .map((name) => ({ value: name, label: serviceLabel(name) }))}
            placeholder="Find a service"
            ariaLabel="Find a service"
            empty="No service matches"
          />
        }
        utilities={[
          themeToggle,
          {
            type: 'menu-dropdown',
            text: region,
            iconName: 'globe',
            ariaLabel: 'Region',
            items: regionItems,
            onItemClick: ({ detail }) => {
              if (detail.id === 'manage') {
                go('/settings')
                return
              }
              if (detail.id === 'divider' || detail.id === 'missing') return
              setRegion(detail.id)
            },
          },
          {
            type: 'menu-dropdown',
            text: me?.user || 'Signed in',
            iconName: 'user-profile',
            ariaLabel: 'Your session',
            items: [
              { id: 'account', text: `Account ${account || '—'}`, disabled: true },
              { id: 'settings', text: 'Settings' },
              { id: 'about', text: 'About' },
              { id: 'logout', text: 'Sign out' },
            ],
            onItemClick: ({ detail }) => {
              if (detail.id === 'logout') {
                window.location.assign('/logout')
                return
              }
              go(`/${detail.id}`)
            },
          },
        ]}
      />

      <AppLayout
        headerSelector="#top-nav"
        navigationOpen={navOpen}
        onNavigationChange={({ detail }) => setNavOpen(detail.open)}
        navigation={
          <SideNavigation
            activeHref={activeHref || location.pathname}
            items={navItems()}
            onFollow={({ detail }) => {
              if (detail.href.startsWith('http') || detail.href === '#') return
              go(detail.href)
            }}
          />
        }
        breadcrumbs={
          <BreadcrumbGroup
            items={[{ text: 'MiniStack', href: '/' }, ...breadcrumbs]}
            onFollow={({ detail }) => {
              if (detail.href.startsWith('http')) return
              go(detail.href)
            }}
          />
        }
        content={children}
        toolsHide
      />
    </>
  )
}
