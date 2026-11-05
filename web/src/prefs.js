import { useCallback, useEffect, useState } from 'react'
import { applyMode, Mode } from '@cloudscape-design/global-styles'

const FAV_KEY = 'ministack:favorites'
const FAV_EVENT = 'ministack:favorites-changed'

function readFavorites() {
  try {
    const stored = localStorage.getItem(FAV_KEY)
    return stored ? JSON.parse(stored) : []
  } catch {
    return []
  }
}

// Service-level favorites, mirrored in every hook instance and the top-nav pins.
export function useFavorites() {
  const [favorites, setFavorites] = useState(readFavorites)

  useEffect(() => {
    const sync = () => setFavorites(readFavorites())
    window.addEventListener(FAV_EVENT, sync)
    return () => window.removeEventListener(FAV_EVENT, sync)
  }, [])

  const toggleFavorite = useCallback((service) => {
    const current = readFavorites()
    const next = current.includes(service)
      ? current.filter((item) => item !== service)
      : [...current, service]
    localStorage.setItem(FAV_KEY, JSON.stringify(next))
    window.dispatchEvent(new Event(FAV_EVENT))
  }, [])

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

const RECENT_KEY = 'ministack:recent'
const RECENT_EVENT = 'ministack:recent-changed'

function readRecent() {
  try {
    const stored = localStorage.getItem(RECENT_KEY)
    return stored ? JSON.parse(stored) : []
  } catch {
    return []
  }
}

// Recently visited services, newest first, shared by the dashboard and shell.
export function useRecent() {
  const [recent, setRecent] = useState(readRecent)

  useEffect(() => {
    const sync = () => setRecent(readRecent())
    window.addEventListener(RECENT_EVENT, sync)
    return () => window.removeEventListener(RECENT_EVENT, sync)
  }, [])

  const addRecent = useCallback((service) => {
    const next = [service, ...readRecent().filter((item) => item !== service)].slice(0, 8)
    localStorage.setItem(RECENT_KEY, JSON.stringify(next))
    window.dispatchEvent(new Event(RECENT_EVENT))
  }, [])

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
