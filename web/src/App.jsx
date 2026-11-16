import { Routes, Route, Navigate, useParams } from 'react-router-dom'
import ErrorBoundary from '@cloudscape-design/components/error-boundary'
import Dashboard from './pages/Dashboard'
import Services from './pages/Services'
import Resources from './pages/Resources'
import CreateBucket from './pages/CreateBucket'
import S3Section from './pages/S3Section'
import BucketDetail from './pages/BucketDetail'
import Settings from './pages/Settings'
import About from './pages/About'
import SignIn from './pages/SignIn'
import { useSession } from './context'

/** The console's service path is `/<service>/home?region=<region>`, the shape the
 *  real console uses, so a link reproduces the account's view. The old
 *  `/resources/<service>` path redirects into it. */
function ServiceRedirect() {
  const { service = 's3' } = useParams()
  const { region } = useSession()
  return <Navigate to={`/${service}/home?region=${region}`} replace />
}

export default function App() {
  return (
    <ErrorBoundary onError={({ error }) => console.error('ministack console:', error)}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/services" element={<Services />} />
        <Route path="/resources" element={<Navigate to="/services" replace />} />
        {/* S3's create is its own page, the way the console does it: one form
            with the region, ownership, access, versioning, tags, encryption and
            Object Lock, applied in a single request. */}
        <Route path="/s3/create" element={<CreateBucket />} />
        {/* S3 Tables and S3 Files are children of S3 in the console, so their
            pages hang off the S3 nav rather than existing as services of their
            own (`/s3tables/home` and friends are not pages). Directory and vector
            buckets are not pages at all: this emulator serves neither. */}
        <Route path="/s3/table-buckets" element={<S3Section section="table-buckets" />} />
        <Route path="/s3/files" element={<S3Section section="files" />} />
        {/* One bucket is its own page, with the tabs this instance backs. */}
        <Route path="/s3/buckets/:name" element={<BucketDetail />} />
        <Route path="/:service/home" element={<Resources />} />
        <Route path="/resources/:service" element={<ServiceRedirect />} />
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
