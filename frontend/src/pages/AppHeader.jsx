import { useState, useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { LogOut, ChevronDown, Settings as SettingsIcon } from 'lucide-react'
import { API_URL } from '../lib/config'
import {
  clearSession,
  logout,
  getErrorDetail,
  isNotAuthenticatedError,
} from '../lib/auth'
import { showToast } from '../lib/toast'
import { ConfirmDialog } from './AuthShell'

const TITLES = {
  '/app/upload':       'Upload',
  '/app/dashboard':    'Dashboard',
  '/app/transactions': 'Transactions',
  '/app/projects':     'Projects',
  '/app/chat':         'Chat',
  '/app/settings':     'Settings',
}

const COLORS = {
  bg:            '#fafaf5',
  border:        'rgba(0,0,0,0.08)',
  textPrimary:   '#1a1a1a',
  textSecondary: '#5a5a5a',
  textMuted:     '#8a8a85',
  iconHoverBg:   'rgba(0,0,0,0.05)',
  menuBg:        '#ffffff',
  accent:        '#e85d3c',
}

export default function AppHeader() {
  const location = useLocation()
  const navigate = useNavigate()
  const title = TITLES[location.pathname] || ''

  const [open, setOpen] = useState(false)
  const [profile, setProfile] = useState({ name: '', email: '' })
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)
  const menuRef = useRef(null)

  // Load name from localStorage immediately; fetch email/full name from /profile.
  useEffect(() => {
    const cachedName = localStorage.getItem('user_name') || ''
    const cachedEmail = localStorage.getItem('user_email') || ''
    setProfile({ name: cachedName, email: cachedEmail })
    fetch(`${API_URL}/profile`)
      .then(r => r.json())
      .then(p => {
        const name = p?.full_name || cachedName
        const email = p?.email || cachedEmail
        setProfile({ name, email })
        if (p?.full_name) localStorage.setItem('user_name', p.full_name.split(' ')[0])
        if (p?.email) localStorage.setItem('user_email', p.email)
      })
      .catch(() => {})
  }, [])

  // Close on click outside
  useEffect(() => {
    const onClick = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const openLogoutConfirm = () => {
    setOpen(false)
    setConfirmOpen(true)
  }

  const finishLocalLogout = ({ showSuccessToast }) => {
    clearSession()
    setConfirmOpen(false)
    setLoggingOut(false)
    if (showSuccessToast) {
      showToast('Logged out successfully.')
    }
    navigate('/login', { replace: true })
  }

  const handleConfirmLogout = async () => {
    if (loggingOut) return
    setLoggingOut(true)
    try {
      const { res, data } = await logout()

      if (res.ok) {
        finishLocalLogout({ showSuccessToast: true })
        return
      }

      if (isNotAuthenticatedError(res, data)) {
        // Already logged out on the server — clear local state, no error toast.
        finishLocalLogout({ showSuccessToast: false })
        return
      }

      showToast(
        getErrorDetail(data, 'Logout failed. Please try again.'),
        'error'
      )
      setLoggingOut(false)
    } catch {
      showToast('Logout failed. Please try again.', 'error')
      setLoggingOut(false)
    }
  }

  const displayName = profile.name || 'Account'
  const initial = (profile.name || profile.email || '?').trim().charAt(0).toUpperCase()

  return (
    <>
      <header style={{
        height: 64,
        background: COLORS.bg,
        borderBottom: `1px solid ${COLORS.border}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 32px',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        <div style={{
          fontWeight: 600,
          fontSize: 18,
          color: COLORS.textPrimary,
          letterSpacing: '-0.01em',
        }}>
          {title}
        </div>

        <div ref={menuRef} style={{ position: 'relative' }}>
          <button
            onClick={() => setOpen(o => !o)}
            aria-label="Account menu"
            style={{
              background: open ? COLORS.iconHoverBg : 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: '6px 10px 6px 8px',
              borderRadius: 10,
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              color: COLORS.textSecondary,
              transition: 'background 0.15s ease',
            }}
            onMouseEnter={e => e.currentTarget.style.background = COLORS.iconHoverBg}
            onMouseLeave={e => e.currentTarget.style.background = open ? COLORS.iconHoverBg : 'transparent'}
          >
            <span style={{
              width: 28, height: 28, borderRadius: '50%',
              background: COLORS.accent, color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 15, fontWeight: 700, flexShrink: 0,
            }}>
              {initial}
            </span>
            <ChevronDown size={15} strokeWidth={2} style={{
              transform: open ? 'rotate(180deg)' : 'none',
              transition: 'transform 0.15s ease',
            }}/>
          </button>

          {open && (
            <div style={{
              position: 'absolute',
              top: 'calc(100% + 8px)',
              right: 0,
              minWidth: 220,
              background: COLORS.menuBg,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 14,
              boxShadow: '0 12px 32px rgba(0,0,0,0.12)',
              padding: 6,
              zIndex: 100,
            }}>
              {/* Profile info */}
              <div style={{ padding: '10px 12px 12px' }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: COLORS.textPrimary, marginBottom: 2 }}>
                  {displayName}
                </div>
                <div style={{ fontSize: 14, color: COLORS.textMuted, wordBreak: 'break-all' }}>
                  {profile.email || 'No email on file'}
                </div>
              </div>

              <div style={{ height: 1, background: COLORS.border, margin: '2px 0 6px' }}/>

              {/* Settings */}
              <button
                onClick={() => { setOpen(false); navigate('/app/settings') }}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 12px',
                  background: 'transparent',
                  border: 'none',
                  borderRadius: 9,
                  cursor: 'pointer',
                  color: COLORS.textPrimary,
                  fontSize: 16,
                  fontWeight: 500,
                  textAlign: 'left',
                  transition: 'background 0.12s ease',
                }}
                onMouseEnter={e => e.currentTarget.style.background = COLORS.iconHoverBg}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <SettingsIcon size={16} strokeWidth={1.75} />
                Settings
              </button>

              {/* Sign out */}
              <button
                onClick={openLogoutConfirm}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 12px',
                  background: 'transparent',
                  border: 'none',
                  borderRadius: 9,
                  cursor: 'pointer',
                  color: COLORS.textPrimary,
                  fontSize: 16,
                  fontWeight: 500,
                  textAlign: 'left',
                  transition: 'background 0.12s ease',
                }}
                onMouseEnter={e => e.currentTarget.style.background = COLORS.iconHoverBg}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <LogOut size={16} strokeWidth={1.75} />
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>

      <ConfirmDialog
        open={confirmOpen}
        title="Log Out"
        cancelLabel="Cancel"
        confirmLabel="Log Out"
        loadingLabel="Logging out…"
        danger
        loading={loggingOut}
        onCancel={() => {
          if (!loggingOut) setConfirmOpen(false)
        }}
        onConfirm={handleConfirmLogout}
      >
        Are you sure you want to log out of your account?
      </ConfirmDialog>
    </>
  )
}
