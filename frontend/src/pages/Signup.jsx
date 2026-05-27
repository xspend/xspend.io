import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { API_URL } from '../lib/config'

const F = "'DM Sans', Inter, -apple-system, BlinkMacSystemFont, system-ui, sans-serif"

const C = {
  bg:         '#fafaf5',
  cardBg:     'rgba(255,255,255,0.65)',
  text:       '#1a1a1a',
  textMuted:  '#5a5a5a',
  textHint:   '#8a8a85',
  border:     'rgba(0,0,0,0.12)',
  borderSoft: 'rgba(0,0,0,0.04)',
  inputBg:    '#ffffff',
  inputBorder:'rgba(0,0,0,0.12)',
  accent:     '#e85d3c',
  errorBg:    '#fdecea',
  errorBorder:'rgba(220,38,38,0.2)',
  errorText:  '#b1372a',
  ctaBg:      '#1a1a1a',
  ctaText:    '#fafaf5',
}

export default function Signup() {
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const submit = async () => {
    if (!form.email || !form.password) {
      setError('Please enter your email and password')
      return
    }
    if (form.password.length < 6) {
      setError('Password must be at least 6 characters')
      return
    }
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${API_URL}/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: form.email,
          password: form.password,
        })
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Signup failed')
        setLoading(false)
        return
      }
      localStorage.setItem('auth_token', data.token)
      localStorage.setItem('user_email', data.user.email)
      if (data.user.name) localStorage.setItem('user_name', data.user.name.split(' ')[0])
      localStorage.setItem('just_signed_up', 'true')
      navigate('/app/upload')
    } catch {
      setError('Could not connect. Make sure the app is running.')
    }
    setLoading(false)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') submit()
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: C.bg,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: F,
      padding: 20,
    }}>
      <div style={{ width: '100%', maxWidth: 420 }}>

        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 36 }}>
          <Link to="/" style={{
            textDecoration: 'none',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 10,
          }}>
            <span style={{
              width: 28,
              height: 28,
              borderRadius: '50%',
              background: C.text,
              display: 'inline-flex',
              position: 'relative',
            }}>
              <span style={{
                position: 'absolute',
                top: 4,
                right: 4,
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: C.accent,
              }}/>
            </span>
            <span style={{
              fontWeight: 500,
              fontSize: 18,
              color: C.text,
              letterSpacing: 1.8,
            }}>XSPEND</span>
          </Link>
        </div>

        {/* Card */}
        <div style={{
          background: C.cardBg,
          border: `0.5px solid ${C.border}`,
          borderRadius: 16,
          padding: '36px 32px',
        }}>
          <h1 style={{
            fontSize: 24,
            fontWeight: 500,
            color: C.text,
            margin: '0 0 6px',
            textAlign: 'center',
            letterSpacing: '-0.01em',
          }}>
            Create your account
          </h1>
          <p style={{
            fontSize: 14,
            color: C.textMuted,
            textAlign: 'center',
            margin: '0 0 28px',
          }}>
            Email and password. No credit card needed.
          </p>

          {error && (
            <div style={{
              background: C.errorBg,
              border: `0.5px solid ${C.errorBorder}`,
              borderRadius: 10,
              padding: '10px 14px',
              marginBottom: 18,
            }}>
              <p style={{ color: C.errorText, fontSize: 13, margin: 0 }}>{error}</p>
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={labelStyle}>Email</label>
              <input
                type="email"
                value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                onKeyDown={handleKeyDown}
                placeholder="you@example.com"
                style={inputStyle}
                autoFocus
              />
            </div>
            <div>
              <label style={labelStyle}>Password</label>
              <input
                type="password"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                onKeyDown={handleKeyDown}
                placeholder="At least 6 characters"
                style={inputStyle}
              />
            </div>
          </div>

          <button
            onClick={submit}
            disabled={loading}
            style={{
              width: '100%',
              background: C.ctaBg,
              color: C.ctaText,
              border: 'none',
              borderRadius: 10,
              padding: '13px 20px',
              fontSize: 15,
              fontWeight: 500,
              cursor: loading ? 'default' : 'pointer',
              opacity: loading ? 0.6 : 1,
              marginTop: 22,
              fontFamily: 'inherit',
              transition: 'opacity 0.15s',
            }}
          >
            {loading ? 'Creating account…' : 'Create account'}
          </button>

          <p style={{
            fontSize: 13,
            color: C.textMuted,
            textAlign: 'center',
            margin: '20px 0 0',
          }}>
            Already have an account?{' '}
            <Link to="/login" style={{
              color: C.text,
              textDecoration: 'underline',
              textUnderlineOffset: 3,
              fontWeight: 500,
            }}>
              Sign in
            </Link>
          </p>
        </div>

        {/* Back to landing */}
        <div style={{ textAlign: 'center', marginTop: 24 }}>
          <Link to="/" style={{
            fontSize: 13,
            color: C.textHint,
            textDecoration: 'none',
          }}>
            ← Back
          </Link>
        </div>

      </div>
    </div>
  )
}

const labelStyle = {
  display: 'block',
  fontSize: 12,
  fontWeight: 500,
  color: '#5a5a5a',
  marginBottom: 6,
  letterSpacing: '0.2px',
}

const inputStyle = {
  background: '#ffffff',
  border: '0.5px solid rgba(0,0,0,0.12)',
  borderRadius: 10,
  padding: '12px 14px',
  color: '#1a1a1a',
  fontSize: 15,
  outline: 'none',
  fontFamily: 'inherit',
  width: '100%',
  boxSizing: 'border-box',
}
