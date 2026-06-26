import { Link } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'

const F = "'DM Sans', Inter, -apple-system, BlinkMacSystemFont, system-ui, sans-serif"

const scrollTo = id => {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const FAQ_ITEMS = [
  {
    q: 'What is xspend?',
    a: 'A personal finance dashboard built around awareness, not control. We help you see where your money goes, separate fixed from flexible spending, and notice patterns — without budgets or judgment.'
  },
  {
    q: 'How is it different from Mint?',
    a: "Mint and similar apps are built around budgeting — they want you to set targets and meet them. xspend is built around awareness — we show you what's happening and trust you to decide what to do. We don't sell data, show ads, or moralize."
  },
  {
    q: 'Do you move my money?',
    a: 'No. xspend is read-only. We can see your transactions to categorize and analyze them, but we cannot transfer money, change account settings, or initiate any movement.'
  },
  {
    q: 'Can I delete my data?',
    a: "Yes, anytime. Your account is immediately deactivated and all data is hard-deleted within 30 days. We don't retain anything after deletion."
  },
]

const C = {
  bg:         '#fafaf5',
  bgSubtle:   'rgba(255,255,255,0.65)',
  text:       '#1a1a1a',
  textMuted:  '#5a5a5a',
  textHint:   '#8a8a85',
  border:     'rgba(0,0,0,0.08)',
  borderSoft: 'rgba(0,0,0,0.04)',
  borderBar:  'rgba(0,0,0,0.06)',
  accent:     '#e85d3c',
  trustBg:    '#ecf3e8',
  trustText:  '#2d4a1d',
  trustIcon:  '#4a7c2a',
  ctaBg:      '#1a1a1a',
  ctaText:    '#fafaf5',
  flexGrad:   'linear-gradient(90deg, #3b82f6, #6366f1)',
  fixedBg:    '#475569',
}

function useInView(threshold = 0.35) {
  const ref = useRef(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    if (!ref.current || inView) return
    const observer = new IntersectionObserver(
      entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting && entry.intersectionRatio >= threshold) {
            setInView(true)
            observer.disconnect()
          }
        })
      },
      { threshold: [threshold] }
    )
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [threshold, inView])

  return [ref, inView]
}

function FeatureCategoryPreview() {
  const [ref, inView] = useInView()
  const rows = [
    { emoji: '🛒', name: 'Groceries',     amount: 653, target: 100, pct: 32 },
    { emoji: '🍽️', name: 'Food & Dining',  amount: 445, target: 68,  pct: 22 },
    { emoji: '🛍️', name: 'Shopping',       amount: 310, target: 47,  pct: 15 },
    { emoji: '🚗', name: 'Transport',     amount: 185, target: 28,  pct: 9  },
  ]

  return (
    <div ref={ref} style={previewBoxStyle}>
      {rows.map((r, i) => (
        <div key={r.name} style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '6px 0',
          fontSize: 14,
        }}>
          <span style={{ width: 18, fontSize: 16 }}>{r.emoji}</span>
          <span style={{ flex: 1, color: C.text }}>{r.name}</span>
          <span style={{
            color: C.text,
            fontWeight: 500,
            fontFamily: 'ui-monospace, monospace',
            minWidth: 50,
            textAlign: 'right',
          }}>${r.amount}</span>
          <div style={{
            width: 100,
            height: 4,
            background: C.borderBar,
            borderRadius: 99,
            overflow: 'hidden',
          }}>
            <div style={{
              width: inView ? `${r.target}%` : '0%',
              height: '100%',
              background: C.flexGrad,
              transition: `width 600ms cubic-bezier(0.22, 1, 0.36, 1) ${i * 80}ms`,
            }}/>
          </div>
          <span style={{
            color: C.textHint,
            fontSize: 13,
            minWidth: 28,
            textAlign: 'right',
            opacity: inView ? 1 : 0,
            transition: `opacity 400ms ease ${350 + i * 80}ms`,
          }}>{r.pct}%</span>
        </div>
      ))}
    </div>
  )
}

