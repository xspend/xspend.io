import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Login from './pages/Login'
import Signup from './pages/Signup'
import Waitlist from './pages/Waitlist'
import Navbar from './pages/Navbar'
import Landing from './pages/Landing'
import Onboarding from './pages/Onboarding'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import Chat from './pages/Chat'
import Goals from './pages/Goals'
import Transactions from './pages/Transactions'

function AppLayout({ children }) {
  return (
    <div style={{ background:'#0a0a0f', minHeight:'100vh' }}>
      <Navbar />
      {children}
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
        <Route path="/login" element={import.meta.env.PROD ? <Navigate to="/waitlist" replace /> : <Login />} />
        <Route path="/signup" element={import.meta.env.PROD ? <Navigate to="/waitlist" replace /> : <Signup />} />
        <Route path="/waitlist" element={<Waitlist />} />
        <Route path="/onboarding" element={<Onboarding />} />

        <Route path="/app" element={<RequireAuth><Navigate to="/app/upload" replace /></RequireAuth>} />
        <Route path="/app/upload" element={<RequireAuth><AppLayout><Upload /></AppLayout></RequireAuth>} />
        <Route path="/app/dashboard" element={<RequireAuth><AppLayout><Dashboard /></AppLayout></RequireAuth>} />
        <Route path="/app/chat" element={<RequireAuth><AppLayout><Chat /></AppLayout></RequireAuth>} />
        <Route path="/app/goals" element={<RequireAuth><AppLayout><Goals /></AppLayout></RequireAuth>} />
        <Route path="/app/transactions" element={<RequireAuth><AppLayout><Transactions /></AppLayout></RequireAuth>} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
