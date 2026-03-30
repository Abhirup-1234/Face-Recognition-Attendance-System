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
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-logo">
          <div className="login-logo-icon">👁</div>
          <div>
            <div className="login-brand">Face<span>Track</span></div>
            <div className="login-sub">AI Attendance Management</div>
          </div>
        </div>

        {error && <div className="login-err" style={{ marginBottom: 16 }}>{error}</div>}

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="login-field">
            <label htmlFor="username">Username</label>
            <input
              id="username" type="text" className="form-input"
              placeholder="Enter username"
              value={username} onChange={e => setUsername(e.target.value)}
              autoComplete="username" required autoFocus
            />
          </div>
          <div className="login-field">
            <label htmlFor="password">Password</label>
            <input
              id="password" type="password" className="form-input"
              placeholder="Enter password"
              value={password} onChange={e => setPassword(e.target.value)}
              autoComplete="current-password" required
            />
          </div>
          <button type="submit" className="login-btn" disabled={loading}>
            {loading ? 'Signing in...' : 'Sign In →'}
          </button>
        </form>

        <div className="login-footer">FaceTrack AI — School Attendance System</div>
      </div>
    </div>
  )
}
