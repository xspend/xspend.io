import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { forgotPassword, getErrorDetail, isValidEmail } from '../lib/auth'
import { showToast } from '../lib/toast'
import { AUTH_COLORS, labelStyle, inputStyle } from '../lib/authStyles'
import {
  AuthPage,
  AuthCard,
  AuthButton,
  ErrorBanner,
  FieldError,
} from './AuthShell'

export default function ForgotPassword() {
  const navigate = useNavigate()
  const C = AUTH_COLORS
  const [email, setEmail] = useState('')
  const [fieldError, setFieldError] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    if (loading) return
    if (!email.trim()) {
      setFieldError('Email is required')
      return
    }
    if (!isValidEmail(email)) {
      setFieldError('Enter a valid email address')
      return
    }
    setFieldError('')
    setError('')
    setLoading(true)
    try {
      const { res, data } = await forgotPassword({ email: email.trim() })
      if (!res.ok) {
        const message = getErrorDetail(data, 'Could not send reset link')
        setError(message)
        showToast(message, 'error')
        setLoading(false)
        return
      }
      setSuccess(true)
      showToast('Password reset link has been sent to your email.')
    } catch {
      const message = 'Could not connect. Make sure the app is running.'
      setError(message)
      showToast(message, 'error')
    }
    setLoading(false)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') submit()
  }

  return (
    <AuthPage>
      <AuthCard
        title={success ? 'Check your email.' : 'Forgot password'}
        subtitle={
          success
            ? undefined
            : "Enter your email and we'll send a reset link."
        }
      >
        <ErrorBanner message={error} />

        {success ? (
          <>
            <p style={{
              textAlign: 'center',
              color: C.textMuted,
              fontSize: 15,
              margin: '0 0 8px',
              lineHeight: 1.55,
            }}>
              We&apos;ve sent you a password reset link.
            </p>
            <p style={{
              textAlign: 'center',
              color: C.textMuted,
              fontSize: 15,
              margin: '0 0 4px',
              lineHeight: 1.55,
            }}>
              Please follow the instructions in the email to reset your password.
            </p>
            <AuthButton onClick={() => navigate('/login')}>
              Back to Login
            </AuthButton>
          </>
        ) : (
          <>
            <div>
              <label style={labelStyle}>Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                  if (fieldError) setFieldError('')
                  if (error) setError('')
                }}
                onKeyDown={handleKeyDown}
                placeholder="you@example.com"
                style={inputStyle}
                autoFocus
                autoComplete="email"
              />
              <FieldError message={fieldError} />
            </div>

            <AuthButton onClick={submit} loading={loading}>
              {loading ? 'Sending…' : 'Send reset link'}
            </AuthButton>

            <p style={{
              fontSize: 15,
              color: C.textMuted,
              textAlign: 'center',
              margin: '20px 0 0',
            }}>
              <Link to="/login" style={{
                color: C.text,
                textDecoration: 'underline',
                textUnderlineOffset: 3,
                fontWeight: 500,
              }}>
                Back to Login
              </Link>
            </p>
          </>
        )}
      </AuthCard>
    </AuthPage>
  )
}
