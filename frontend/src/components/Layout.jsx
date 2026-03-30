import { useState, useEffect, useCallback } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useSocket } from '../context/SocketContext'

// Inline SVG badge — no external image dependency, works completely offline.
// Replace with <img src="/nps-logo.png" .../> if you add a real logo to public/.
function NPSBadge() {
  return (
    <svg
      width="24" height="24" viewBox="0 0 24 24"
      fill="none" xmlns="http://www.w3.org/2000/svg"
      style={{ flexShrink: 0 }}
    >
      <defs>
        <linearGradient id="nps-g" x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#4f46e5" />
          <stop offset="100%" stopColor="#06b6d4" />
        </linearGradient>
      </defs>
      {/* Shield shape */}
      <path
        d="M12 2L3 6v6c0 5.25 3.9 10.15 9 11.35C17.1 22.15 21 17.25 21 12V6L12 2z"
        fill="url(#nps-g)"
      />
      {/* NPS text */}
      <text
        x="12" y="15"
        textAnchor="middle"
        fill="white"
        fontSize="6.5"
        fontWeight="800"
        fontFamily="'Sora', 'Segoe UI', sans-serif"
        letterSpacing="0.3"
      >
        NPS
      </text>
    </svg>
  )
}

const NAV = [
  { to: '/',         icon: '⬡', label: 'Dashboard',          section: 'Main'    },
  { to: '/cameras',  icon: '⊕', label: 'Live Cameras',       section: 'Main'    },
  { to: '/enroll',   icon: '◊', label: 'Enroll Students',    section: 'Main'    },
  { to: '/reports',  icon: '▦', label: 'Attendance Records', section: 'Reports' },
  { to: '/manage',   icon: '⌾', label: 'Manage',             section: 'System'  },
  { to: '/settings', icon: '⚙', label: 'Settings',           section: 'System'  },
]

const PAGE_TITLES = {
  '/':         'Dashboard',
  '/cameras':  'Live Cameras',
  '/enroll':   'Enroll Students',
  '/reports':  'Attendance Records',
  '/manage':   'Manage',
  '/settings': 'Settings',
}

export default function Layout({ children, enrolledCount = 0 }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [clock, setClock] = useState('')
  const [date,  setDate]  = useState('')
  const { connected } = useSocket()
  const navigate = useNavigate()

  // Clock
  useEffect(() => {
    function tick() {
      const now = new Date()
      setClock(now.toLocaleTimeString('en-IN', { hour12: false }))
      setDate(now.toLocaleDateString('en-IN', {
        weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
      }))
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  const closeOverlay = useCallback(() => setSidebarOpen(false), [])
  const onNavClick   = useCallback(() => {
    if (window.innerWidth <= 900) setSidebarOpen(false)
  }, [])

  const pageTitle = PAGE_TITLES[location.pathname] || 'FaceTrack AI'
  const sections  = ['Main', 'Reports', 'System']

  const handleLogout = async () => {
    await fetch('/logout', { credentials: 'include' })
    window.location.href = '/login'
  }

  return (
    <div className="app-shell">

      {/* ── Sidebar ─────────────────────────────────────────────────────────── */}
      <nav className={`sidebar${sidebarOpen ? ' open' : ''}`}>
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">👁</div>
          <div className="sidebar-logo-text">Face<span>Track</span></div>
        </div>

        {sections.map(section => {
          const items = NAV.filter(n => n.section === section)
          return (
            <div key={section}>
              <div className="sidebar-label" style={{ marginTop: section !== 'Main' ? 16 : 0 }}>
                {section}
              </div>
              {items.map(item => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
                  onClick={onNavClick}
                >
                  <span className="nav-icon">{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
            </div>
          )
        })}

        <div className="sidebar-spacer" />

        {/* System status */}
        <div className="sidebar-status">
          <div className="flex" style={{ marginBottom: 6 }}>
            <span className={`sdot ${connected ? 'green' : 'yellow'}`} />
            <span className="status-text">
              {connected ? 'System Live' : 'Connecting...'}
            </span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text3)' }}>
            {enrolledCount} student(s) enrolled
          </div>
        </div>

        {/* Logout */}
        <button
          onClick={handleLogout}
          style={{
            display: 'flex', alignItems: 'center', gap: 9,
            padding: '9px 12px', borderRadius: 'var(--radius-sm)',
            color: 'var(--text3)', background: 'none',
            border: '1px solid var(--border)', cursor: 'pointer',
            fontSize: 13, fontWeight: 500, marginTop: 6, width: '100%',
            fontFamily: "'Sora', sans-serif", transition: 'all .18s',
          }}
          onMouseOver={e => {
            e.currentTarget.style.borderColor = 'var(--danger)'
            e.currentTarget.style.color = 'var(--danger)'
          }}
          onMouseOut={e => {
            e.currentTarget.style.borderColor = 'var(--border)'
            e.currentTarget.style.color = 'var(--text3)'
          }}
        >
          ⇒ Logout
        </button>

        {/* ── School credits footer ────────────────────────────────────────── */}
        <div className="sidebar-credits">
          <div className="credits-school">
            <NPSBadge />
            <span className="credits-name">Narula Public School</span>
          </div>
          <div className="credits-sub">
            Developed by Abhirup<br />
            © 2026 All rights reserved
          </div>
        </div>
      </nav>

      {/* Overlay (mobile) */}
      <div
        className={`sb-overlay${sidebarOpen ? ' active' : ''}`}
        onClick={closeOverlay}
      />

      {/* ── Main content ─────────────────────────────────────────────────────── */}
      <div className="main-area">
        <header className="header">
          <button className="hburger" onClick={() => setSidebarOpen(o => !o)}>☰</button>
          <div style={{ flex: 1 }}>
            <div className="header-title">{pageTitle}</div>
            <div className="header-date">{date}</div>
          </div>
          <div className="header-actions">
            <span className="clock">{clock}</span>
          </div>
        </header>

        <div className="page-content">
          <div className="page-enter">{children}</div>
        </div>
      </div>
    </div>
  )
}
