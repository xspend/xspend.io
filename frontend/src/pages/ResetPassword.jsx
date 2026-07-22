import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import {
  resetPassword,
  getErrorDetail,
  validatePassword,
} from '../lib/auth'
import { showToast } from '../lib/toast'
import { AUTH_COLORS, labelStyle } from '../lib/authStyles'
import {
  AuthPage,
  AuthCard,
  AuthButton,
  ErrorBanner,
  SuccessBanner,
  PasswordInput,
  FieldError,
} from './AuthShell'

const REDIRECT_MS = 2500

function readResetParams(searchParams, search) {
  // Prefer React Router params; fall back to window/location search so query
  // strings are never lost on first paint or after alias redirects.
  const fromWindow = typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search)
    : null
  const fromLocation = search ? new URLSearchParams(search) : null

  const token = (
    searchParams.get('token')
    || fromLocation?.get('token')
    || fromWindow?.get('token')
    || ''
  ).trim()

  const eid = (
    searchParams.get('eid')
    || fromLocation?.get('eid')
    || fromWindow?.get('eid')
    || ''
  ).trim()

  return { token, eid }
}

export default function ResetPassword() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const C = AUTH_COLORS

  // Capture token/eid once from the URL and keep them for the API call.
  const [token, setToken] = useState('')
  const [eid, setEid] = useState('')
  const [paramsReady, setParamsReady] = useState(false)

  const [form, setForm] = useState({ password: '', confirmPassword: '' })
  const [fieldErrors, setFieldErrors] = useState({ password: '', confirmPassword: '' })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const params = readResetParams(searchParams, location.search)
    setToken(params.token)
    setEid(params.eid)
    setParamsReady(true)
    if (!params.token) {
      setError('This reset link is invalid or has expired.')
    }
  }, [searchParams, location.search])

  useEffect(() => {
    if (!success) return undefined
    const timer = setTimeout(() => {
      navigate('/login', { replace: true })
    }, REDIRECT_MS)
    return () => clearTimeout(timer)
  }, [success, navigate])

  const setField = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }))
    if (fieldErrors[key]) setFieldErrors((prev) => ({ ...prev, [key]: '' }))
    if (error) setError('')
  }

  const validate = () => {
    const next = { password: '', confirmPassword: '' }
    next.password = validatePassword(form.password)
    if (!form.confirmPassword) next.confirmPassword = 'Confirm password is required'
    else if (form.confirmPassword !== form.password) {
      next.confirmPassword = 'Passwords must match'
    }
    setFieldErrors(next)
    return !next.password && !next.confirmPassword
  }

  const submit = async () => {
    if (loading) return
    if (!token) {
      const message = 'This reset link is invalid or has expired.'
      setError(message)
      showToast(message, 'error')
      return
    }
    if (!validate()) return
    setLoading(true)
    setError('')
    try {
      const { res, data } = await resetPassword({
        token,
        eid,
        new_password: form.password,
      })
      if (!res.ok) {
        const message = getErrorDetail(
          data,
          'Could not reset password. The link may be invalid or expired.'
        )
        setError(message)
        showToast(message, 'error')
        setLoading(false)
        return
      }
      setSuccess(true)
      showToast('Password has been reset successfully.')
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
    <AuthPage showHomeLink={false}>
      <AuthCard
        title={success ? 'Password reset' : 'Reset password'}
        subtitle={
          success
            ? undefined
            : 'Choose a new password for your account.'
        }
      >
        <ErrorBanner message={!success ? error : ''} />
        <SuccessBanner
          message={
            success
              ? 'Password has been reset successfully. Redirecting to Login…'
              : ''
          }
        />

        {!success && paramsReady && (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={labelStyle}>New password</label>
                <PasswordInput
                  value={form.password}
                  onChange={setField('password')}
                  onKeyDown={handleKeyDown}
                  placeholder="At least 8 characters"
                  autoComplete="new-password"
                  autoFocus={Boolean(token)}
                />
                <FieldError message={fieldErrors.password} />
              </div>
              <div>
                <label style={labelStyle}>Confirm password</label>
                <PasswordInput
                  value={form.confirmPassword}
                  onChange={setField('confirmPassword')}
                  onKeyDown={handleKeyDown}
                  placeholder="Re-enter password"
                  autoComplete="new-password"
                />
                <FieldError message={fieldErrors.confirmPassword} />
              </div>
            </div>

            <AuthButton onClick={submit} loading={loading} disabled={!token}>
              {loading ? 'Saving…' : 'Reset password'}
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

        {success && (
          <AuthButton onClick={() => navigate('/login', { replace: true })}>
            Go to Login
          </AuthButton>
        )}
      </AuthCard>
    </AuthPage>
  )
}
