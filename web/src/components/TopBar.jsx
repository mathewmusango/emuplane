import { useEffect, useRef, useState } from 'react'
import {
  Bell,
  ChevronDown,
  Copy,
  LayoutGrid,
  HelpCircle,
  Moon,
  Search,
  Settings,
  Star,
  Sun,
} from 'lucide-react'
import { api } from '../api'
import { serviceLabel } from '../serviceLabels'
import {
  enableMultiSession,
  forgetIdentity,
  multiSessionEnabled,
  readIdentities,
  remember,
} from '../identityStore'
import './topbar.css'

// The console bar: mark, favourites, the services grid, search, then the
// operator cluster on the right. Custom rather than Cloudscape's TopNavigation
// because the services button has to sit *before* the search — that is where the
// console puts it, and TopNavigation has no slot there.

const REGION_NAMES = {
  'us-east-1': 'N. Virginia',
  'us-east-2': 'Ohio',
  'us-west-1': 'N. California',
  'us-west-2': 'Oregon',
  'eu-west-1': 'Ireland',
  'eu-west-2': 'London',
  'eu-west-3': 'Paris',
  'eu-central-1': 'Frankfurt',
  'eu-north-1': 'Stockholm',
  'ap-south-1': 'Mumbai',
  'ap-southeast-1': 'Singapore',
  'ap-southeast-2': 'Sydney',
  'ap-northeast-1': 'Tokyo',
  'ap-northeast-2': 'Seoul',
  'sa-east-1': 'São Paulo',
  'ca-central-1': 'Canada Central',
  'af-south-1': 'Cape Town',
  'me-south-1': 'Bahrain',
  'il-central-1': 'Israel',
}

const groupId = (accountId) => {
  const id = (accountId || '').replace(/\D/g, '')
  if (id.length !== 12) return accountId || '—'
  return `${id.slice(0, 4)}-${id.slice(4, 8)}-${id.slice(8)}`
}

