import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { API_URL } from '../lib/config'

const COLORS = {
  bg: '#fafaf5',
  card: '#ffffff',
  border: 'rgba(0,0,0,0.08)',
  textPrimary: '#1a1a1a',
  textSecondary: '#5a5a5a',
  textMuted: '#8a8a85',
  accent: '#e85d3c',
  danger: '#d85a30',
}

export default function Settings() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [deleting, setDeleting] = useState(false)

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
      'Delete your account? This permanently removes your account and all your data. This cannot be undone.'
    )
    if (!ok) return
    setDeleting(true)
    try {
      await fetch(`${API_URL}/auth/account`, { method: 'DELETE' })
      localStorage.clear()
      navigate('/')
    } catch (e) {
      setDeleting(false)
      window.alert('Something went wrong deleting your account. Please try again.')
    }
  }

  const label = { fontSize: 16, fontWeight: 600, color: COLORS.textSecondary, marginBottom: 8, display: 'block' }
  const input = {
    width: '100%', padding: '12px 14px', fontSize: 18, color: COLORS.textPrimary,
    background: '#fff', border: `1px solid ${COLORS.border}`, borderRadius: 10,
    fontFamily: 'inherit', boxSizing: 'border-box',
  }
  const card = {
    background: COLORS.card, border: `1px solid ${COLORS.border}`,
    borderRadius: 16, padding: 28, marginBottom: 20,
  }

  if (loading) {
    return <div style={{ padding: 40, color: COLORS.textMuted, fontSize: 18 }}>Loading…</div>
  }

  return (
    <div style={{ maxWidth: 560, margin: '0 auto', padding: '32px 24px' }}>
      <h1 style={{ fontSize: 30, fontWeight: 800, color: COLORS.textPrimary, marginBottom: 4 }}>
        Settings
      </h1>
      <p style={{ fontSize: 17, color: COLORS.textMuted, marginBottom: 28 }}>
        Manage your profile and account.
      </p>

      {/* Profile */}
      <div style={card}>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: COLORS.textPrimary, marginBottom: 20 }}>
          Profile
        </h2>

        <label style={label}>Name</label>
        <input
          style={input}
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="Your name"
        />

        {email && (
          <div style={{ marginTop: 18 }}>
            <label style={label}>Email</label>
            <div style={{ ...input, color: COLORS.textMuted, background: '#faf9f5' }}>
              {email}
            </div>
          </div>
        )}

        <div style={{ marginTop: 22, display: 'flex', alignItems: 'center', gap: 14 }}>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              padding: '11px 22px', fontSize: 17, fontWeight: 600,
              color: '#fff', background: COLORS.accent, border: 'none',
              borderRadius: 10, cursor: saving ? 'default' : 'pointer',
              opacity: saving ? 0.7 : 1, fontFamily: 'inherit',
            }}
          >
            {saving ? 'Saving…' : 'Save changes'}
          </button>
          {saved && <span style={{ fontSize: 16, color: '#1d9e75', fontWeight: 600 }}>Saved ✓</span>}
        </div>
      </div>

      {/* Danger zone */}
      <div style={{ ...card, borderColor: 'rgba(216,90,48,0.3)' }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: COLORS.danger, marginBottom: 8 }}>
          Delete account
        </h2>
        <p style={{ fontSize: 16, color: COLORS.textSecondary, marginBottom: 20, lineHeight: 1.5 }}>
          Permanently delete your account and all your data — transactions, uploads, and goals.
          This cannot be undone.
        </p>
        <button
          onClick={handleDelete}
          disabled={deleting}
          style={{
            padding: '11px 22px', fontSize: 17, fontWeight: 600,
            color: COLORS.danger, background: 'transparent',
            border: `1px solid ${COLORS.danger}`, borderRadius: 10,
            cursor: deleting ? 'default' : 'pointer', opacity: deleting ? 0.7 : 1,
            fontFamily: 'inherit',
          }}
        >
          {deleting ? 'Deleting…' : 'Delete my account'}
        </button>
      </div>
    </div>
  )
}
