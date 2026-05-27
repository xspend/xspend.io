// API base URL — set via .env.local for development, Vercel env vars for production.
// Falls back to localhost so dev still works if env var isn't set.
export const API_URL = import.meta.env.VITE_API_URL || `${API_URL}`