function FeatureSplitPreview() {
  const [ref, inView] = useInView()

  return (
    <div ref={ref} style={{ ...previewBoxStyle, padding: 18 }}>
      <div style={{
        display: 'flex',
        gap: 0,
        height: 16,
        borderRadius: 8,
        overflow: 'hidden',
        marginBottom: 14,
        background: 'rgba(0,0,0,0.04)',
      }}>
        <div style={{
          width: inView ? '84%' : '0%',
          height: '100%',
          background: C.flexGrad,
          transition: 'width 700ms cubic-bezier(0.22, 1, 0.36, 1) 60ms',
        }}/>
        <div style={{
          width: inView ? '16%' : '0%',
          height: '100%',
          background: C.fixedBg,
          transition: 'width 500ms cubic-bezier(0.22, 1, 0.36, 1) 500ms',
        }}/>
      </div>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        opacity: inView ? 1 : 0,
        transition: 'opacity 500ms ease 950ms',
      }}>
        <div>
          <div style={splitLabelStyle}>Flexible</div>
          <div style={splitAmountStyle}>$2,202</div>
          <div style={splitSublineStyle}>84% · groceries, dining, shopping</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={splitLabelStyle}>Fixed</div>
          <div style={splitAmountStyle}>$412</div>
          <div style={splitSublineStyle}>16% · rent, utilities, subs</div>
        </div>
      </div>
    </div>
  )
}

function FeatureInsightsPreview() {
  const [ref, inView] = useInView()
  const insights = [
    { emoji: '🍽️', text: 'You dined out 16 times this month.' },
    { emoji: '📅', text: 'Most shopping happened in a 2-day burst around Apr 14–15.' },
    { emoji: '🔁', text: '7 active subscriptions · $127/month.' },
  ]

  return (
    <div ref={ref} style={{
      ...previewBoxStyle,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      {insights.map((ins, i) => (
        <div key={i} style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 10,
          padding: '10px 12px',
          background: 'rgba(255,255,255,0.9)',
          border: `0.5px solid ${C.borderBar}`,
          borderRadius: 8,
          opacity: inView ? 1 : 0,
          transform: inView ? 'translateY(0)' : 'translateY(6px)',
          transition: `opacity 400ms ease ${i * 300}ms, transform 400ms cubic-bezier(0.22, 1, 0.36, 1) ${i * 300}ms`,
        }}>
          <span style={{ fontSize: 15, flexShrink: 0 }}>{ins.emoji}</span>
          <span style={{ fontSize: 14, color: C.text, lineHeight: 1.5 }}>{ins.text}</span>
        </div>
      ))}
    </div>
  )
}

function FeatureCard({ icon, title, tagline, body, children }) {
  return (
    <div style={{
      padding: 26,
      background: C.bgSubtle,
      border: `0.5px solid ${C.border}`,
      borderRadius: 14,
    }}>
      <div style={{ display: 'flex', gap: 18, alignItems: 'flex-start' }}>
        <span style={{ fontSize: 28, lineHeight: 1.2, flexShrink: 0 }}>{icon}</span>
        <div style={{ flex: 1 }}>
          <h3 style={{
            fontSize: 18,
            fontWeight: 500,
            color: C.text,
            margin: '0 0 4px',
          }}>{title}</h3>
          <p style={{
            fontSize: 15,
            color: C.textHint,
            margin: 0,
          }}>{tagline}</p>
        </div>
      </div>
      {children}
      <p style={{
        fontSize: 16,
        color: C.textMuted,
        margin: '0 0 0 44px',
        lineHeight: 1.6,
      }}>{body}</p>
    </div>
  )
}

