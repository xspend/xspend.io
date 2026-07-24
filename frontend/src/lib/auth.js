import { API_URL } from './config'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const MIN_PASSWORD_LENGTH = 8

export function isValidEmail(email) {
  return EMAIL_RE.test(String(email || '').trim())
}

export function validatePassword(password) {
  if (!password) return 'Password is required'
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters`
  }
  return ''
}

/** Stricter rules for logged-in change-password (Settings). */
export function validateStrongPassword(password) {
  if (!password) return 'Password is required'
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters`
  }
  if (!/[A-Z]/.test(password)) return 'Password must contain an uppercase letter'
  if (!/[a-z]/.test(password)) return 'Password must contain a lowercase letter'
  if (!/[0-9]/.test(password)) return 'Password must contain a number'
  if (!/[^A-Za-z0-9]/.test(password)) {
    return 'Password must contain a special character'
  }
  return ''
}

export function getErrorDetail(data, fallback = 'Something went wrong') {
  if (!data) return fallback
  const detail = data.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msgs = detail.map((e) => e?.msg || e?.message).filter(Boolean)
    if (msgs.length) return msgs.join('. ')
  }
  if (detail && typeof detail === 'object' && detail.message) return detail.message
  if (typeof data.message === 'string') return data.message
  return fallback
}

async function parseJson(res) {
  try {
    return await res.json()
  } catch {
    return null
  }
}

// Auth endpoints wrap their body in {status, message, data}. Flatten that
// back to the old top-level shape so every existing caller (data.access_token,
// data.login_token, data.user, ...) keeps working unchanged.
export function unwrapEnvelope(body) {
  if (body && typeof body === 'object' && 'status' in body && 'data' in body) {
    return { ...(body.data || {}), message: body.message }
  }
  return body
}

async function authFetch(path, body) {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = unwrapEnvelope(await parseJson(res))
  return { res, data }
}

export function saveSession({ access_token, refresh_token, user }) {
  if (access_token) localStorage.setItem('auth_token', access_token)
  if (refresh_token) localStorage.setItem('refresh_token', refresh_token)
  if (user?.email) localStorage.setItem('user_email', user.email)
  if (user?.name) localStorage.setItem('user_name', String(user.name).split(' ')[0])
  localStorage.setItem('onboarding_complete', 'true')
}

export function clearSession() {
  localStorage.removeItem('auth_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user_name')
  localStorage.removeItem('user_email')
  clearPending2FA()
}

const PENDING_2FA_KEY = 'pending_2fa'

export function savePending2FA({
  login_token = '',
  temp_token = '',
  email = '',
  access_token = '',
  refresh_token = '',
  user = null,
}) {
  const token = login_token || temp_token || ''
  localStorage.setItem(PENDING_2FA_KEY, JSON.stringify({
    login_token: token,
    email: email || '',
    access_token: access_token || '',
    refresh_token: refresh_token || '',
    user: user || null,
  }))
  // Clear any existing authenticated session — dashboard only after OTP.
  localStorage.removeItem('auth_token')
}

export function getPending2FA() {
  try {
    const raw = localStorage.getItem(PENDING_2FA_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      const login_token = parsed.login_token || parsed.temp_token || ''
      return {
        login_token,
        temp_token: login_token,
        email: parsed.email || '',
        access_token: parsed.access_token || '',
        refresh_token: parsed.refresh_token || '',
        user: parsed.user || null,
      }
    }
  } catch {
    // fall through to legacy keys
  }

  // Legacy single-key format (from earlier auth work)
  const legacyToken = localStorage.getItem('pending_2fa_token') || ''
  return {
    login_token: legacyToken,
    temp_token: legacyToken,
    email: localStorage.getItem('pending_2fa_email') || '',
    access_token: '',
    refresh_token: '',
    user: null,
  }
}

export function clearPending2FA() {
  localStorage.removeItem(PENDING_2FA_KEY)
  localStorage.removeItem('pending_2fa_token')
  localStorage.removeItem('pending_2fa_email')
}

export function isEmailNotVerifiedError(message) {
  return /verify your email/i.test(String(message || ''))
}

export function is2FARequired(data) {
  if (!data || typeof data !== 'object') return false
  return Boolean(
    data.requires_2fa ||
    data.two_factor_required ||
    data.requires_two_factor ||
    data['2fa_required']
  )
}

export async function signup({ email, password, name }) {
  return authFetch('/auth/signup', { email, password, name })
}

export async function login({ email, password }) {
  return authFetch('/auth/login', { email, password })
}

export async function verifyEmail({ token, eid }) {
  const body = { token }
  // Always include eid when provided so the backend can run its sanity check.
  if (eid != null && eid !== '') body.eid = eid
  return authFetch('/auth/verify-email', body)
}

export async function resendVerification({ email }) {
  return authFetch('/auth/resend-verification', { email })
}

export async function forgotPassword({ email }) {
  return authFetch('/auth/forgot-password', { email })
}

export async function resetPassword({ token, eid, new_password }) {
  return authFetch('/auth/reset-password', {
    token,
    eid: eid || '',
    new_password,
  })
}

export async function changePassword({ current_password, new_password }) {
  return authFetch('/auth/change-password', {
    current_password,
    new_password,
  })
}

/**
 * POST /auth/logout — blacklists access token and optionally revokes refresh.
 * Passes _skipAuthRedirect so a 401 does not trigger the global session-expired
 * hard redirect; the caller decides how to clear local state.
 */
export async function logout() {
  const refresh_token = localStorage.getItem('refresh_token') || ''
  const body = refresh_token ? { refresh_token } : {}
  const res = await fetch(`${API_URL}/auth/logout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    _skipAuthRedirect: true,
  })
  const data = await parseJson(res)
  return { res, data }
}

export function isNotAuthenticatedError(res, data) {
  if (res?.status === 401 || res?.status === 403) return true
  const detail = getErrorDetail(data, '')
  return /not authenticated/i.test(detail)
}

export async function verifyOtp({ login_token, otp }) {
  return authFetch('/auth/verify-otp', {
    login_token,
    otp,
  })
}

/** @deprecated Use verifyOtp — kept as an alias for existing imports. */
export async function verifyTwoFactor({ login_token, code, otp }) {
  return verifyOtp({
    login_token,
    otp: otp || code,
  })
}

export async function resendOtp({ login_token }) {
  return authFetch('/auth/resend-otp', {
    login_token,
  })
}

/** @deprecated Use resendOtp — kept as an alias for existing imports. */
export async function resendTwoFactor({ login_token }) {
  return resendOtp({ login_token })
}
