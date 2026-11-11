import { useCallback, useEffect, useState } from 'react'
import { applyMode, Mode } from '@cloudscape-design/global-styles'

const FAV_PREFIX = 'ministack:favorites'
const FAV_EVENT = 'ministack:favorites-changed'

// Browser state is scoped to the signed-in account: a new account (or a wiped
// database, which mints new IDs) starts with an empty list instead of replaying
// whatever the previous tenancy left behind.
const keyFor = (prefix, scope) => `${prefix}:${scope || 'anon'}`

function readFavorites(key) {
  try {
    const stored = localStorage.getItem(key)
    return stored ? JSON.parse(stored) : []
  } catch {
    return []
  }
}

// Service-level favorites, mirrored in every hook instance and the top-nav pins.
export function useFavorites(scope) {
  const key = keyFor(FAV_PREFIX, scope)
  const [favorites, setFavorites] = useState(() => readFavorites(key))

  useEffect(() => {
    setFavorites(readFavorites(key))
    const sync = () => setFavorites(readFavorites(key))
    window.addEventListener(FAV_EVENT, sync)
    return () => window.removeEventListener(FAV_EVENT, sync)
  }, [key])

  const toggleFavorite = useCallback((service) => {
    const current = readFavorites(key)
    const next = current.includes(service)
      ? current.filter((item) => item !== service)
      : [...current, service]
    localStorage.setItem(key, JSON.stringify(next))
    window.dispatchEvent(new Event(FAV_EVENT))
  }, [key])

  const isFavorite = useCallback(
    (service) => favorites.includes(service),
    [favorites],
  )

  return { favorites, toggleFavorite, isFavorite }
}

export function applyTheme(theme) {
  const prefersDark =
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-color-scheme: dark)').matches
  const dark = theme === 'dark' || (theme === 'system' && prefersDark)
  applyMode(dark ? Mode.Dark : Mode.Light)
}

const RECENT_PREFIX = 'ministack:recent'
const RECENT_EVENT = 'ministack:recent-changed'

function readRecent(key) {
  try {
    const stored = localStorage.getItem(key)
    return stored ? JSON.parse(stored) : []
  } catch {
    return []
  }
}

// Recently visited services, newest first, shared by the dashboard and shell.
export function useRecent(scope) {
  const key = keyFor(RECENT_PREFIX, scope)
  const [recent, setRecent] = useState(() => readRecent(key))

  useEffect(() => {
    setRecent(readRecent(key))
    const sync = () => setRecent(readRecent(key))
    window.addEventListener(RECENT_EVENT, sync)
    return () => window.removeEventListener(RECENT_EVENT, sync)
  }, [key])

  const addRecent = useCallback((service) => {
    const next = [service, ...readRecent(key).filter((item) => item !== service)].slice(0, 8)
    localStorage.setItem(key, JSON.stringify(next))
    window.dispatchEvent(new Event(RECENT_EVENT))
  }, [key])

  return { recent, addRecent }
}

export function useTheme() {
  const [theme, setThemeState] = useState(
    () => localStorage.getItem('ministack:theme') || 'system',
  )

  const setTheme = useCallback((next) => {
    localStorage.setItem('ministack:theme', next)
    applyTheme(next)
    setThemeState(next)
  }, [])

  return { theme, setTheme }
}
