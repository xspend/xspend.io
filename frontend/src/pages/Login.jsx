import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  login,
  resendVerification,
  savePending2FA,
  getErrorDetail,
  isValidEmail,
  isEmailNotVerifiedError,
} from '../lib/auth'
import { consumeSessionToast } from '../lib/apiClient'
import { AUTH_COLORS, labelStyle, inputStyle } from '../lib/authStyles'
import {
  AuthPage,
  AuthCard,
  AuthButton,
  ErrorBanner,
  SuccessBanner,
  PasswordInput,
  FieldError,
} from './AuthShell'

export default function Login() {
  const navigate = useNavigate()
  const C = AUTH_COLORS
  const [form, setForm] = useState({ email: '', password: '' })
  const [fieldErrors, setFieldErrors] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [resending, setResending] = useState(false)
  const [showResend, setShowResend] = useState(false)
  const [resendMessage, setResendMessage] = useState('')

  useEffect(() => {
    consumeSessionToast()
  }, [])

  const setField = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }))
    if (fieldErrors[key]) setFieldErrors((prev) => ({ ...prev, [key]: '' }))
    if (error) setError('')
    if (resendMessage) setResendMessage('')
  }

  const validate = () => {
    const next = { email: '', password: '' }
    if (!form.email.trim()) next.email = 'Email is required'
    else if (!isValidEmail(form.email)) next.email = 'Enter a valid email address'
    if (!form.password) next.password = 'Password is required'
    setFieldErrors(next)
    return !next.email && !next.password
  }

  const submit = async () => {
    if (loading) return
    if (!validate()) return
    setLoading(true)
    setError('')
    setShowResend(false)
    setResendMessage('')
    try {
      const email = form.email.trim()
      const { res, data } = await login({
        email,
        password: form.password,
      })

      if (!res.ok) {
        const message = getErrorDetail(data, 'Login failed')
        setError(message)
        if (isEmailNotVerifiedError(message) || res.status === 403) {
          setShowResend(true)
        }
        setLoading(false)
        return
      }

      // Login succeeded — do NOT open the dashboard yet.
      // Hold login_token and send the user through 2FA first.
      const loginToken = data.login_token || ''
      if (!loginToken) {
        setError('Login succeeded but no login_token was returned. Cannot continue 2FA.')
        setLoading(false)
        return
      }
      savePending2FA({
        login_token: loginToken,
        email: data.user?.email || email,
        access_token: data.access_token || data.token || '',
        refresh_token: data.refresh_token || '',
        user: data.user || null,
      })
      navigate('/auth/two-factor', { replace: true })
    } catch {
      setError('Could not connect. Make sure the app is running.')
    }
    setLoading(false)
  }

  const handleResend = async () => {
    if (resending || !form.email.trim()) return
    setResending(true)
    setResendMessage('')
    try {
      const { res, data } = await resendVerification({ email: form.email.trim() })
      if (!res.ok) {
        setError(getErrorDetail(data, 'Could not resend verification email'))
      } else {
        setResendMessage(data?.message || 'Verification email sent.')
        setError('')
      }
    } catch {
      setError('Could not connect. Make sure the app is running.')
    }
    setResending(false)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') submit()
  }

  return (
    <AuthPage>
      <AuthCard title="Welcome back" subtitle="Sign in to continue">
        <ErrorBanner message={error} />
        <SuccessBanner message={resendMessage} />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={labelStyle}>Email</label>
            <input
              type="email"
              value={form.email}
              onChange={setField('email')}
              onKeyDown={handleKeyDown}
              placeholder="you@example.com"
              style={inputStyle}
              autoFocus
              autoComplete="email"
            />
            <FieldError message={fieldErrors.email} />
          </div>
          <div>
            <label style={labelStyle}>Password</label>
            <PasswordInput
              value={form.password}
              onChange={setField('password')}
              onKeyDown={handleKeyDown}
              placeholder="Your password"
              autoComplete="current-password"
            />
            <FieldError message={fieldErrors.password} />
            <div style={{ textAlign: 'right', marginTop: 8 }}>
              <Link to="/auth/forgot-password" style={{
                fontSize: 14,
                color: C.textHint,
                textDecoration: 'none',
              }}>
                Forgot password?
              </Link>
            </div>
          </div>
        </div>

        <AuthButton onClick={submit} loading={loading}>
          {loading ? 'Signing in…' : 'Sign in'}
        </AuthButton>

        {showResend && (
          <button
            type="button"
            onClick={handleResend}
            disabled={resending}
            style={{
              width: '100%',
              marginTop: 12,
              background: 'transparent',
              border: `0.5px solid ${C.border}`,
              borderRadius: 10,
              padding: '11px 20px',
              fontSize: 15,
              fontWeight: 500,
              color: C.text,
              cursor: resending ? 'default' : 'pointer',
              opacity: resending ? 0.6 : 1,
              fontFamily: 'inherit',
            }}
          >
            {resending ? 'Sending…' : 'Resend Verification Email'}
          </button>
        )}

        <p style={{
          fontSize: 15,
          color: C.textMuted,
          textAlign: 'center',
          margin: '20px 0 0',
        }}>
          Don&apos;t have an account?{' '}
          <Link to="/signup" style={{
            color: C.text,
            textDecoration: 'underline',
            textUnderlineOffset: 3,
            fontWeight: 500,
          }}>
            Get started
          </Link>
        </p>
      </AuthCard>
    </AuthPage>
  )
}
