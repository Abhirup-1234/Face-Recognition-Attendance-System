import { useState, useEffect, useCallback } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useSocket } from '../context/SocketContext'

// NPS logo embedded as base64 - works completely offline
const NPS_LOGO = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAABCGlDQ1BJQ0MgUHJvZmlsZQAAeJxjYGA8wQAELAYMDLl5JUVB7k4KEZFRCuwPGBiBEAwSk4sLGHADoKpv1yBqL+viUYcLcKakFicD6Q9ArFIEtBxopAiQLZIOYWuA2EkQtg2IXV5SUAJkB4DYRSFBzkB2CpCtkY7ETkJiJxcUgdT3ANk2uTmlyQh3M/Ck5oUGA2kOIJZhKGYIYnBncAL5H6IkfxEDg8VXBgbmCQixpJkMDNtbGRgkbiHEVBYwMPC3MDBsO48QQ4RJQWJRIliIBYiZ0tIYGD4tZ2DgjWRgEL7AwMAVDQsIHG5TALvNnSEfCNMZchhSgSKeDHkMyQx6QJYRgwGDIYMZAKbWPz9HbOBQAAAP30lEQVR42u2ZeZRU1Z3HP/cttXdV9b5A09C0zdLsIJuBZlEkoCYmKZLoxKCT0cm4RI0RMc4pW3PMqjPRcY7RmSRmNTTGrRXFBRpFWVoElKbZoYGm964u272/qlJ3/O69qNICoiI55x+/c06q6la98rv3d3/fJr9QgqREREQAAA=='

const NAV = [
  { to: '/',         icon: '⬡', label: 'Dashboard',         section: 'Main' },
  { to: '/cameras',  icon: '⊕', label: 'Live Cameras',      section: 'Main' },
  { to: '/enroll',   icon: '◊', label: 'Enroll Students',   section: 'Main' },
  { to: '/reports',  icon: '▦', label: 'Attendance Records',section: 'Reports' },
  { to: '/manage',   icon: '⌾', label: 'Manage',            section: 'System' },
  { to: '/settings', icon: '⚙', label: 'Settings',          section: 'System' },
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
      setDate(now.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }))
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  // Close sidebar when clicking outside
  const closeOverlay = useCallback(() => setSidebarOpen(false), [])

  // Close sidebar on nav click (mobile)
  const onNavClick = useCallback(() => {
    if (window.innerWidth <= 900) setSidebarOpen(false)
  }, [])

  // Current page title
  const pageTitle = PAGE_TITLES[location.pathname] || 'FaceTrack AI'

  // Group nav items by section
  const sections = ['Main', 'Reports', 'System']

  const handleLogout = async () => {
    await fetch('/logout', { credentials: 'include' })
    window.location.href = '/login'
  }

  return (
    <div className="app-shell">
      {/* Sidebar */}
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

        <div className="sidebar-status">
          <div className="flex" style={{ marginBottom: 6 }}>
            <span className={`sdot ${connected ? 'green' : 'yellow'}`} />
            <span className="status-text">{connected ? 'System Live' : 'Connecting...'}</span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text3)' }}>
            {enrolledCount} student(s) enrolled
          </div>
        </div>

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
          onMouseOver={e => { e.currentTarget.style.borderColor = 'var(--danger)'; e.currentTarget.style.color = 'var(--danger)' }}
          onMouseOut={e  => { e.currentTarget.style.borderColor = 'var(--border)';  e.currentTarget.style.color = 'var(--text3)' }}
        >
          ⇒ Logout
        </button>

        {/* Credits footer */}
        <div className="sidebar-credits">
          <div className="credits-school">
            <img src={NPS_LOGO} alt="NPS" className="credits-logo" />
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

      {/* Main content */}
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
