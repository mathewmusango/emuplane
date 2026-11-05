import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(cleanup)

// jsdom has no layout engine; Cloudscape's app layout and autosuggest only
// observe, so a no-op observer is enough to render them.
class Observer {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return []
  }
}

globalThis.ResizeObserver = globalThis.ResizeObserver || Observer
globalThis.IntersectionObserver = globalThis.IntersectionObserver || Observer

if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })
}

if (!window.scrollTo) {
  window.scrollTo = () => {}
}

vi.stubGlobal('scrollTo', () => {})
