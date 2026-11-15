import { useEffect, useMemo, useRef, useState } from 'react'
import { serviceLabel } from '../serviceLabels'
import { describeService, groupByCategory } from '../serviceCatalogue'
import './services-menu.css'

// The services menu: a category rail on the left, the services themselves on the
// right. Two panes are computed — what you visited, and everything — and every
// category is a third. Alphabetical inside a pane, as the console does it.

const recentKey = (account) => `emuplane:recent:${account || 'anon'}`

export function readRecent(account) {
  try {
    const raw = JSON.parse(localStorage.getItem(recentKey(account)) || '[]')
    return Array.isArray(raw) ? raw.filter((item) => typeof item === 'string') : []
  } catch {
    return []
  }
}

export function rememberService(account, name) {
  try {
    const next = [name, ...readRecent(account).filter((item) => item !== name)].slice(0, 8)
    localStorage.setItem(recentKey(account), JSON.stringify(next))
  } catch {
    // storage denied: the menu just starts empty
  }
}

export default function ServicesMenu({ names, account, onClose, onPick }) {
  const [pane, setPane] = useState('recent')
  const panel = useRef(null)

  const grouped = useMemo(() => groupByCategory(names), [names])
  const categories = grouped.map((group) => group.category)
  const recent = useMemo(() => readRecent(account), [account])

  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const list = () => {
    if (pane === 'recent') {
      return [...new Set(recent)].filter((name) => names.includes(name)).sort()
    }
    if (pane === 'all') return [...names].sort()
    const group = grouped.find((item) => item.category === pane)
    return group ? group.services : []
  }

  const title =
    pane === 'recent' ? 'Recently visited' : pane === 'all' ? 'All services' : pane

  const choose = (name) => {
    rememberService(account, name)
    onPick(name)
    onClose()
  }

  return (
    <>
      <div className="services-menu__scrim" onClick={onClose} aria-hidden="true" />
      <div
        className="services-menu"
        role="dialog"
        aria-label="Services"
        ref={panel}
      >
        <div className="services-menu__nav">
          <button
            type="button"
            className={`services-menu__link${pane === 'recent' ? ' is-active' : ''}`}
            onClick={() => setPane('recent')}
          >
            Recently visited
          </button>
          <button
            type="button"
            className={`services-menu__link${pane === 'all' ? ' is-active' : ''}`}
            onClick={() => setPane('all')}
          >
            All services
          </button>
          <hr className="services-menu__rule" />
          {categories.map((category) => (
            <button
              key={category}
              type="button"
              className={`services-menu__link${pane === category ? ' is-active' : ''}`}
              onClick={() => setPane(category)}
            >
              {category}
            </button>
          ))}
        </div>

        <div className="services-menu__list">
          <h2 className="services-menu__title">{title}</h2>
          {list().length === 0 ? (
            <p className="services-menu__empty">
              {pane === 'recent'
                ? 'Nothing visited yet. Open a service and it lands here.'
                : 'Nothing in this category.'}
            </p>
          ) : (
            <ul className="services-menu__items">
              {list().map((name) => (
                <li key={name}>
                  <button
                    type="button"
                    className="services-menu__item"
                    onClick={() => choose(name)}
                  >
                    <span className="services-menu__name">{serviceLabel(name)}</span>
                    <span className="services-menu__desc">{describeService(name)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </>
  )
}