export default function Landing() {
  const [openFaq, setOpenFaq] = useState(null)

  return (
    <div style={{
      minHeight: '100vh',
      background: C.bg,
      color: C.text,
      fontFamily: F,
      overflowX: 'hidden',
    }}>

      {/* NAV */}
      <nav style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '20px 48px',
        background: C.bg,
        borderBottom: `0.5px solid ${C.borderSoft}`,
        position: 'sticky',
        top: 0,
        zIndex: 50,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
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
            fontSize: 20,
            color: C.text,
            letterSpacing: 1.8,
          }}>XSPEND</span>
        </div>

        <div style={{ display: 'flex', gap: 32, fontSize: 16, color: C.textMuted }}>
          <button onClick={() => scrollTo('features')} style={navLinkStyle}>Features</button>
          <button onClick={() => scrollTo('how-it-works')} style={navLinkStyle}>How it works</button>
          <button onClick={() => scrollTo('contact-faq')} style={navLinkStyle}>Contact & FAQ</button>
        </div>
      </nav>

      {/* HERO */}
      <section style={{
        textAlign: 'center',
        padding: '120px 32px 80px',
        maxWidth: 720,
        margin: '0 auto',
      }}>
        <h1 style={{
          fontSize: 54,
          fontWeight: 500,
          lineHeight: 1.1,
          color: C.text,
          margin: '0 0 24px',
          letterSpacing: '-0.02em',
        }}>
          See every dollar.<br/>Understand where it went.
        </h1>
        <p style={{
          fontSize: 18,
          color: C.textMuted,
          lineHeight: 1.6,
          maxWidth: 480,
          margin: '0 auto 36px',
        }}>
          Connect your bank or upload statements — your choice. A clear picture in 60 seconds. No judgment.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
          <Link to={import.meta.env.PROD ? "/waitlist" : "/signup"} style={{
            background: C.ctaBg,
            color: C.ctaText,
            border: 'none',
            borderRadius: 10,
            padding: '14px 36px',
            fontSize: 17,
            fontWeight: 500,
            textDecoration: 'none',
            fontFamily: 'inherit',
            display: 'inline-block',
          }}>
            Get started — it's free
          </Link>
          <Link to="/login" style={{
            fontSize: 16,
            color: C.textMuted,
            textDecoration: 'none',
            fontFamily: 'inherit',
          }}>
            I already have an account →
          </Link>
        </div>

        <div style={{
          display: 'inline-flex',
          alignItems: 'flex-start',
          gap: 10,
          background: C.trustBg,
          borderRadius: 10,
          padding: '12px 18px',
          marginTop: 40,
          fontSize: 15,
          color: C.trustText,
          maxWidth: 460,
          lineHeight: 1.5,
        }}>
          <span style={{ color: C.trustIcon, flexShrink: 0, fontSize: 16 }}>✓</span>
          <span><span style={{ fontWeight: 500 }}>Bank-grade encryption.</span> Read-only access. We never move your money.</span>
        </div>

        <button
          onClick={() => scrollTo('features')}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            marginTop: 56,
            color: C.textHint,
            fontSize: 14,
            letterSpacing: 1,
            fontFamily: 'inherit',
            padding: 8,
            display: 'block',
            margin: '56px auto 0',
          }}
        >
          <div style={{ fontSize: 22, lineHeight: 1, marginBottom: 6 }}>↓</div>
          See more
        </button>
      </section>

      {/* FEATURES */}
      <style>{`@media (max-width: 760px){ .features-grid{ grid-template-columns: 1fr !important; } }`}</style>
      <section id="features" style={{
        padding: '80px 32px 60px',
        maxWidth: 1080,
        margin: '0 auto',
        borderTop: `0.5px solid ${C.borderSoft}`,
        scrollMarginTop: 80,
      }}>
        <p style={{
          fontSize: 17,
          color: C.textMuted,
          textAlign: 'center',
          margin: '0 0 44px',
          fontStyle: 'italic',
        }}>
          Understand your spending without budgeting your life.
        </p>

        <div style={eyebrowStyle}>Features</div>
        <h2 style={sectionHeadingStyle}>What xspend gives you</h2>

        <div className="features-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 20, alignItems: 'stretch' }}>
          <FeatureCard
            icon="🔍"
            title="See where your money actually goes"
            tagline="Spending, categorized."
            body="Automatically categorize spending across groceries, dining, shopping, travel, bills, and more — without manual tracking or spreadsheets."
          >
            <div style={previewWrapperStyle}>
              <FeatureCategoryPreview />
            </div>
          </FeatureCard>

          <FeatureCard
            icon="⚖️"
            title="Know what's a choice and what's not"
            tagline="Fixed vs flexible."
            body="Understand what's committed versus what's changeable. See the difference between structural expenses and everyday choices in one clear view."
          >
            <div style={previewWrapperStyle}>
              <FeatureSplitPreview />
            </div>
          </FeatureCard>

          <FeatureCard
            icon="💬"
            title="Get insights written in plain English"
            tagline="Patterns, surfaced."
            body="Spot patterns without digging through charts. From subscription changes to spending habits, xspend highlights what changed and what's worth noticing."
          >
            <div style={previewWrapperStyle}>
              <FeatureInsightsPreview />
            </div>
          </FeatureCard>

          <FeatureCard
            icon="🎯"
            title="Track spending around what matters"
            tagline="Projects, your way."
            body="Group spending around a trip, a renovation, a move, or any goal. Tag transactions to a project and watch the total add up automatically — see exactly what something really cost."
          />
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section id="how-it-works" style={{
        padding: '80px 32px 60px',
        maxWidth: 720,
        margin: '0 auto',
        borderTop: `0.5px solid ${C.borderSoft}`,
        scrollMarginTop: 80,
      }}>
        <div style={eyebrowStyle}>How it works</div>
        <h2 style={sectionHeadingStyle}>Three steps to clarity</h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
          {[
            { n: 1, title: 'Create your account', body: 'Email and password. No credit card needed.' },
            { n: 2, title: 'Upload your statements', body: 'Export from your bank as CSV, Excel, PDF, or OFX and upload — we handle the parsing. Tested with Chase, Amex, Bank of America, Wells Fargo, and more.' },
            { n: 3, title: 'See your spending, clearly', body: 'Spending organized by category, fixed vs flexible separated, patterns surfaced — without budgets or judgment.' },
          ].map(s => (
            <div key={s.n} style={{ display: 'flex', gap: 20 }}>
              <div style={{
                flexShrink: 0,
                width: 32,
                height: 32,
                borderRadius: '50%',
                background: C.ctaBg,
                color: C.ctaText,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 16,
                fontWeight: 500,
              }}>
                {s.n}
              </div>
              <div>
                <h3 style={{ ...cardTitleStyle, marginTop: 4 }}>{s.title}</h3>
                <p style={cardBodyStyle}>{s.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* CONTACT & FAQ */}
      <section id="contact-faq" style={{
        padding: '80px 32px 100px',
        maxWidth: 720,
        margin: '0 auto',
        borderTop: `0.5px solid ${C.borderSoft}`,
        scrollMarginTop: 80,
      }}>
        <div style={eyebrowStyle}>Contact & FAQ</div>
        <h2 style={sectionHeadingStyle}>Questions?</h2>

        <div>
          {FAQ_ITEMS.map((item, i) => {
            const isOpen = openFaq === i
            const isLast = i === FAQ_ITEMS.length - 1
            return (
              <div key={i} style={{
                borderBottom: isLast ? 'none' : `0.5px solid ${C.border}`,
                padding: '18px 0',
              }}>
                <button
                  onClick={() => setOpenFaq(isOpen ? null : i)}
                  style={{
                    width: '100%',
                    background: 'none',
                    border: 'none',
                    padding: 0,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    fontSize: 17,
                    fontWeight: 500,
                    color: C.text,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    textAlign: 'left',
                  }}
                >
                  <span>{item.q}</span>
                  <span style={{
                    color: C.textHint,
                    fontSize: 20,
                    fontWeight: 400,
                    transform: isOpen ? 'rotate(45deg)' : 'rotate(0deg)',
                    transition: 'transform 0.2s',
                  }}>+</span>
                </button>
                {isOpen && (
                  <p style={{
                    fontSize: 16,
                    color: C.textMuted,
                    margin: '12px 0 4px',
                    lineHeight: 1.65,
                  }}>
                    {item.a}
                  </p>
                )}
              </div>
            )
          })}
        </div>

        <div style={{
          marginTop: 36,
          paddingTop: 24,
          borderTop: `0.5px solid ${C.borderSoft}`,
          fontSize: 16,
          color: C.textMuted,
        }}>
          Still have questions?{' '}
          <a href="mailto:xspend.io@gmail.com" style={{
            color: C.text,
            textDecoration: 'underline',
            textUnderlineOffset: 3,
          }}>
            xspend.io@gmail.com
          </a>
        </div>
      </section>

      <footer style={{
        padding: '32px',
        borderTop: `0.5px solid ${C.borderSoft}`,
        textAlign: 'center',
        fontSize: 14,
        color: C.textHint,
      }}>
        © {new Date().getFullYear()} xspend
      </footer>

    </div>
  )
}

const navLinkStyle = {
  background: 'none',
  border: 'none',
  color: 'inherit',
  fontSize: 16,
  fontWeight: 400,
  cursor: 'pointer',
  padding: 0,
  fontFamily: 'inherit',
}

const eyebrowStyle = {
  fontSize: 13,
  color: '#8a8a85',
  letterSpacing: 1.5,
  textTransform: 'uppercase',
  marginBottom: 12,
  fontWeight: 500,
}

const sectionHeadingStyle = {
  fontSize: 30,
  fontWeight: 500,
  color: '#1a1a1a',
  margin: '0 0 32px',
  letterSpacing: '-0.01em',
}

const cardTitleStyle = {
  fontSize: 18,
  fontWeight: 500,
  color: '#1a1a1a',
  margin: '0 0 8px',
}

const cardBodyStyle = {
  fontSize: 16,
  color: '#5a5a5a',
  margin: 0,
  lineHeight: 1.6,
}

const previewBoxStyle = {
  padding: 16,
  background: '#fafaf5',
  border: '0.5px solid rgba(0,0,0,0.06)',
  borderRadius: 10,
}

const previewWrapperStyle = {
  margin: '16px 0 14px 44px',
}

const splitLabelStyle = {
  fontSize: 12,
  color: '#8a8a85',
  textTransform: 'uppercase',
  letterSpacing: 1,
  marginBottom: 4,
}

const splitAmountStyle = {
  fontFamily: 'ui-monospace, monospace',
  color: '#1a1a1a',
  fontSize: 18,
  fontWeight: 500,
}

const splitSublineStyle = {
  fontSize: 13,
  color: '#8a8a85',
}
