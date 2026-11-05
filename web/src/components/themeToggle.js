import { useTheme } from '../prefs'

const SUN = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="%23e9ebed" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>`

const MOON = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="%23e9ebed" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>`

// Cloudscape's top navigation only renders its own utility types, so the
// toggle is exposed as a utility object rather than a custom element.
export function useThemeToggle() {
  const { theme, setTheme } = useTheme()
  const systemDark =
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  const dark = theme === 'system' ? systemDark : theme === 'dark'
  return {
    type: 'button',
    iconUrl: `data:image/svg+xml;utf8,${dark ? SUN : MOON}`,
    iconAlt: dark ? 'Switch to light mode' : 'Switch to dark mode',
    ariaLabel: dark ? 'Switch to light mode' : 'Switch to dark mode',
    onClick: () => setTheme(dark ? 'light' : 'dark'),
  }
}
