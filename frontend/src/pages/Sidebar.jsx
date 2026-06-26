import { Link, useLocation } from 'react-router-dom'
import { Upload, LayoutDashboard, ArrowLeftRight, FolderKanban, MessageSquare } from 'lucide-react'

const NAV_ITEMS = [
  { to: '/app/upload',       label: 'Upload',       Icon: Upload },
  { to: '/app/dashboard',    label: 'Dashboard',    Icon: LayoutDashboard },
  { to: '/app/transactions', label: 'Transactions', Icon: ArrowLeftRight },
  { to: '/app/projects',     label: 'Projects',     Icon: FolderKanban },
  { to: '/app/chat',         label: 'Chat',         Icon: MessageSquare },
]

const COLORS = {
  bg:            '#f5f4ef',
  border:        'rgba(0,0,0,0.08)',
  textPrimary:   '#1a1a1a',
  textSecondary: '#5a5a5a',
  textMuted:     '#8a8a85',
  activeBg:      'rgba(232,93,60,0.08)',
  activeText:    '#1a1a1a',
  activeBorder:  '#e85d3c',
  hoverBg:       'rgba(0,0,0,0.04)',
}

export default function Sidebar() {
  const location = useLocation()

  return (
    <aside style={{
      width: 240,
      minHeight: '100vh',
      background: COLORS.bg,
      borderRight: `1px solid ${COLORS.border}`,
      padding: '24px 16px',
      display: 'flex',
      flexDirection: 'column',
      position: 'sticky',
      top: 0,
      flexShrink: 0,
    }}>
      <Link to="/" style={{
        display: 'block',
        padding: '16px 12px 32px 12px',
        fontWeight: 700,
        fontSize: 30,
        color: COLORS.textPrimary,
        letterSpacing: '-0.02em',
        textDecoration: 'none',
        cursor: 'pointer',
      }}>
        xspend
      </Link>

      <nav style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {NAV_ITEMS.map(({ to, label, Icon }) => {
          const isActive = location.pathname.startsWith(to)
          return (
            <Link
              key={to}
              to={to}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 14,
                padding: '12px 14px',
                borderRadius: 8,
                textDecoration: 'none',
                color: isActive ? COLORS.activeText : COLORS.textSecondary,
                background: isActive ? COLORS.activeBg : 'transparent',
                fontWeight: isActive ? 600 : 500,
                fontSize: 17,
                transition: 'background 0.15s ease, color 0.15s ease',
                position: 'relative',
              }}
              onMouseEnter={e => {
                if (!isActive) e.currentTarget.style.background = COLORS.hoverBg
              }}
              onMouseLeave={e => {
                if (!isActive) e.currentTarget.style.background = 'transparent'
              }}
            >
              {isActive && (
                <span style={{
                  position: 'absolute',
                  left: 0,
                  top: 8,
                  bottom: 8,
                  width: 3,
                  background: COLORS.activeBorder,
                  borderRadius: 2,
                }} />
              )}
              <Icon size={20} strokeWidth={isActive ? 2.25 : 1.75} />
              <span>{label}</span>
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}
