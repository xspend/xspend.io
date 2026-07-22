import { Link } from 'react-router-dom'
import { Eye, EyeOff } from 'lucide-react'
import { useState } from 'react'
import {
  AUTH_FONT,
  AUTH_COLORS,
  inputStyle,
  fieldErrorStyle,
} from '../lib/authStyles'

export function AuthLogo() {
  const C = AUTH_COLORS
  return (
    <div style={{ textAlign: 'center', marginBottom: 36 }}>
      <Link to="/" style={{
        textDecoration: 'none',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 10,
      }}>
        <span style={{
          width: 28,
          height: 28,
          borderRadius: '50%',
          background: C.text,
          display: 'inline-flex',
          position: 'relative',
        }}>
          <span style={{
            position: 'absolute',
            top: 4,
            right: 4,
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: C.accent,
          }} />
        </span>
        <span style={{
          fontWeight: 500,
          fontSize: 20,
          color: C.text,
          letterSpacing: 1.8,
        }}>XSPEND</span>
      </Link>
    </div>
  )
}

export function AuthPage({ children, showHomeLink = true }) {
  const C = AUTH_COLORS
  return (
    <div style={{
      minHeight: '100vh',
      background: C.bg,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: AUTH_FONT,
      padding: 20,
    }}>
      <div style={{ width: '100%', maxWidth: 420 }}>
        <AuthLogo />
        {children}
        {showHomeLink && (
          <div style={{ textAlign: 'center', marginTop: 24 }}>
            <Link to="/" style={{
              fontSize: 15,
              color: C.textHint,
              textDecoration: 'none',
            }}>
              ← Back
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}

export function AuthCard({ title, subtitle, children }) {
  const C = AUTH_COLORS
  return (
    <div style={{
      background: C.cardBg,
      border: `0.5px solid ${C.border}`,
      borderRadius: 16,
      padding: '36px 32px',
    }}>
      {title && (
        <h1 style={{
          fontSize: 26,
          fontWeight: 500,
          color: C.text,
          margin: '0 0 6px',
          textAlign: 'center',
          letterSpacing: '-0.01em',
        }}>
          {title}
        </h1>
      )}
      {subtitle && (
        <p style={{
          fontSize: 16,
          color: C.textMuted,
          textAlign: 'center',
          margin: '0 0 28px',
        }}>
          {subtitle}
        </p>
      )}
      {children}
    </div>
  )
}

export function ErrorBanner({ message }) {
  const C = AUTH_COLORS
  if (!message) return null
  return (
    <div style={{
      background: C.errorBg,
      border: `0.5px solid ${C.errorBorder}`,
      borderRadius: 10,
      padding: '10px 14px',
      marginBottom: 18,
    }}>
      <p style={{ color: C.errorText, fontSize: 15, margin: 0 }}>{message}</p>
    </div>
  )
}

export function SuccessBanner({ message }) {
  const C = AUTH_COLORS
  if (!message) return null
  return (
    <div style={{
      background: C.successBg,
      border: `0.5px solid ${C.successBorder}`,
      borderRadius: 10,
      padding: '10px 14px',
      marginBottom: 18,
    }}>
      <p style={{ color: C.successText, fontSize: 15, margin: 0 }}>{message}</p>
    </div>
  )
}

export function AuthButton({ loading, children, disabled, style, ...props }) {
  const C = AUTH_COLORS
  const isDisabled = loading || disabled
  return (
    <button
      type="button"
      disabled={isDisabled}
      style={{
        width: '100%',
        background: C.ctaBg,
        color: C.ctaText,
        border: 'none',
        borderRadius: 10,
        padding: '13px 20px',
        fontSize: 17,
        fontWeight: 500,
        cursor: isDisabled ? 'default' : 'pointer',
        opacity: isDisabled ? 0.6 : 1,
        marginTop: 22,
        fontFamily: 'inherit',
        transition: 'opacity 0.15s',
        ...style,
      }}
      {...props}
    >
      {children}
    </button>
  )
}

export function PasswordInput({
  value,
  onChange,
  onKeyDown,
  placeholder,
  autoComplete = 'current-password',
  autoFocus = false,
  id,
}) {
  const [show, setShow] = useState(false)
  return (
    <div style={{ position: 'relative' }}>
      <input
        id={id}
        type={show ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        style={{ ...inputStyle, paddingRight: 44 }}
        autoComplete={autoComplete}
        autoFocus={autoFocus}
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? 'Hide password' : 'Show password'}
        style={{
          position: 'absolute',
          right: 10,
          top: '50%',
          transform: 'translateY(-50%)',
          background: 'none',
          border: 'none',
          padding: 4,
          cursor: 'pointer',
          color: AUTH_COLORS.textHint,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {show ? <EyeOff size={18} /> : <Eye size={18} />}
      </button>
    </div>
  )
}

export function FieldError({ message }) {
  if (!message) return null
  return <p style={fieldErrorStyle}>{message}</p>
}

export function SuccessDialog({ open, title, children, primaryLabel, onPrimary }) {
  const C = AUTH_COLORS
  if (!open) return null
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-success-title"
      style={{
        position: 'fixed',
        inset: 0,
        background: C.overlay,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
        zIndex: 1000,
        fontFamily: AUTH_FONT,
      }}
    >
      <div style={{
        width: '100%',
        maxWidth: 420,
        background: '#fff',
        border: `0.5px solid ${C.border}`,
        borderRadius: 16,
        padding: '32px 28px',
        boxShadow: '0 16px 40px rgba(0,0,0,0.12)',
      }}>
        <h2 id="auth-success-title" style={{
          fontSize: 22,
          fontWeight: 500,
          color: C.text,
          margin: '0 0 12px',
          textAlign: 'center',
        }}>
          {title}
        </h2>
        <div style={{
          fontSize: 15,
          color: C.textMuted,
          lineHeight: 1.55,
          textAlign: 'center',
          marginBottom: 24,
        }}>
          {children}
        </div>
        <AuthButton onClick={onPrimary} style={{ marginTop: 0 }}>
          {primaryLabel}
        </AuthButton>
      </div>
    </div>
  )
}
