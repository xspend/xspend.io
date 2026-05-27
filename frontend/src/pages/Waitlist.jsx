import { Link } from 'react-router-dom'

const F = "'DM Sans', Inter, -apple-system, BlinkMacSystemFont, system-ui, sans-serif"

const C = {
  bg:         '#fafaf5',
  cardBg:     'rgba(255,255,255,0.65)',
  text:       '#1a1a1a',
  textMuted:  '#5a5a5a',
  textHint:   '#8a8a85',
  border:     'rgba(0,0,0,0.12)',
  accent:     '#e85d3c',
  trustBg:    '#ecf3e8',
  trustText:  '#2d4a1d',
  trustIcon:  '#4a7c2a',
  ctaBg:      '#1a1a1a',
  ctaText:    '#fafaf5',
}

const MAILTO = 'mailto:xspend.io@gmail.com?subject=Beta%20access%20request&body=Hi%2C%0A%0AI%27d%20like%20early%20access%20to%20xspend.%0A%0AA%20bit%20about%20me%3A%0A%0A%5Btell%20us%20a%20bit%20about%20yourself%5D%0A%0AThanks%21'

export default function Waitlist() {
  return (
    <div style={{
      minHeight: '100vh',
      background: C.bg,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: F,
      padding: 20,
    }}>
      <div style={{ width: '100%', maxWidth: 480 }}>

        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
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
              }}/>
            </span>
            <span style={{
              fontWeight: 500,
              fontSize: 18,
              color: C.text,
              letterSpacing: 1.8,
            }}>XSPEND</span>
          </Link>
        </div>

        {/* Card */}
        <div style={{
          background: C.cardBg,
          border: `0.5px solid ${C.border}`,
          borderRadius: 16,
          padding: '40px 36px',
        }}>
          <h1 style={{
            fontSize: 28,
            fontWeight: 500,
            color: C.text,
            margin: '0 0 12px',
            letterSpacing: '-0.01em',
            lineHeight: 1.2,
          }}>
            We're getting things ready.
          </h1>
          <p style={{
            fontSize: 15,
            color: C.textMuted,
            margin: '0 0 28px',
            lineHeight: 1.6,
          }}>
            xspend is in a small private beta while we make sure everything works the way it should. If you'd like early access, send us a note — we'll reach out when we're ready for you.
          </p>

          <a
            href={MAILTO}
            style={{
              display: 'block',
              width: '100%',
              background: C.ctaBg,
              color: C.ctaText,
              borderRadius: 10,
              padding: '14px 20px',
              fontSize: 15,
              fontWeight: 500,
              textDecoration: 'none',
              textAlign: 'center',
              fontFamily: 'inherit',
              boxSizing: 'border-box',
            }}
          >
            Request beta access
          </a>

          <p style={{
            fontSize: 13,
            color: C.textHint,
            textAlign: 'center',
            margin: '14px 0 0',
            lineHeight: 1.5,
          }}>
            Opens your email — write a quick note and we'll get back to you.
          </p>
        </div>

        {/* Trust + back link */}
        <div style={{ marginTop: 28 }}>
          <div style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 10,
            background: C.trustBg,
            borderRadius: 10,
            padding: '12px 16px',
            fontSize: 12,
            color: C.trustText,
            lineHeight: 1.5,
            marginBottom: 20,
          }}>
            <span style={{ color: C.trustIcon, flexShrink: 0, fontSize: 13 }}>✓</span>
            <span>
              <span style={{ fontWeight: 500 }}>Bank-grade encryption.</span> Read-only access. We never move your money.
            </span>
          </div>

          <div style={{ textAlign: 'center' }}>
            <Link to="/" style={{
              fontSize: 13,
              color: C.textHint,
              textDecoration: 'none',
            }}>
              ← Back to home
            </Link>
          </div>
        </div>

      </div>
    </div>
  )
}
