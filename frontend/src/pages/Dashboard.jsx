import { useState, useEffect, useCallback } from 'react'
import { useSocket } from '../context/SocketContext'
import { stats as statsApi } from '../api'

function initials(name) {
  return String(name || 'XX').split(' ').map(w => w[0] || '').join('').slice(0, 2).toUpperCase()
}

export default function Dashboard() {
  const [data,    setData]    = useState(null)
  const [feed,    setFeed]    = useState([])
  const [loading, setLoading] = useState(true)
  const { socket } = useSocket()

  const loadStats = useCallback(async () => {
    const res = await statsApi.get()
    if (res?.ok) setData(res.data)
    setLoading(false)
  }, [])

  useEffect(() => {
    loadStats()
    const id = setInterval(loadStats, 5000)
    return () => clearInterval(id)
  }, [loadStats])

  useEffect(() => {
    if (!socket) return
    const handler = event => {
      setFeed(prev => [event, ...prev].slice(0, 50))
    }
    socket.on('attendance_marked', handler)
    return () => socket.off('attendance_marked', handler)
  }, [socket])

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data)   return <div className="empty"><div className="empty-title">No data</div></div>

  const classes  = data.daily?.classes || []
  const cameras  = data.cameras || {}
  const enrolled = data.enrolled || 0
  const totalP   = classes.reduce((a, c) => a + (c.present || 0), 0)
  const totalT   = classes.reduce((a, c) => a + (c.total   || 0), 0)
  const totalA   = totalT - totalP
  const pct      = totalT > 0 ? Math.round(totalP / totalT * 100 * 10) / 10 : 0

  return (
    <div>
      {/* KPI row */}
      <div className="g4" style={{ marginBottom: 20 }}>
        <div className="statcard sc-blue">
          <div className="stat-label">Present Today</div>
          <div className="stat-value">{totalP}</div>
          <div className="stat-sub">of {totalT} enrolled</div>
          <div className="stat-icon">👥</div>
        </div>
        <div className="statcard sc-red">
          <div className="stat-label">Absent Today</div>
          <div className="stat-value">{totalA}</div>
          <div className="stat-sub">{Math.round((100 - pct) * 10) / 10}% absent rate</div>
          <div className="stat-icon">✗</div>
        </div>
        <div className="statcard sc-green">
          <div className="stat-label">Attendance Rate</div>
          <div className="stat-value">{pct}%</div>
          <div className="stat-sub">school-wide today</div>
          <div className="stat-icon">📈</div>
        </div>
        <div className="statcard sc-orange">
          <div className="stat-label">Active Cameras</div>
          <div className="stat-value">{Object.keys(cameras).length}</div>
          <div className="stat-sub">monitoring classrooms</div>
          <div className="stat-icon">📷</div>
        </div>
      </div>

      <div className="g2" style={{ gap: 20 }}>
        {/* Class breakdown */}
        <div className="card">
          <div className="card-title"><span className="card-icon">▦</span> Class Breakdown</div>
          {classes.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">📋</div>
              <div className="empty-title">No data yet</div>
              <div className="empty-sub">Enroll students and start a camera.</div>
            </div>
          ) : (
            classes.map(cls => (
              <div key={cls.class_name} style={{ marginBottom: 14 }}>
                <div className="flex-sb" style={{ marginBottom: 6 }}>
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{cls.class_name}</span>
                  <span style={{ fontSize: 12, color: 'var(--text3)', fontFamily: 'Space Mono, monospace' }}>
                    {cls.present}/{cls.total}
                    <span
                      className={`badge ${cls.percentage >= 75 ? 'badge-green' : cls.percentage >= 50 ? 'badge-yellow' : 'badge-red'}`}
                      style={{ marginLeft: 6 }}
                    >
                      {cls.percentage}%
                    </span>
                  </span>
                </div>
                <div className="pbar-wrap">
                  <div className="pbar" style={{ width: `${cls.percentage}%` }} />
                </div>
              </div>
            ))
          )}
        </div>

        {/* Live activity */}
        <div className="card">
          <div className="card-title">
            <span className="card-icon">⊕</span>
            Live Activity
            <span className="sdot green" style={{ marginLeft: 4 }} />
            <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'Space Mono, monospace' }}>LIVE</span>
          </div>
          <div className="log-list" style={{ maxHeight: 360, overflowY: 'auto' }}>
            {feed.length === 0 ? (
              <div className="empty">
                <div className="empty-icon">📷</div>
                <div className="empty-title">No detections yet</div>
                <div className="empty-sub">Waiting for camera activity...</div>
              </div>
            ) : (
              feed.map((r, i) => (
                <div key={i} className="log-item">
                  <div className="log-av">{initials(r.student_name)}</div>
                  <div className="log-info">
                    <div className="log-name">{r.student_name || 'Unknown'}</div>
                    <div className="log-time">{r.camera_id} · {r.timestamp}</div>
                  </div>
                  <span className="badge badge-green mono">{(r.confidence || 0).toFixed(3)}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Camera status */}
      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-title"><span className="card-icon">◊</span> Camera Status</div>
        {Object.keys(cameras).length === 0 ? (
          <div className="muted">No cameras configured. Edit CAMERAS in config.py.</div>
        ) : (
          <div className="g3" style={{ gap: 12 }}>
            {Object.entries(cameras).map(([camId, s]) => (
              <div
                key={camId}
                style={{
                  background: 'var(--bg3)',
                  border: `1px solid ${s.status === 'running' ? 'rgba(16,185,129,.3)' : s.status === 'error' ? 'rgba(239,68,68,.3)' : 'var(--border)'}`,
                  borderRadius: 'var(--radius-sm)',
                  padding: 14,
                }}
              >
                <div className="flex-sb" style={{ marginBottom: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{camId}</span>
                  <span className={`sdot ${s.status === 'running' ? 'green' : s.status === 'error' ? 'red' : 'yellow'}`} />
                </div>
                <div style={{ fontSize: 12, color: 'var(--secondary)', fontFamily: 'Space Mono, monospace' }}>
                  Capture: {s.capture_fps || 0} fps
                </div>
                <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>
                  Stream: {s.stream_fps || 0} fps
                </div>
                <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>
                  {s.faces_detected || 0} face(s) in frame
                </div>
                <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>
                  {s.recognitions_today || 0} marked today
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
