import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@cloudscape-design/global-styles/index.css'
import { I18nProvider } from '@cloudscape-design/components/i18n'
import enMessages from '@cloudscape-design/components/i18n/messages/all.en'
import App from './App'
import { SessionProvider } from './context'
import { applyTheme } from './prefs'
import './styles.css'

const storedTheme = localStorage.getItem('emuplane:theme') || 'system'
applyTheme(storedTheme)
window
  .matchMedia?.('(prefers-color-scheme: dark)')
  .addEventListener?.('change', () => {
    const current = localStorage.getItem('emuplane:theme') || 'system'
    if (current === 'system') applyTheme('system')
  })

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <I18nProvider messages={[enMessages]}>
      <BrowserRouter>
        <SessionProvider>
          <App />
        </SessionProvider>
      </BrowserRouter>
    </I18nProvider>
  </React.StrictMode>,
)
