import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Waitlist from './pages/Waitlist'
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

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/waitlist" element={<Waitlist />} />
        <Route path="/onboarding" element={<Onboarding />} />

        <Route path="/app" element={<RequireAuth><Navigate to="/app/upload" replace /></RequireAuth>} />
        <Route path="/app/upload" element={<RequireAuth><AppLayout><Upload /></AppLayout></RequireAuth>} />
        <Route path="/app/dashboard" element={<RequireAuth><AppLayout><Dashboard /></AppLayout></RequireAuth>} />
        <Route path="/app/chat" element={<RequireAuth><AppLayout><Chat /></AppLayout></RequireAuth>} />
        <Route path="/app/projects" element={<RequireAuth><AppLayout><Goals /></AppLayout></RequireAuth>} />
        <Route path="/app/transactions" element={<RequireAuth><AppLayout><Transactions /></AppLayout></RequireAuth>} />
        <Route path="/app/settings" element={<RequireAuth><AppLayout><Settings /></AppLayout></RequireAuth>} />

        {/* Backward compatibility: old /app/goals URL redirects to new /app/projects */}
        <Route path="/app/goals" element={<Navigate to="/app/projects" replace />} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
