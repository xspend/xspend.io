import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  verifyOtp,
  resendOtp,
  getPending2FA,
  clearPending2FA,
  saveSession,
  getErrorDetail,
} from '../lib/auth'
import { showToast } from '../lib/toast'
import { AUTH_COLORS } from '../lib/authStyles'
import {
  AuthPage,
  AuthCard,
  AuthButton,
  ErrorBanner,
  FieldError,
} from './AuthShell'

const OTP_LENGTH = 6
const RESEND_COOLDOWN_SEC = 120

function formatCountdown(totalSec) {
  const safe = Math.max(0, totalSec)
  const minutes = Math.floor(safe / 60)
  const seconds = safe % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

export default function TwoFactor() {
  const navigate = useNavigate()
  const C = AUTH_COLORS
  const inputsRef = useRef([])
  const timerRef = useRef(null)
  const [pending] = useState(() => getPending2FA())
  const [digits, setDigits] = useState(Array(OTP_LENGTH).fill(''))
  const [error, setError] = useState('')
  const [fieldError, setFieldError] = useState('')
  const [loading, setLoading] = useState(false)
  const [resending, setResending] = useState(false)
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_SEC)

  const clearTimer = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  const startTimer = (seconds = RESEND_COOLDOWN_SEC) => {
    clearTimer()
    setCooldown(seconds)
    timerRef.current = setInterval(() => {
      setCooldown((prev) => {
        if (prev <= 1) {
          clearTimer()
          return 0
        }
        return prev - 1
      })
    }, 1000)
  }

  useEffect(() => {
    if (!pending.login_token) {
      navigate('/login', { replace: true })
      return undefined
    }
    startTimer(RESEND_COOLDOWN_SEC)
    const focusId = window.setTimeout(() => inputsRef.current[0]?.focus(), 0)
    return () => {
      clearTimer()
      window.clearTimeout(focusId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate, pending.login_token])

  const code = digits.join('')

  const updateDigit = (index, value) => {
    const cleaned = value.replace(/\D/g, '')
    if (!cleaned) {
      setDigits((prev) => {
        const next = [...prev]
        next[index] = ''
        return next
      })
      return
    }

    const chars = cleaned.slice(0, OTP_LENGTH - index).split('')
    setDigits((prev) => {
      const next = [...prev]
      chars.forEach((ch, i) => {
        next[index + i] = ch
      })
      return next
    })
    const focusIndex = Math.min(index + chars.length, OTP_LENGTH - 1)
    inputsRef.current[focusIndex]?.focus()
    if (fieldError) setFieldError('')
    if (error) setError('')
  }

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace') {
      if (digits[index]) {
        setDigits((prev) => {
          const next = [...prev]
          next[index] = ''
          return next
        })
        return
      }
      if (index > 0) {
        inputsRef.current[index - 1]?.focus()
        setDigits((prev) => {
          const next = [...prev]
          next[index - 1] = ''
          return next
        })
      }
    }
    if (e.key === 'ArrowLeft' && index > 0) {
      inputsRef.current[index - 1]?.focus()
    }
    if (e.key === 'ArrowRight' && index < OTP_LENGTH - 1) {
      inputsRef.current[index + 1]?.focus()
    }
    if (e.key === 'Enter') submit()
  }

  const handlePaste = (e) => {
    e.preventDefault()
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, OTP_LENGTH)
    if (!pasted) return
    const next = Array(OTP_LENGTH).fill('')
    pasted.split('').forEach((ch, i) => { next[i] = ch })
    setDigits(next)
    inputsRef.current[Math.min(pasted.length, OTP_LENGTH) - 1]?.focus()
    if (fieldError) setFieldError('')
    if (error) setError('')
  }

  const completeAuthenticatedSession = (data) => {
    saveSession({
      access_token: data.access_token || data.token || pending.access_token,
      refresh_token: data.refresh_token || pending.refresh_token,
      user: data.user || pending.user,
    })
    clearPending2FA()
    showToast('Login successful. Two-Factor Authentication verified.')
    navigate('/app/dashboard', { replace: true })
  }

  const submit = async () => {
    if (loading) return
    if (code.length !== OTP_LENGTH || !/^\d{6}$/.test(code)) {
      setFieldError('Enter the 6-digit code')
      return
    }
    if (!pending.login_token) {
      setError('Missing login session. Please sign in again.')
      showToast('Missing login session. Please sign in again.', 'error')
      return
    }
    setLoading(true)
    setError('')
    setFieldError('')
    try {
      const { res, data } = await verifyOtp({
        login_token: pending.login_token,
        otp: code,
      })
      if (!res.ok) {
        const message = getErrorDetail(data, 'Invalid or expired verification code')
        setError(message)
        showToast(message, 'error')
        setLoading(false)
        return
      }
      completeAuthenticatedSession(data || {})
    } catch {
      const message = 'Could not connect. Make sure the app is running.'
      setError(message)
      showToast(message, 'error')
    }
    setLoading(false)
  }

  const handleResend = async () => {
    if (resending || cooldown > 0 || loading) return
    if (!pending.login_token) {
      const message = 'Missing login session. Please sign in again.'
      setError(message)
      showToast(message, 'error')
      return
    }
    setResending(true)
    setError('')
    try {
      const { res, data } = await resendOtp({
        login_token: pending.login_token,
      })
      if (!res.ok) {
        const message = getErrorDetail(data, 'Could not resend code')
        setError(message)
        showToast(message, 'error')
        // Do not restart timer on failure.
      } else {
        setDigits(Array(OTP_LENGTH).fill(''))
        inputsRef.current[0]?.focus()
        startTimer(RESEND_COOLDOWN_SEC)
        showToast('A new verification code has been sent to your registered email.')
      }
    } catch {
      const message = 'Could not connect. Make sure the app is running.'
      setError(message)
      showToast(message, 'error')
    }
    setResending(false)
  }

  const resendDisabled = resending || cooldown > 0 || loading

  return (
    <AuthPage showHomeLink={false}>
      <AuthCard
        title="Two-Factor Authentication"
        subtitle="Enter the 6-digit verification code sent to your registered email."
      >
        <ErrorBanner message={error} />

        <div
          style={{ display: 'flex', gap: 10, justifyContent: 'center' }}
          onPaste={handlePaste}
        >
          {digits.map((digit, index) => (
            <input
              key={index}
              ref={(el) => { inputsRef.current[index] = el }}
              type="text"
              inputMode="numeric"
              autoComplete={index === 0 ? 'one-time-code' : 'off'}
              maxLength={1}
              value={digit}
              onChange={(e) => updateDigit(index, e.target.value)}
              onKeyDown={(e) => handleKeyDown(index, e)}
              aria-label={`Digit ${index + 1}`}
              disabled={loading}
              style={{
                width: 48,
                height: 52,
                textAlign: 'center',
                fontSize: 20,
                fontWeight: 500,
                borderRadius: 10,
                border: `0.5px solid ${C.border}`,
                background: '#fff',
                color: C.text,
                outline: 'none',
                fontFamily: 'inherit',
                opacity: loading ? 0.7 : 1,
              }}
            />
          ))}
        </div>
        <div style={{ textAlign: 'center' }}>
          <FieldError message={fieldError} />
        </div>

        <AuthButton onClick={submit} loading={loading}>
          {loading ? 'Verifying…' : 'Verify'}
        </AuthButton>

        <button
          type="button"
          onClick={handleResend}
          disabled={resendDisabled}
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
            cursor: resendDisabled ? 'default' : 'pointer',
            opacity: resendDisabled ? 0.6 : 1,
            fontFamily: 'inherit',
          }}
        >
          {resending
            ? 'Sending…'
            : cooldown > 0
              ? `Resend Code in ${formatCountdown(cooldown)}`
              : 'Resend Code'}
        </button>

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
      </AuthCard>
    </AuthPage>
  )
}
