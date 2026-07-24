import { API_URL } from './config'
import { clearSession, getErrorDetail, unwrapEnvelope } from './auth'
import { showToast } from './toast'

const SESSION_EXPIRED_MESSAGE = 'Your session has expired. Please log in again.'
const SESSION_TOAST_KEY = 'auth_session_toast'

/** Auth endpoints that must never trigger a silent refresh on 401. */
const NO_REFRESH_PATHS = [
  '/auth/login',
  '/auth/refresh',
  '/auth/signup',
  '/auth/verify-email',
  '/auth/verify-otp',
  '/auth/resend-verification',
  '/auth/resend-otp',
  '/auth/forgot-password',
  '/auth/reset-password',
]

let refreshPromise = null

export function getAccessToken() {
  return localStorage.getItem('auth_token') || ''
}

export function getRefreshToken() {
  return localStorage.getItem('refresh_token') || ''
}

export function updateStoredTokens({ access_token, refresh_token }) {
  if (access_token) localStorage.setItem('auth_token', access_token)
  if (refresh_token) localStorage.setItem('refresh_token', refresh_token)
}

function urlString(url) {
  if (typeof url === 'string') return url
  if (url && typeof url.url === 'string') return url.url
  try {
    return String(url)
  } catch {
    return ''
  }
}

function isApiUrl(url) {
  return url.indexOf(API_URL) !== -1
}

function isRefreshUrl(url) {
  return url.indexOf('/auth/refresh') !== -1
}

function shouldAttemptRefresh(url) {
  if (!isApiUrl(url) || isRefreshUrl(url)) return false
  return !NO_REFRESH_PATHS.some((path) => url.indexOf(path) !== -1)
}

function mergeHeaders(existing, extra) {
  const headers = { ...(existing || {}) }
  Object.assign(headers, extra || {})
  return headers
}

/**
 * Single-flight refresh: concurrent 401s share one POST /auth/refresh call.
 * Uses the raw fetch implementation so the interceptor cannot recurse.
 */
async function refreshAccessToken(rawFetch) {
  const refresh_token = getRefreshToken()
  if (!refresh_token) return null

  const res = await rawFetch(`${API_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token }),
  })

  let data = null
  try {
    data = unwrapEnvelope(await res.json())
  } catch {
    data = null
  }

  if (!res.ok) {
    const detail = getErrorDetail(data, '')
    // Treat auth failures uniformly — caller will clear session.
    if (res.status === 401 || res.status === 403 || detail) {
      return null
    }
    return null
  }

  const access_token = data?.access_token || data?.token || ''
  const next_refresh = data?.refresh_token || ''
  if (!access_token) return null

  updateStoredTokens({
    access_token,
    refresh_token: next_refresh || undefined,
  })
  return access_token
}

function queueRefresh(rawFetch) {
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken(rawFetch).finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

export function forceSessionExpiryRedirect() {
  clearSession()
  try {
    sessionStorage.setItem(
      SESSION_TOAST_KEY,
      JSON.stringify({ message: SESSION_EXPIRED_MESSAGE, type: 'error' })
    )
  } catch {
    // ignore storage failures
  }
  showToast(SESSION_EXPIRED_MESSAGE, 'error')
  if (!window.location.pathname.startsWith('/login')) {
    window.location.href = '/login'
  }
}

/** Call from Login (or App) to surface a session-expired toast after hard redirect. */
export function consumeSessionToast() {
  try {
    const raw = sessionStorage.getItem(SESSION_TOAST_KEY)
    if (!raw) return
    sessionStorage.removeItem(SESSION_TOAST_KEY)
    const parsed = JSON.parse(raw)
    if (parsed?.message) showToast(parsed.message, parsed.type || 'error')
  } catch {
    sessionStorage.removeItem(SESSION_TOAST_KEY)
  }
}

/**
 * Installs the global fetch interceptor:
 * - Attaches Bearer access_token to API requests
 * - On 401, refreshes once (shared across concurrent failures) and retries
 * - On refresh failure, clears session and sends the user to Login
 */
export function installAuthFetchInterceptor() {
  const rawFetch = window.fetch.bind(window)

  window.fetch = async (url, opts = {}) => {
    const u = urlString(url)
    const isApi = isApiUrl(u)
    const alreadyRetried = Boolean(opts && opts._authRetry)

    const nextOpts = { ...opts }
    // Strip internal flag so it is never sent over the wire as a header-like field.
    // It stays on the options object for our interceptor only.
    if (isApi && !isRefreshUrl(u)) {
      const token = getAccessToken()
      if (token) {
        nextOpts.headers = mergeHeaders(nextOpts.headers, {
          Authorization: `Bearer ${token}`,
        })
      }
    }

    let res
    try {
      res = await rawFetch(url, nextOpts)
    } catch {
      return rawFetch(url, opts)
    }

    if (
      res.status !== 401 ||
      !isApi ||
      alreadyRetried ||
      !shouldAttemptRefresh(u)
    ) {
      return res
    }

    const refresh_token = getRefreshToken()
    if (!refresh_token) {
      if (!opts._skipAuthRedirect) forceSessionExpiryRedirect()
      return res
    }

    const newAccess = await queueRefresh(rawFetch)
    if (!newAccess) {
      if (!opts._skipAuthRedirect) forceSessionExpiryRedirect()
      return res
    }

    const retryOpts = {
      ...nextOpts,
      _authRetry: true,
      _skipAuthRedirect: Boolean(opts._skipAuthRedirect),
      headers: mergeHeaders(nextOpts.headers, {
        Authorization: `Bearer ${newAccess}`,
      }),
    }

    return rawFetch(url, retryOpts)
  }
}
