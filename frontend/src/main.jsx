import './mobile.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { API_URL } from './lib/config'

// ── Global auth interceptor ──────────────────────────────────────────────
// The backend requires a bearer token on data endpoints. Inject the stored
// auth_token into every request to our API, so individual fetch() calls don't
// each need to set the header. On a 401, clear the session and bounce to login.
const _origFetch = window.fetch.bind(window)
window.fetch = async (url, opts = {}) => {
  try {
    const u = typeof url === 'string' ? url : (url && url.url) || ''
    const token = localStorage.getItem('auth_token')
    const isApi = u.indexOf(API_URL) !== -1
    if (token && isApi) {
      opts = { ...opts, headers: { ...(opts.headers || {}), Authorization: `Bearer ${token}` } }
    }
    const res = await _origFetch(url, opts)
    if (res.status === 401 && isApi) {
      // Token missing/expired — clear and send to login (avoid loop if already there).
      localStorage.removeItem('auth_token')
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return res
  } catch (e) {
    return _origFetch(url, opts)
  }
}
// ─────────────────────────────────────────────────────────────────────────

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
