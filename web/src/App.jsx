import { Routes, Route, Navigate } from 'react-router-dom'
import ErrorBoundary from '@cloudscape-design/components/error-boundary'
import Dashboard from './pages/Dashboard'
import Services from './pages/Services'
import Resources from './pages/Resources'
import Settings from './pages/Settings'
import About from './pages/About'
import SignIn from './pages/SignIn'

export default function App() {
  return (
    <ErrorBoundary onError={({ error }) => console.error('ministack console:', error)}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/services" element={<Services />} />
        <Route path="/resources" element={<Navigate to="/services" replace />} />
        <Route path="/resources/:service" element={<Resources />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/about" element={<About />} />
        {/* The sign-in screens are the login page: the control plane serves this
            route without a session and POST /api/auth/login mints the cookie. */}
        <Route path="/login" element={<SignIn />} />
        <Route path="/signin" element={<SignIn />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  )
}
