import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Login from './pages/Login'
import Signup from './pages/Signup'
import VerifyEmail from './pages/VerifyEmail'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import TwoFactor from './pages/TwoFactor'
import Landing from './pages/Landing'
import Onboarding from './pages/Onboarding'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import Chat from './pages/Chat'
import Goals from './pages/Goals'
import Transactions from './pages/Transactions'
import Sidebar from './pages/Sidebar'
import AppHeader from './pages/AppHeader'
import Settings from './pages/Settings'
import ToastHost from './pages/ToastHost'

function AppLayout({ children }) {
  return (
    <div style={{
      background: '#fafaf5',
      minHeight: '100vh',
      display: 'flex',
      color: '#1a1a1a',
    }}>
      <Sidebar />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <AppHeader />
        <main style={{ flex: 1, padding: '24px 32px' }}>
          {children}
        </main>
      </div>
    </div>
  )
}

function RequireAuth({ children }) {
  const token = localStorage.getItem('auth_token')
  if (!token) return <Navigate to="/login" replace />
  return children
}

/** Preserve query string when normalizing email deep-links. */
function RedirectWithSearch({ to }) {
  const location = useLocation()
  return <Navigate to={`${to}${location.search}${location.hash}`} replace />
}

/**
 * Safety net for auth email links. Never send these paths to Landing.
 * Handles trailing slashes and unexpected path prefixes.
 */
function FallbackRoute() {
  const location = useLocation()
  const path = location.pathname.replace(/\/+$/, '') || '/'

  if (path === '/verify-email' || path.endsWith('/verify-email')) {
    return <VerifyEmail />
  }
  if (path === '/auth/verify-email') {
    return <VerifyEmail />
  }
  if (path === '/forgot-password' || path.endsWith('/forgot-password')) {
    return <ForgotPassword />
  }
  if (path === '/auth/forgot-password') {
    return <ForgotPassword />
  }
  // Email links use /reset-password — keep users on the reset form, never Landing.
  if (path === '/reset-password' || path.endsWith('/reset-password')) {
    return <ResetPassword />
  }
  if (path === '/auth/reset-password') {
    return <ResetPassword />
  }
  if (path === '/auth/two-factor' || path.endsWith('/two-factor')) {
    return <TwoFactor />
  }

  return <Navigate to="/" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastHost />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/onboarding" element={<Onboarding />} />

        {/* Public auth email links — must not be wrapped in RequireAuth */}
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/auth/verify-email" element={<VerifyEmail />} />

        <Route path="/auth/forgot-password" element={<ForgotPassword />} />
        <Route path="/forgot-password" element={<RedirectWithSearch to="/auth/forgot-password" />} />

        {/* Canonical reset page + email-link alias (backend sends /reset-password?token&eid) */}
        <Route path="/auth/reset-password" element={<ResetPassword />} />
        <Route path="/reset-password" element={<RedirectWithSearch to="/auth/reset-password" />} />

        <Route path="/auth/two-factor" element={<TwoFactor />} />

        <Route path="/app" element={<RequireAuth><Navigate to="/app/upload" replace /></RequireAuth>} />
        <Route path="/app/upload" element={<RequireAuth><AppLayout><Upload /></AppLayout></RequireAuth>} />
        <Route path="/app/dashboard" element={<RequireAuth><AppLayout><Dashboard /></AppLayout></RequireAuth>} />
        <Route path="/app/chat" element={<RequireAuth><AppLayout><Chat /></AppLayout></RequireAuth>} />
        <Route path="/app/projects" element={<RequireAuth><AppLayout><Goals /></AppLayout></RequireAuth>} />
        <Route path="/app/transactions" element={<RequireAuth><AppLayout><Transactions /></AppLayout></RequireAuth>} />
        <Route path="/app/settings" element={<RequireAuth><AppLayout><Settings /></AppLayout></RequireAuth>} />

        {/* Backward compatibility: old /app/goals URL redirects to new /app/projects */}
        <Route path="/app/goals" element={<Navigate to="/app/projects" replace />} />

        <Route path="*" element={<FallbackRoute />} />
      </Routes>
    </BrowserRouter>
  )
}
