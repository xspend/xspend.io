import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Eye, EyeOff } from 'lucide-react'
import { API_URL } from '../lib/config'
import {
  changePassword,
  getErrorDetail,
  validateStrongPassword,
} from '../lib/auth'
import { showToast } from '../lib/toast'

const COLORS = {
  bg: '#fafaf5',
  card: '#ffffff',
  border: 'rgba(0,0,0,0.08)',
  textPrimary: '#1a1a1a',
  textSecondary: '#5a5a5a',
  textMuted: '#8a8a85',
  accent: '#e85d3c',
  danger: '#d85a30',
  errorText: '#b1372a',
}

const emptyPwErrors = {
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
}

function PasswordField({
  id,
  label,
  value,
  onChange,
  onKeyDown,
  placeholder,
  autoComplete,
  error,
}) {
  const [show, setShow] = useState(false)
  return (
    <div style={{ marginBottom: 18 }}>
      <label htmlFor={id} className="settings-label">
        {label}
      </label>
      <div style={{ position: 'relative' }}>
        <input
          id={id}
          className="settings-input"
          type={show ? 'text' : 'password'}
          value={value}
          onChange={onChange}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          autoComplete={autoComplete}
          style={{ paddingRight: 44 }}
        />
        <button
          type="button"
          className="settings-eye"
          onClick={() => setShow((s) => !s)}
          aria-label={show ? 'Hide password' : 'Show password'}
        >
          {show ? <EyeOff size={18} /> : <Eye size={18} />}
        </button>
      </div>
      {error ? (
        <p style={{ color: COLORS.errorText, fontSize: 13, margin: '7px 0 0', lineHeight: 1.4 }}>
          {error}
        </p>
      ) : null}
    </div>
  )
}

