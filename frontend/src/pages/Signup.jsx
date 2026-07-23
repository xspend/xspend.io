import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  signup,
  isValidEmail,
  validatePassword,
  getErrorDetail,
} from '../lib/auth'
import { AUTH_COLORS, labelStyle, inputStyle } from '../lib/authStyles'
import {
  AuthPage,
  AuthCard,
  AuthButton,
  ErrorBanner,
  PasswordInput,
  FieldError,
  SuccessDialog,
} from './AuthShell'

const emptyErrors = {
  fullName: '',
  email: '',
  password: '',
  confirmPassword: '',
}

export default function Signup() {
  const navigate = useNavigate()
  const C = AUTH_COLORS
  const [form, setForm] = useState({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
  })
  const [errors, setErrors] = useState(emptyErrors)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showSuccess, setShowSuccess] = useState(false)

  const setField = (key) => (e) => {
    const value = e.target.value
    setForm((f) => ({ ...f, [key]: value }))
    if (errors[key]) setErrors((prev) => ({ ...prev, [key]: '' }))
    if (error) setError('')
  }

  const validate = () => {
    const next = { ...emptyErrors }
    if (!form.fullName.trim()) next.fullName = 'Full Name is required.'
    if (!form.email.trim()) next.email = 'Email is required'
    else if (!isValidEmail(form.email)) next.email = 'Enter a valid email address'
    next.password = validatePassword(form.password)
    if (!form.confirmPassword) next.confirmPassword = 'Confirm password is required'
    else if (form.confirmPassword !== form.password) {
      next.confirmPassword = 'Passwords must match'
    }
    setErrors(next)
    return !Object.values(next).some(Boolean)
  }

  const submit = async () => {
    if (loading) return
    if (!validate()) return
    setLoading(true)
    setError('')
    try {
      // Keep existing API payload key `name` — now holds the full name.
      const { res, data } = await signup({
        name: form.fullName.trim(),
        email: form.email.trim(),
        password: form.password,
      })
      if (!res.ok) {
        setError(getErrorDetail(data, 'Signup failed'))
        setLoading(false)
        return
      }
      setShowSuccess(true)
    } catch {
      setError('Could not connect. Make sure the app is running.')
    }
    setLoading(false)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') submit()
  }

  return (
    <AuthPage>
      <AuthCard
        title="Create your account"
        subtitle="Email and password. No credit card needed."
      >
        <ErrorBanner message={error} />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={labelStyle}>Full Name</label>
            <input
              type="text"
              value={form.fullName}
              onChange={setField('fullName')}
              onKeyDown={handleKeyDown}
              placeholder="Enter your full name"
              style={inputStyle}
              autoFocus
              autoComplete="name"
            />
            <FieldError message={errors.fullName} />
          </div>

          <div>
            <label style={labelStyle}>Email</label>
            <input
              type="email"
              value={form.email}
              onChange={setField('email')}
              onKeyDown={handleKeyDown}
              placeholder="you@example.com"
              style={inputStyle}
              autoComplete="email"
            />
            <FieldError message={errors.email} />
          </div>

          <div>
            <label style={labelStyle}>Password</label>
            <PasswordInput
              value={form.password}
              onChange={setField('password')}
              onKeyDown={handleKeyDown}
              placeholder="At least 8 characters"
              autoComplete="new-password"
            />
            <FieldError message={errors.password} />
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
            <FieldError message={errors.confirmPassword} />
          </div>
        </div>

        <AuthButton onClick={submit} loading={loading}>
          {loading ? 'Creating account…' : 'Create account'}
        </AuthButton>

        <p style={{
          fontSize: 15,
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
      </AuthCard>

      <SuccessDialog
        open={showSuccess}
        title="Registration Successful!"
        primaryLabel="Back to Login"
        onPrimary={() => navigate('/login')}
      >
        <p style={{ margin: '0 0 10px' }}>
          Your account has been created successfully.
        </p>
        <p style={{ margin: '0 0 10px' }}>
          Please verify your email before logging in.
        </p>
        <p style={{ margin: 0 }}>
          We&apos;ve sent a verification link to your registered email address.
        </p>
      </SuccessDialog>
    </AuthPage>
  )
}
