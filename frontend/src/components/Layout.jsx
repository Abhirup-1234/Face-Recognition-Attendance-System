import { useState, useEffect, useCallback } from 'react'
import { NavLink } from 'react-router-dom'
import { useSocket } from '../context/SocketContext'

const NPS_LOGO = 'data:image/png;base64,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'

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

      {/* ── Aurora background — blobs travel slowly across the full screen */}
      <div className="aurora" aria-hidden="true">
        <div className="aurora-orb aurora-blue" />
        <div className="aurora-orb aurora-orange" />
        <div className="aurora-orb aurora-green" />
        <div className="aurora-orb aurora-purple" />
      </div>

      {/* ── Sidebar */}
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
                  key={item.to} to={item.to} end={item.to === '/'}
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

        <div className="sidebar-status">
          <div className="flex" style={{ marginBottom: 6 }}>
            <span className={`sdot ${connected ? 'green' : 'yellow'}`} />
            <span className="status-text">{connected ? 'System Live' : 'Connecting...'}</span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text3)' }}>
            {enrolledCount} student(s) enrolled
          </div>
        </div>

        <button onClick={handleLogout} style={{
          display: 'flex', alignItems: 'center', gap: 9,
          padding: '9px 12px', borderRadius: 'var(--radius-sm)',
          color: 'var(--text3)', background: 'rgba(255,255,255,.03)',
          border: '1px solid var(--border)', cursor: 'pointer',
          fontSize: 13, fontWeight: 600, marginTop: 8, width: '100%',
          fontFamily: "'Sora', sans-serif", transition: 'all .2s',
          backdropFilter: 'blur(8px)',
        }}
          onMouseOver={e => {
            e.currentTarget.style.borderColor = 'rgba(239,68,68,.5)'
            e.currentTarget.style.color = '#f87171'
            e.currentTarget.style.background = 'rgba(239,68,68,.08)'
          }}
          onMouseOut={e => {
            e.currentTarget.style.borderColor = 'var(--border)'
            e.currentTarget.style.color = 'var(--text3)'
            e.currentTarget.style.background = 'rgba(255,255,255,.03)'
          }}
        >
          ⇒ Logout
        </button>

        <div className="sidebar-credits">
          <div className="credits-school">
            <img src={NPS_LOGO} alt="NPS" className="credits-logo" />
            <span className="credits-name">Narula Public School</span>
          </div>
          <div className="credits-sub">
            Developed by Abhirup<br />© 2026 All rights reserved
          </div>
        </div>
      </nav>

      <div className={`sb-overlay${sidebarOpen ? ' active' : ''}`} onClick={closeOverlay} />

      {/* ── Main content */}
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
