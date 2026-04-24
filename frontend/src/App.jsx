import { useState, useEffect, useCallback } from 'react'
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useSocket } from './context/SocketContext'
import Layout    from './components/Layout'
import Login     from './pages/Login'
import Dashboard from './pages/Dashboard'
import Cameras   from './pages/Cameras'
import Enroll    from './pages/Enroll'
import Reports   from './pages/Reports'
import Manage    from './pages/Manage'
import Settings  from './pages/Settings'

// Auth states
const AUTH = { CHECKING: 'checking', IN: 'in', OUT: 'out' }

export default function App() {
  const [auth,     setAuth]     = useState(AUTH.CHECKING)
  const [enrolled, setEnrolled] = useState(0)
  const location  = useLocation()
  const { socket } = useSocket()

  // Check auth on mount and on navigation
  useEffect(() => {
    let cancelled = false
    fetch('/api/auth/status', { credentials: 'include' })
      .then(r => r.json())
      .then(d => {
        if (cancelled) return
        setAuth(d.logged_in ? AUTH.IN : AUTH.OUT)
        setEnrolled(d.enrolled || 0)
      })
      .catch(() => { if (!cancelled) setAuth(AUTH.OUT) })
    return () => { cancelled = true }
  }, [location.pathname])

  // Listen for live enrollment count updates via socket
  useEffect(() => {
    if (!socket) return
    const handler = (data) => setEnrolled(data.count ?? 0)
    socket.on('enrolled_count', handler)
    return () => socket.off('enrolled_count', handler)
  }, [socket])

  // Called by EnrollQueueProvider when a student is enrolled successfully
  const handleEnrolled = useCallback(() => {
    setEnrolled(n => n + 1)
  }, [])

  // Loading spinner while checking
  if (auth === AUTH.CHECKING) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: 'var(--bg)' }}>
        <span className="spin" />
      </div>
    )
  }

  // Not logged in — show login page
  if (auth === AUTH.OUT) {
    return (
      <Routes>
        <Route path="/login" element={<Login onLogin={() => setAuth(AUTH.IN)} />} />
        <Route path="*"      element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  // Logged in — redirect away from /login
  if (location.pathname === '/login') {
    return <Navigate to="/" replace />
  }

  // Main SPA
  return (
    <Layout enrolledCount={enrolled} onEnrolled={handleEnrolled}>
      <Routes>
        <Route path="/"         element={<Dashboard />} />
        <Route path="/cameras"  element={<Cameras />} />
        <Route path="/enroll"   element={<Enroll />} />
        <Route path="/reports"  element={<Reports />} />
        <Route path="/manage"   element={<Manage />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*"         element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
