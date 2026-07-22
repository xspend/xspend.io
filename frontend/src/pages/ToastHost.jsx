import { useEffect, useState } from 'react'
import { subscribeToast } from '../lib/toast'
import { AUTH_COLORS, AUTH_FONT } from '../lib/authStyles'

const DISMISS_MS = 3200

export default function ToastHost() {
  const [toasts, setToasts] = useState([])

  useEffect(() => {
    return subscribeToast((toast) => {
      setToasts((prev) => [...prev, toast])
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== toast.id))
      }, DISMISS_MS)
    })
  }, [])

  if (!toasts.length) return null

  return (
    <div
      aria-live="polite"
      style={{
        position: 'fixed',
        top: 20,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 2000,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        width: 'min(440px, calc(100vw - 32px))',
        pointerEvents: 'none',
        fontFamily: AUTH_FONT,
      }}
    >
      {toasts.map((toast) => {
        const isError = toast.type === 'error'
        return (
          <div
            key={toast.id}
            role="status"
            style={{
              pointerEvents: 'auto',
              background: isError ? AUTH_COLORS.errorBg : AUTH_COLORS.successBg,
              border: `0.5px solid ${isError ? AUTH_COLORS.errorBorder : AUTH_COLORS.successBorder}`,
              color: isError ? AUTH_COLORS.errorText : AUTH_COLORS.successText,
              borderRadius: 12,
              padding: '12px 16px',
              fontSize: 15,
              fontWeight: 500,
              boxShadow: '0 10px 28px rgba(0,0,0,0.10)',
              textAlign: 'center',
            }}
          >
            {toast.message}
          </div>
        )
      })}
    </div>
  )
}
