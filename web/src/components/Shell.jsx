import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import AppLayout from '@cloudscape-design/components/app-layout'
import BreadcrumbGroup from '@cloudscape-design/components/breadcrumb-group'
import SideNavigation from '@cloudscape-design/components/side-navigation'
import { useSession } from '../context'
import { api } from '../api'
import { useThemeMode } from './themeToggle'
import TopBar from './TopBar'
import { serviceLabel, serviceLongName } from '../serviceLabels'
import ServicesMenu from './ServicesMenu'

const navItems = () => [
  { type: 'link', text: 'Home', href: '/' },
  { type: 'link', text: 'All services', href: '/services' },
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
  const { dark, toggle: toggleTheme } = useThemeMode()
  const [navOpen, setNavOpen] = useState(true)
  const [search, setSearch] = useState('')
  const [catalogue, setCatalogue] = useState(null)
  const [servicesOpen, setServicesOpen] = useState(false)

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

  // On `/<service>/home` the sidebar is the service's own: what it lists here is
  // what this console can actually do with it. S3 hangs more pages off that nav
  // (create, and the bucket types and files tabs), and they all belong to it.
  const serviceHome = (() => {
    const parts = location.pathname.split('/').filter(Boolean)
    if (parts[0] === 's3') return 's3'
    return parts.length === 2 && (parts[1] === 'home' || parts[1] === 'create')
      ? parts[0]
      : ''
  })()
  const serviceBase = serviceHome ? `/${serviceHome}/home` : ''

  const serviceNav = () => {
    if (serviceHome === 's3') {
      return [
        {
          type: 'section',
          text: 'Buckets',
          items: [
            {
              type: 'link',
              text: 'General purpose buckets',
              href: serviceBase,
            },
            { type: 'link', text: 'Table buckets', href: '/s3/table-buckets' },
          ],
        },
        {
          type: 'section',
          text: 'Files',
          items: [
            { type: 'link', text: 'File systems', href: '/s3/files' },
          ],
        },
        { type: 'divider' },
        { type: 'link', text: 'All services', href: '/services' },
      ]
    }
    return [
      { type: 'link', text: 'Resources', href: serviceBase },
      { type: 'divider' },
      { type: 'link', text: 'All services', href: '/services' },
    ]
  }

  // Write the region into the URL at the moment the picker is used. The page
  // also syncs it from an effect, but doing it here means the address bar changes
  // on the click itself — no render scheduling involved.
  const changeRegion = (name) => {
    setRegion(name)
    const parts = location.pathname.split('/').filter(Boolean)
    if (parts.length === 2 && parts[1] === 'home') {
      navigate(
        { pathname: location.pathname, search: `?region=${name}` },
        { replace: true },
      )
    }
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
      <TopBar
        me={me}
        account={account}
        accountName={meta?.accounts?.find((item) => item.account_id === account)?.name || ''}
        accountAlias={meta?.accounts?.find((item) => item.account_id === account)?.alias
          || meta?.me?.alias
          || ''}
        regions={meta?.regions || []}
        region={region}
        onRegion={changeRegion}
        serviceNames={serviceNames}
        servicesOpen={servicesOpen}
        onToggleServices={() => setServicesOpen((open) => !open)}
        onPickService={(name) => go(`/${name}/home`)}
        onNavigate={go}
        dark={dark}
        onToggleTheme={toggleTheme}
      />

      {servicesOpen && (
        <ServicesMenu
          names={serviceNames}
          account={account}
          onClose={() => setServicesOpen(false)}
          onPick={(name) => go(`/resources/${name}`)}
        />
      )}

      <div className="console-offset">
      <AppLayout
        navigationOpen={navOpen}
        onNavigationChange={({ detail }) => setNavOpen(detail.open)}
        navigation={
          <SideNavigation
            header={
              serviceHome
                ? { text: serviceLongName(serviceHome), href: serviceBase }
                : undefined
            }
            activeHref={
              serviceHome === 's3'
                ? location.pathname === '/s3/create'
                  ? serviceBase
                  : location.pathname
                : serviceHome
                  ? serviceBase
                  : activeHref || location.pathname
            }
            items={serviceHome ? serviceNav() : navItems()}
            onFollow={({ detail }) => {
              if (detail.href.startsWith('http') || detail.href === '#') return
              go(detail.href)
            }}
          />
        }
        breadcrumbs={
          <BreadcrumbGroup
            items={[{ text: 'Home', href: '/' }, ...breadcrumbs]}
            onFollow={({ detail }) => {
              if (detail.href.startsWith('http')) return
              go(detail.href)
            }}
          />
        }
        content={children}
        toolsHide
      />
      </div>
    </>
  )
}
