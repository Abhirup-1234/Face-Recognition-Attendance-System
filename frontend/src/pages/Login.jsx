import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async e => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await fetch('/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username, password }),
      })
      if (res.status === 429) {
        setError('Too many attempts. Please try again in a minute.')
        return
      }
      const data = await res.json().catch(() => ({}))
      if (data.ok) {
        onLogin?.()
        navigate('/', { replace: true })
      } else {
        setError(data.error || 'Invalid username or password.')
      }
    } catch {
      setError('Connection error. Is the server running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {/* Aurora runs here too — same blobs as the main app */}
      <div className="aurora" aria-hidden="true">
        <div className="aurora-orb aurora-blue" />
        <div className="aurora-orb aurora-orange" />
        <div className="aurora-orb aurora-green" />
      </div>

      <div className="login-wrap" style={{ position: 'relative', zIndex: 1 }}>
        <div className="login-card">

          {/* Logo + brand */}
          <div className="login-logo">
            <div className="login-logo-icon">👁</div>
            <div>
              <div className="login-brand">Face<span>Track</span> <span style={{ color: 'var(--text3)', fontSize: 13, fontWeight: 500 }}>AI</span></div>
              <div className="login-sub">Narula Public School Attendance System</div>
            </div>
          </div>

          {/* Divider */}
          <div style={{
            height: 1,
            background: 'linear-gradient(90deg, transparent, var(--border2), transparent)',
            marginBottom: 28,
          }} />

          {error && <div className="login-err" style={{ marginBottom: 20 }}>{error}</div>}

          <form className="login-form" onSubmit={handleSubmit}>
            <div className="login-field">
              <label htmlFor="username">Username</label>
              <input id="username" type="text" className="form-input"
                placeholder="Enter your username"
                value={username} onChange={e => setUsername(e.target.value)}
                autoComplete="username" required autoFocus />
            </div>
            <div className="login-field">
              <label htmlFor="password">Password</label>
              <input id="password" type="password" className="form-input"
                placeholder="Enter your password"
                value={password} onChange={e => setPassword(e.target.value)}
                autoComplete="current-password" required />
            </div>
            <button type="submit" className="login-btn" disabled={loading}>
              {loading
                ? <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}><span className="spin" style={{ borderTopColor: '#fff' }} /> Signing in...</span>
                : 'Sign In →'
              }
            </button>
          </form>

          <div className="login-footer">
            Enrich · Empower · Enlighten — Mogra
          </div>
        </div>
      </div>
    </>
  )
}
