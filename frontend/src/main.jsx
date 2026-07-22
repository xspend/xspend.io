import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './mobile.css'
import './index.css'
import App from './App.jsx'
import { installAuthFetchInterceptor } from './lib/apiClient'

// Global fetch interceptor: injects Bearer tokens and silently refreshes
// expired access tokens via POST /auth/refresh (single-flight + one retry).
installAuthFetchInterceptor()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
