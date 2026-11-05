import { Routes, Route, Navigate } from 'react-router-dom'
import ErrorBoundary from '@cloudscape-design/components/error-boundary'
import Dashboard from './pages/Dashboard'
import Services from './pages/Services'
import Resources from './pages/Resources'
import Favorites from './pages/Favorites'
import Accounts from './pages/Accounts'
import Onboarding from './pages/Onboarding'
import Settings from './pages/Settings'
import About from './pages/About'

export default function App() {
  return (
    <ErrorBoundary onError={({ error }) => console.error('ministack console:', error)}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/services" element={<Services />} />
        <Route path="/resources" element={<Navigate to="/services" replace />} />
        <Route path="/resources/:service" element={<Resources />} />
        <Route path="/favorites" element={<Favorites />} />
        <Route path="/accounts" element={<Accounts />} />
        <Route path="/onboarding" element={<Onboarding />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/about" element={<About />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  )
}