export default function TopBar({
  me,
  account,
  accountName,
  regions,
  region,
  onRegion,
  serviceNames,
  servicesOpen,
  onToggleServices,
  onPickService,
  onNavigate,
  dark,
  onToggleTheme,
}) {
  const [search, setSearch] = useState('')
  const [accountOpen, setAccountOpen] = useState(false)
  const [regionOpen, setRegionOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [multi, setMulti] = useState(() => multiSessionEnabled())
  const [identities, setIdentities] = useState(() => readIdentities())
  const [busy, setBusy] = useState(false)
  const accountRef = useRef(null)
  const regionRef = useRef(null)

  useEffect(() => {
    const onClick = (event) => {
      if (accountRef.current && !accountRef.current.contains(event.target)) {
        setAccountOpen(false)
      }
      if (regionRef.current && !regionRef.current.contains(event.target)) {
        setRegionOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const matches = serviceNames
    .filter((name) => name.includes(search.trim().toLowerCase()))
    .slice(0, 6)
  const isRoot = (me?.role || 'root') === 'root'

  const submit = (event) => {
    event.preventDefault()
    if (!search.trim()) return
    if (matches.length) onPickService(matches[0])
    setSearch('')
  }

  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(account || '')
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard denied: the ID is on screen anyway
    }
  }

  return (
    <header className="topbar" id="topbar">
      <button
        type="button"
        className="topbar__logo"
        aria-label="Console Home"
        onClick={() => onNavigate('/')}
      >
        <img src="/emuplane.png" alt="Emuplane" />
      </button>

      <button
        type="button"
        className="topbar__icon"
        title="Favorites"
        aria-label="Favorites"
        onClick={() => onNavigate('/favorites')}
      >
        <Star size={18} />
      </button>

      <button
        type="button"
        className={`topbar__icon${servicesOpen ? ' is-active' : ''}`}
        title="Services"
        aria-label="Services"
        aria-expanded={servicesOpen}
        onClick={onToggleServices}
      >
        <LayoutGrid size={18} />
      </button>

      <form className="topbar__search" onSubmit={submit} role="search">
        <Search size={16} aria-hidden="true" />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search"
          aria-label="Search services"
        />
        <kbd>Alt+S</kbd>
      </form>

      <div className="topbar__right">
        <button
          type="button"
          className="topbar__icon"
          title="Notifications"
          aria-label="Notifications"
          onClick={() => onNavigate('/about')}
        >
          <Bell size={18} />
        </button>
        <button
          type="button"
          className="topbar__icon"
          title="Help"
          aria-label="Help"
          onClick={() => onNavigate('/about')}
        >
          <HelpCircle size={18} />
        </button>
        <button
          type="button"
          className="topbar__icon"
          title="Settings"
          aria-label="Settings"
          onClick={() => onNavigate('/settings')}
        >
          <Settings size={18} />
        </button>
        <button
          type="button"
          className="topbar__icon"
          title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          onClick={onToggleTheme}
        >
          {dark ? <Sun size={18} /> : <Moon size={18} />}
        </button>

        <div className="topbar__region" ref={regionRef}>
          <button
            type="button"
            className="topbar__text"
            aria-expanded={regionOpen}
            onClick={() => setRegionOpen((open) => !open)}
          >
            {REGION_NAMES[region] || region} <ChevronDown size={14} />
          </button>
          {regionOpen && (
            <ul className="topbar__menu topbar__menu--region" role="menu">
              {(regions || []).map((name) => (
                <li key={name}>
                  <button
                    type="button"
                    role="menuitem"
                    className={name === region ? 'is-current' : ''}
                    onClick={() => {
                      onRegion(name)
                      setRegionOpen(false)
                    }}
                  >
                    {REGION_NAMES[name] || name} <span>{name}</span>
                  </button>
                </li>
              ))}
              <li>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    onNavigate('/settings')
                    setRegionOpen(false)
                  }}
                >
                  Manage regions
                </button>
              </li>
            </ul>
          )}
        </div>

        <div className="topbar__account" ref={accountRef}>
          <button
            type="button"
            className="topbar__chip"
            aria-expanded={accountOpen}
            onClick={() => {
              setIdentities(readIdentities())
              setMulti(multiSessionEnabled())
              setAccountOpen((open) => !open)
            }}
          >
            {accountName || 'Account'}
            {' ('}
            {account || '—'}
            {')'}
            <ChevronDown size={14} />
          </button>
          <span className="topbar__chip-label">
            {isRoot ? accountName || 'Account' : me?.user || 'IAM user'}
          </span>

          {accountOpen && (
            <div className="topbar__menu topbar__menu--account" role="menu">
              {/* Root sees the account's identity; an IAM user sees the alias and
                  its own username — the console draws the same distinction. */}
              {isRoot ? (
                <>
                  <div className="topbar__field">
                    <span>Account ID</span>
                    <div className="topbar__copy">
                      <code>{groupId(account)}</code>
                      <button
                        type="button"
                        aria-label="Copy account ID"
                        title={copied ? 'Copied' : 'Copy account ID'}
                        onClick={copyId}
                      >
                        <Copy size={14} />
                      </button>
                    </div>
                  </div>
                  <div className="topbar__field">
                    <span>Account name</span>
                    <strong>{accountName || account || '—'}</strong>
                  </div>
                  <div className="topbar__field">
                    <span>Account colour</span>
                    <strong className="topbar__colour">
                      <i aria-hidden="true" /> Orange
                    </strong>
                  </div>
                </>
              ) : (
                <>
                  <div className="topbar__field">
                    <span>Account alias</span>
                    <strong>{accountName || account || '—'}</strong>
                  </div>
                  <div className="topbar__field">
                    <span>IAM user</span>
                    <strong>{me?.user || '—'}</strong>
                  </div>
                  <div className="topbar__field">
                    <span>Account ID</span>
                    <div className="topbar__copy">
                      <code>{groupId(account)}</code>
                      <button
                        type="button"
                        aria-label="Copy account ID"
                        title={copied ? 'Copied' : 'Copy account ID'}
                        onClick={copyId}
                      >
                        <Copy size={14} />
                      </button>
                    </div>
                  </div>
                </>
              )}

              <hr />
              <button type="button" role="menuitem" onClick={() => onNavigate('/settings')}>
                Account
              </button>
              <button type="button" role="menuitem" onClick={() => onNavigate('/about')}>
                Service quotas
              </button>
              <button type="button" role="menuitem" onClick={() => onNavigate('/settings')}>
                Security credentials
              </button>
              {multi && identities.length > 0 && (
                <>
                  <hr />
                  <div className="topbar__field">
                    <span>Switch identity</span>
                  </div>
                  {identities.map((item) => (
                    <button
                      key={`${item.account}:${item.user}`}
                      type="button"
                      role="menuitem"
                      className="topbar__identity"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true)
                        try {
                          await api.switchIdentity(item.token)
                          window.location.assign('/')
                        } catch {
                          // The token died (signed out elsewhere): forget it.
                          forgetIdentity(item.user, item.account)
                          setIdentities(readIdentities())
                          setBusy(false)
                        }
                      }}
                    >
                      {item.user}
                      <span>
                        {item.role} · {item.alias || item.account}
                      </span>
                    </button>
                  ))}
                </>
              )}

              <hr />
              <div className="topbar__footer">
                <button
                  type="button"
                  className="topbar__box"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true)
                    if (multi) {
                      enableMultiSession(false)
                      setMulti(false)
                      setIdentities([])
                      setBusy(false)
                      return
                    }
                    // Turning it on stores this session, so switching works
                    // straight away rather than from the next sign-in.
                    try {
                      const current = await api.remember()
                      enableMultiSession(true)
                      if (current?.token) remember(current)
                      setMulti(true)
                      setIdentities(readIdentities())
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  {multi
                    ? 'Turn off multi-session support'
                    : 'Turn on multi-session support'}
                </button>
                {!isRoot && (
                  <button
                    type="button"
                    className="topbar__box"
                    onClick={() => window.location.assign('/logout')}
                  >
                    Switch role
                  </button>
                )}
                <button
                  type="button"
                  className="topbar__signout"
                  onClick={() => window.location.assign('/logout')}
                >
                  Sign out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* The search box shows what Enter will open, the way the console's does. */}
      {search.trim() && matches.length > 0 && (
        <ul className="topbar__suggestions">
          {matches.map((name) => (
            <li key={name}>
              <button
                type="button"
                onMouseDown={(event) => {
                  event.preventDefault()
                  onPickService(name)
                  setSearch('')
                }}
              >
                {serviceLabel(name)}
              </button>
            </li>
          ))}
        </ul>
      )}
    </header>
  )
}
