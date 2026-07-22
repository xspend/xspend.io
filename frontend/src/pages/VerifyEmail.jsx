import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { verifyEmail, getErrorDetail } from '../lib/auth'
import { AUTH_COLORS, AUTH_FONT } from '../lib/authStyles'
import {
  AuthPage,
  AuthCard,
  AuthButton,
} from './AuthShell'

const REDIRECT_MS = 2500

// Cache in-flight/completed verifies so StrictMode remounts don't re-use a one-time token.
const verifyCache = new Map()

function readQueryParams(searchParams) {
  // Prefer React Router params; fall back to window.location so query strings
  // are never lost if the router search object is empty on first paint.
  const fromWindow = typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search)
    : null

  const token = (searchParams.get('token') || fromWindow?.get('token') || '').trim()
  const eid = (searchParams.get('eid') || fromWindow?.get('eid') || '').trim()
  return { token, eid }
}

function Spinner() {
  const C = AUTH_COLORS
  return (
    <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 18 }}>
      <div
        aria-hidden="true"
        style={{
          width: 36,
          height: 36,
          borderRadius: '50%',
          border: `3px solid ${C.border}`,
          borderTopColor: C.text,
          animation: 'xspend-spin 0.8s linear infinite',
        }}
      />
      <style>{`@keyframes xspend-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

export default function VerifyEmail() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const C = AUTH_COLORS
  const [status, setStatus] = useState('loading') // loading | success | error
  const [message, setMessage] = useState('')
  const startedRef = useRef(false)

  // Kick off verification as soon as the page loads — never navigate away first.
  useEffect(() => {
    let cancelled = false
    const { token, eid } = readQueryParams(searchParams)
    const cacheKey = `${token}|${eid}`

    const apply = (result) => {
      if (cancelled) return
      setStatus(result.status)
      setMessage(result.message)
    }

    const run = async () => {
      if (!token) {
        apply({
          status: 'error',
          message: 'This verification link is invalid or has expired.',
        })
        return
      }

      if (verifyCache.has(cacheKey)) {
        apply(await verifyCache.get(cacheKey))
        return
      }

      // Guard against overlapping starts within the same mount cycle.
      if (startedRef.current && !verifyCache.has(cacheKey)) {
        return
      }
      startedRef.current = true

      const request = (async () => {
        try {
          const body = { token, eid }
          const { res, data } = await verifyEmail(body)
          if (res.ok) {
            return {
              status: 'success',
              message: data?.message || 'Your email has been verified successfully.',
            }
          }
          return {
            status: 'error',
            message: getErrorDetail(
              data,
              'This verification link is invalid or has expired.'
            ),
          }
        } catch {
          return {
            status: 'error',
            message: 'Could not connect. Make sure the app is running.',
          }
        }
      })()

      verifyCache.set(cacheKey, request)
      const result = await request
      verifyCache.set(cacheKey, Promise.resolve(result))
      apply(result)
    }

    run()
    return () => { cancelled = true }
  }, [searchParams])

  // Success → Login after a short delay. Failure never auto-redirects.
  useEffect(() => {
    if (status !== 'success') return undefined
    const timer = setTimeout(() => {
      navigate('/login', { replace: true })
    }, REDIRECT_MS)
    return () => clearTimeout(timer)
  }, [status, navigate])

  return (
    <AuthPage showHomeLink={false}>
      <AuthCard
        title={
          status === 'loading'
            ? undefined
            : status === 'success'
              ? '✅ Email Verified Successfully'
              : 'Verification Failed'
        }
      >
        {status === 'loading' && (
          <div style={{ textAlign: 'center', padding: '8px 0 4px' }}>
            <Spinner />
            <p style={{
              margin: 0,
              fontSize: 17,
              fontWeight: 500,
              color: C.text,
              fontFamily: AUTH_FONT,
            }}>
              Verifying your email...
            </p>
          </div>
        )}

        {status === 'success' && (
          <>
            <p style={{
              textAlign: 'center',
              color: C.textMuted,
              fontSize: 15,
              margin: '0 0 8px',
              lineHeight: 1.55,
            }}>
              Your email has been verified successfully.
            </p>
            <p style={{
              textAlign: 'center',
              color: C.textMuted,
              fontSize: 15,
              margin: '0 0 4px',
              lineHeight: 1.55,
            }}>
              You can now log in to your account.
            </p>
            <p style={{
              textAlign: 'center',
              color: C.textHint,
              fontSize: 13,
              margin: '16px 0 0',
            }}>
              Redirecting to Login…
            </p>
            <AuthButton onClick={() => navigate('/login', { replace: true })}>
              Go to Login
            </AuthButton>
          </>
        )}

        {status === 'error' && (
          <>
            <p style={{
              textAlign: 'center',
              color: C.textMuted,
              fontSize: 15,
              margin: '0 0 4px',
              lineHeight: 1.55,
            }}>
              {message || 'This verification link is invalid or has expired.'}
            </p>
            <AuthButton onClick={() => navigate('/login', { replace: true })}>
              Back to Login
            </AuthButton>
          </>
        )}
      </AuthCard>
    </AuthPage>
  )
}