export default function Settings() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const [pwForm, setPwForm] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  })
  const [pwErrors, setPwErrors] = useState(emptyPwErrors)
  const [updatingPw, setUpdatingPw] = useState(false)

  useEffect(() => {
    fetch(`${API_URL}/profile`)
      .then(r => r.json())
      .then(p => {
        setName(p?.full_name || '')
        setEmail(p?.email || localStorage.getItem('user_email') || '')
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      await fetch(`${API_URL}/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: name }),
      })
      if (name) localStorage.setItem('user_name', name.split(' ')[0])
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      // no-op
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    const ok = window.confirm(
      'Delete your account? You will be logged out and your email address will be freed up. This cannot be undone.'
    )
    if (!ok) return
    setDeleting(true)
    try {
      const res = await fetch(`${API_URL}/auth/user`, { method: 'DELETE' })
      if (!res.ok) {
        throw new Error(`Delete failed with status ${res.status}`)
      }
      localStorage.clear()
      navigate('/')
    } catch (e) {
      setDeleting(false)
      window.alert('Something went wrong deleting your account. Please try again.')
    }
  }

  const setPwField = (key) => (e) => {
    setPwForm((f) => ({ ...f, [key]: e.target.value }))
    if (pwErrors[key]) setPwErrors((prev) => ({ ...prev, [key]: '' }))
  }

  const validatePw = () => {
    const next = { ...emptyPwErrors }
    if (!pwForm.currentPassword) {
      next.currentPassword = 'Current password is required'
    }
    next.newPassword = validateStrongPassword(pwForm.newPassword)
    if (!pwForm.confirmPassword) {
      next.confirmPassword = 'Confirm password is required'
    } else if (pwForm.confirmPassword !== pwForm.newPassword) {
      next.confirmPassword = 'Passwords must match'
    }
    setPwErrors(next)
    return !Object.values(next).some(Boolean)
  }

  const handleChangePassword = async () => {
    if (updatingPw) return
    if (!validatePw()) return
    setUpdatingPw(true)
    try {
      const { res, data } = await changePassword({
        current_password: pwForm.currentPassword,
        new_password: pwForm.newPassword,
      })
      if (!res.ok) {
        showToast(getErrorDetail(data, 'Could not update password.'), 'error')
        return
      }
      showToast(data?.message || 'Password updated.')
      setPwForm({
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',
      })
      setPwErrors(emptyPwErrors)
    } catch {
      showToast('Could not update password. Please try again.', 'error')
    } finally {
      setUpdatingPw(false)
    }
  }

  if (loading) {
    return <div style={{ padding: 40, color: COLORS.textMuted, fontSize: 15 }}>Loading…</div>
  }

  return (
    <div className="settings-page">
      <style>{`
        .settings-page {
          max-width: 48rem;
          margin: 0 auto;
          padding: 8px 8px 48px;
          width: 100%;
          box-sizing: border-box;
        }
        .settings-header { margin-bottom: 28px; }
        .settings-header h1 {
          font-size: 1.5rem;
          font-weight: 600;
          color: #1a1a1a;
          margin: 0 0 4px;
          letter-spacing: -0.02em;
        }
        .settings-header p {
          font-size: 0.875rem;
          color: #5a5a5a;
          margin: 0;
          line-height: 1.5;
        }
        .settings-stack {
          display: flex;
          flex-direction: column;
          gap: 20px;
        }
        .settings-card {
          background: #fff;
          border: 1px solid rgba(0,0,0,0.08);
          border-radius: 16px;
          padding: 28px 26px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.04);
          transition: box-shadow 0.2s ease;
        }
        .settings-card:hover {
          box-shadow: 0 6px 20px rgba(0,0,0,0.06);
        }
        .settings-card-danger {
          background: #fef8f6;
          border-color: rgba(216,90,48,0.28);
        }
        .settings-card h2 {
          font-size: 17px;
          font-weight: 600;
          color: #1a1a1a;
          margin: 0 0 4px;
          letter-spacing: -0.01em;
        }
        .settings-card-danger h2 { color: #d85a30; }
        .settings-card .settings-desc {
          font-size: 14px;
          color: #8a8a85;
          margin: 0 0 22px;
          line-height: 1.5;
        }
        .settings-label {
          display: block;
          font-size: 13px;
          font-weight: 600;
          color: #5a5a5a;
          margin-bottom: 8px;
          letter-spacing: 0.01em;
        }
        .settings-input {
          width: 100%;
          padding: 12px 14px;
          font-size: 15px;
          line-height: 1.4;
          color: #1a1a1a;
          background: #fff;
          border: 1px solid rgba(0,0,0,0.12);
          border-radius: 12px;
          font-family: inherit;
          box-sizing: border-box;
          outline: none;
          transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }
        .settings-input:hover { border-color: rgba(0,0,0,0.18); }
        .settings-input:focus {
          border-color: rgba(232,93,60,0.5);
          box-shadow: 0 0 0 3px rgba(232,93,60,0.12);
        }
        .settings-input-readonly {
          color: #8a8a85;
          background: #faf9f5;
          border: 1px solid rgba(0,0,0,0.08);
          cursor: default;
        }
        .settings-field { margin-bottom: 18px; }
        .settings-actions {
          margin-top: 8px;
          display: flex;
          align-items: center;
          gap: 14px;
          flex-wrap: wrap;
        }
        .settings-btn {
          padding: 11px 20px;
          font-size: 15px;
          font-weight: 600;
          color: #fff;
          background: #e85d3c;
          border: none;
          border-radius: 12px;
          font-family: inherit;
          cursor: pointer;
          transition: filter 0.15s ease, box-shadow 0.15s ease, transform 0.1s ease, opacity 0.15s ease;
          box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        }
        .settings-btn:hover:not(:disabled) {
          filter: brightness(1.04);
          box-shadow: 0 4px 14px rgba(232,93,60,0.28);
        }
        .settings-btn:active:not(:disabled) { transform: scale(0.98); }
        .settings-btn:disabled { opacity: 0.65; cursor: default; }
        .settings-btn-danger {
          color: #d85a30;
          background: transparent;
          border: 1px solid #d85a30;
          box-shadow: none;
        }
        .settings-btn-danger:hover:not(:disabled) {
          filter: none;
          background: rgba(216,90,48,0.06);
          box-shadow: none;
        }
        .settings-eye {
          position: absolute;
          right: 10px;
          top: 50%;
          transform: translateY(-50%);
          background: none;
          border: none;
          padding: 6px;
          cursor: pointer;
          color: #8a8a85;
          display: inline-flex;
          align-items: center;
          border-radius: 8px;
          transition: color 0.15s ease, background 0.15s ease;
        }
        .settings-eye:hover {
          color: #1a1a1a;
          background: rgba(0,0,0,0.04);
        }
        .settings-hint {
          font-size: 12px;
          color: #8a8a85;
          margin: -6px 0 16px;
          line-height: 1.5;
        }
        .settings-saved {
          font-size: 14px;
          color: #1d9e75;
          font-weight: 600;
        }
        @media (max-width: 640px) {
          .settings-page { padding: 4px 4px 40px; }
          .settings-card { padding: 22px 18px; }
          .settings-btn { width: 100%; }
          .settings-actions { width: 100%; }
        }
      `}</style>

      <header className="settings-header">
        <h1>Settings</h1>
        <p>Manage your profile and account settings.</p>
      </header>

      <div className="settings-stack">
        {/* Profile */}
        <section className="settings-card">
          <h2>Profile</h2>
          <p className="settings-desc">Update your personal information.</p>

          <div className="settings-field">
            <label className="settings-label" htmlFor="settings-name">Name</label>
            <input
              id="settings-name"
              className="settings-input"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Your name"
              autoComplete="name"
            />
          </div>

          {email && (
            <div className="settings-field">
              <label className="settings-label" htmlFor="settings-email">Email</label>
              <div id="settings-email" className="settings-input settings-input-readonly">
                {email}
              </div>
            </div>
          )}

          <div className="settings-actions">
            <button
              type="button"
              className="settings-btn"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Saving…' : 'Save changes'}
            </button>
            {saved && <span className="settings-saved">Saved ✓</span>}
          </div>
        </section>

        {/* Change Password */}
        <section className="settings-card">
          <h2>Change Password</h2>
          <p className="settings-desc">Change your account password.</p>

          <PasswordField
            id="settings-current-password"
            label="Current Password"
            value={pwForm.currentPassword}
            onChange={setPwField('currentPassword')}
            onKeyDown={(e) => e.key === 'Enter' && handleChangePassword()}
            placeholder="Enter current password"
            autoComplete="current-password"
            error={pwErrors.currentPassword}
          />
          <PasswordField
            id="settings-new-password"
            label="New Password"
            value={pwForm.newPassword}
            onChange={setPwField('newPassword')}
            onKeyDown={(e) => e.key === 'Enter' && handleChangePassword()}
            placeholder="At least 8 characters"
            autoComplete="new-password"
            error={pwErrors.newPassword}
          />
          <p className="settings-hint">
            Use 8+ characters with uppercase, lowercase, a number, and a special character.
          </p>
          <PasswordField
            id="settings-confirm-password"
            label="Confirm New Password"
            value={pwForm.confirmPassword}
            onChange={setPwField('confirmPassword')}
            onKeyDown={(e) => e.key === 'Enter' && handleChangePassword()}
            placeholder="Re-enter new password"
            autoComplete="new-password"
            error={pwErrors.confirmPassword}
          />

          <div className="settings-actions">
            <button
              type="button"
              className="settings-btn"
              onClick={handleChangePassword}
              disabled={updatingPw}
            >
              {updatingPw ? 'Updating…' : 'Update Password'}
            </button>
          </div>
        </section>

        {/* Danger zone */}
        <section className="settings-card settings-card-danger">
          <h2>Delete account</h2>
          <p className="settings-desc" style={{ color: COLORS.textSecondary }}>
            Permanently delete your account and all your data — transactions, uploads, and goals.
            This cannot be undone.
          </p>
          <button
            type="button"
            className="settings-btn settings-btn-danger"
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting ? 'Deleting…' : 'Delete my account'}
          </button>
        </section>
      </div>
    </div>
  )
}
