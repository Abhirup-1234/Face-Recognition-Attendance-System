import { useState, useEffect, useCallback } from 'react'
import { useSocket } from '../context/SocketContext'
import { stats as statsApi } from '../api'
import { initials } from '../utils'

const CONTENT_HEIGHT = 196   // matches .empty placeholder height exactly

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
    const handler = event => setFeed(prev => [event, ...prev].slice(0, 50))
    socket.on('attendance_marked', handler)
    return () => socket.off('attendance_marked', handler)
  }, [socket])

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data)   return <div className="empty"><div className="empty-title">No data</div></div>

  const classes = data.daily?.classes || []
  const cameras = data.cameras || {}
  const totalP  = classes.reduce((a, c) => a + (c.present || 0), 0)
  const totalT  = classes.reduce((a, c) => a + (c.total   || 0), 0)
  const totalA  = totalT - totalP
  const pct     = totalT > 0 ? Math.round(totalP / totalT * 100 * 10) / 10 : 0

  return (
    <div>
      {/* ── KPI stat cards ──────────────────────────────────────────────────── */}
      <div className="g4" style={{ marginBottom: 22 }}>

        <div className="statcard sc-blue">
          <div className="stat-label">Present Today</div>
          <div className="stat-value">{totalP}</div>
          <div className="stat-sub">of {totalT} enrolled</div>
          <div className="stat-icon">🎓</div>
        </div>

        <div className="statcard sc-orange">
          <div className="stat-label">Absent Today</div>
          <div className="stat-value">{totalA}</div>
          <div className="stat-sub">{Math.round((100 - pct) * 10) / 10}% absent rate</div>
          <div className="stat-icon">📋</div>
        </div>

        <div className="statcard sc-green">
          <div className="stat-label">Attendance Rate</div>
          <div className="stat-value">{pct}%</div>
          <div className="stat-sub">school-wide today</div>
          <div className="stat-icon">📈</div>
        </div>

        <div className="statcard sc-yellow">
          <div className="stat-label">Active Cameras</div>
          <div className="stat-value">{Object.keys(cameras).length}</div>
          <div className="stat-sub">monitoring classrooms</div>
          <div className="stat-icon">🎥</div>
        </div>
      </div>

      {/* ── Class breakdown + Live activity ─────────────────────────────────── */}
      <div className="g2" style={{ gap: 20, alignItems: 'start' }}>

        <div className="card">
          <div className="card-title">
            <span className="card-icon">▦</span> Class Breakdown
          </div>
          <div style={{ maxHeight: CONTENT_HEIGHT, overflowY: 'auto' }}>
            {classes.length === 0 ? (
              <div className="empty">
                <div className="empty-icon">📋</div>
                <div className="empty-title">No data yet</div>
                <div className="empty-sub">Enroll students and start a camera.</div>
              </div>
            ) : (
              classes.map(cls => (
                <div key={cls.class_name} style={{ marginBottom: 16 }}>
                  <div className="flex-sb" style={{ marginBottom: 7 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>
                      {cls.class_name}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 12, color: 'var(--text3)', fontFamily: 'Space Mono, monospace' }}>
                        {cls.present}/{cls.total}
                      </span>
                      <span className={`badge ${
                        cls.percentage >= 75 ? 'badge-green' :
                        cls.percentage >= 50 ? 'badge-yellow' : 'badge-red'
                      }`}>
                        {cls.percentage}%
                      </span>
                    </div>
                  </div>
                  <div className="pbar-wrap">
                    <div className="pbar" style={{ width: `${cls.percentage}%` }} />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-title">
            <span className="card-icon">⊕</span>
            Live Activity
            <span className="sdot green" style={{ marginLeft: 2 }} />
            <span style={{ fontSize: 10.5, color: 'var(--text3)', fontFamily: 'Space Mono, monospace', letterSpacing: '.5px' }}>LIVE</span>
          </div>
          <div style={{ maxHeight: CONTENT_HEIGHT, overflowY: 'auto' }}>
            {feed.length === 0 ? (
              <div className="empty">
                <div className="empty-icon">📷</div>
                <div className="empty-title">No detections yet</div>
                <div className="empty-sub">Waiting for camera activity...</div>
              </div>
            ) : (
              <div className="log-list">
                {feed.map((r, i) => (
                  <div key={i} className="log-item">
                    <div className="log-av">{initials(r.student_name)}</div>
                    <div className="log-info">
                      <div className="log-name">{r.student_name || 'Unknown'}</div>
                      <div className="log-time">{r.camera_id} · {r.timestamp}</div>
                    </div>
                    <span className="badge badge-green mono">
                      {(r.confidence || 0).toFixed(3)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Camera status ───────────────────────────────────────────────────── */}
      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-title"><span className="card-icon">◊</span> Camera Status</div>
        {Object.keys(cameras).length === 0 ? (
          <div className="muted">No cameras configured. Edit CAMERAS in config.py.</div>
        ) : (
          <div className="g3" style={{ gap: 14 }}>
            {Object.entries(cameras).map(([camId, s]) => {
              const isRunning = s.status === 'running'
              const isError   = s.status === 'error'
              return (
                <div key={camId} style={{
                  background: 'rgba(255,255,255,.025)',
                  border: `1px solid ${isRunning ? 'rgba(22,163,74,.3)' : isError ? 'rgba(239,68,68,.3)' : 'var(--border)'}`,
                  borderRadius: 'var(--radius-sm)',
                  padding: '14px 16px',
                  backdropFilter: 'blur(8px)',
                  transition: 'border-color .2s, box-shadow .2s',
                  boxShadow: isRunning ? '0 0 20px rgba(22,163,74,.07)' : 'none',
                }}>
                  <div className="flex-sb" style={{ marginBottom: 10 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, fontFamily: 'Space Mono, monospace', color: 'var(--text)' }}>
                      {camId}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span className={`sdot ${isRunning ? 'green' : isError ? 'red' : 'yellow'}`} />
                      <span style={{ fontSize: 10.5, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.5px' }}>
                        {s.status || 'stopped'}
                      </span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {[
                      ['Capture', `${s.capture_fps || 0} fps`, 'var(--secondary)'],
                      ['Stream',  `${s.stream_fps  || 0} fps`, 'var(--text2)'],
                      ['Faces',   `${s.faces_detected || 0} in frame`, 'var(--text2)'],
                      ['Marked',  `${s.recognitions_today || 0} today`, '#4ade80'],
                    ].map(([label, val, col]) => (
                      <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                        <span style={{ color: 'var(--text3)' }}>{label}</span>
                        <span style={{ color: col, fontFamily: 'Space Mono, monospace', fontWeight: 600 }}>{val}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
