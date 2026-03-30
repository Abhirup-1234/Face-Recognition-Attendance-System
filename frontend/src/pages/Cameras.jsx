import { useState, useEffect, useRef, useCallback } from 'react'
import { useSocket } from '../context/SocketContext'
import { cameras as camerasApi } from '../api'

function initials(name) {
  return String(name || 'XX').split(' ').map(w => w[0] || '').join('').slice(0, 2).toUpperCase()
}

// Snapshot poller component — avoids Chrome loading spinner
function CameraFeed({ camId }) {
  const imgRef      = useRef(null)
  const timerRef    = useRef(null)
  const [err, setErr] = useState(false)

  const poll = useCallback(() => {
    const img = new Image()
    img.onload = () => {
      if (imgRef.current) {
        imgRef.current.src = img.src
        imgRef.current.style.display = ''
      }
      setErr(false)
      timerRef.current = setTimeout(poll, 100)
    }
    img.onerror = () => {
      setErr(true)
      timerRef.current = setTimeout(poll, 2000)
    }
    img.src = `/snapshot/${camId}?t=${Date.now()}`
  }, [camId])

  useEffect(() => {
    poll()
    return () => clearTimeout(timerRef.current)
  }, [poll])

  return (
    <div className="vidbox" style={{ borderRadius: 0, border: 'none' }}>
      <img
        ref={imgRef}
        alt={`Camera ${camId}`}
        style={{ width: '100%', height: '100%', objectFit: 'contain', display: err ? 'none' : 'block' }}
      />
      {err && (
        <div className="vid-err">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" width="52" opacity=".3">
            <path d="M23 7l-7 5 7 5V7z" />
            <rect x="1" y="5" width="15" height="14" rx="2" />
          </svg>
          <span>Stream unavailable</span>
        </div>
      )}
    </div>
  )
}

export default function Cameras() {
  const [camStats, setCamStats] = useState({})
  const [feed,     setFeed]     = useState([])
  const [camIds,   setCamIds]   = useState([])
  const { socket } = useSocket()

  const loadStats = useCallback(async () => {
    const res = await camerasApi.stats()
    if (res?.ok) {
      setCamStats(res.data)
      setCamIds(Object.keys(res.data))
    }
  }, [])

  useEffect(() => {
    loadStats()
    const id = setInterval(loadStats, 5000)
    return () => clearInterval(id)
  }, [loadStats])

  useEffect(() => {
    if (!socket) return
    const handler = event => setFeed(prev => [event, ...prev].slice(0, 60))
    socket.on('attendance_marked', handler)
    return () => socket.off('attendance_marked', handler)
  }, [socket])

  const camAction = useCallback(async (camId, action) => {
    if (action === 'start')   await camerasApi.start(camId)
    if (action === 'stop')    await camerasApi.stop(camId)
    if (action === 'restart') await camerasApi.restart(camId)
    setTimeout(loadStats, 1500)
  }, [loadStats])

  if (camIds.length === 0) {
    return (
      <div className="card">
        <div className="empty">
          <div className="empty-icon">📷</div>
          <div className="empty-title">No cameras configured</div>
          <div className="empty-sub">Edit CAMERAS in config.py to add camera sources.</div>
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 20 }}>
      {/* Camera feeds */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {camIds.map(camId => {
          const s = camStats[camId] || {}
          const running = s.status === 'running'

          return (
            <div key={camId} className="card" style={{ padding: 0, overflow: 'hidden' }}>
              {/* Header */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
                <div className="flex">
                  <span style={{ fontSize: 14, fontWeight: 700 }}>{camId}</span>
                  <span className={`sdot ${running ? 'green' : s.status === 'error' ? 'red' : 'yellow'}`} />
                  <span style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'Space Mono, monospace' }}>
                    {running ? 'LIVE' : (s.status || 'STOPPED').toUpperCase()}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {!running && (
                    <button className="btn btn-ghost btn-sm" onClick={() => camAction(camId, 'start')}>
                      ▶ Start
                    </button>
                  )}
                  {running && (
                    <button className="btn btn-ghost btn-sm" onClick={() => camAction(camId, 'stop')}>
                      ■ Stop
                    </button>
                  )}
                  <button className="btn btn-ghost btn-sm" onClick={() => camAction(camId, 'restart')}>
                    ↺ Restart
                  </button>
                </div>
              </div>

              {/* Video */}
              <CameraFeed camId={camId} />

              {/* Footer stats */}
              <div style={{ padding: '10px 16px', background: 'var(--bg2)', display: 'flex', gap: 16, fontSize: 12, fontFamily: 'Space Mono, monospace', color: 'var(--text3)' }}>
                <span>Capture: {s.capture_fps || 0} fps</span>
                <span>Stream: {s.stream_fps || 0} fps</span>
                <span>{s.faces_detected || 0} face(s)</span>
                <span>{s.status || 'stopped'}</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Live detections sidebar */}
      <div className="card" style={{ alignSelf: 'start', position: 'sticky', top: 80 }}>
        <div className="card-title">
          <span className="card-icon">⊕</span>
          Detections
          <span className="sdot green" style={{ marginLeft: 4 }} />
        </div>
        <div className="log-list" style={{ maxHeight: 520, overflowY: 'auto' }}>
          {feed.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">📷</div>
              <div className="empty-title">Waiting...</div>
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
  )
}
