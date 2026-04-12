import { useState, useEffect, useCallback, useRef } from 'react'
import { useSocket } from '../context/SocketContext'
import { cameras as camerasApi } from '../api'
import { initials } from '../utils'

// Snapshot poller — avoids Chrome loading spinner
function CameraFeed({ camId }) {
  const imgRef   = useRef(null)
  const timerRef = useRef(null)
  const [err, setErr] = useState(false)

  const poll = useCallback(() => {
    const img = new Image()
    img.onload = () => {
      if (imgRef.current) { imgRef.current.src = img.src; imgRef.current.style.display = '' }
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
    <div className="vidbox" style={{ borderRadius:0, border:'none' }}>
      <img ref={imgRef} alt={`Camera ${camId}`}
        style={{ width:'100%', height:'100%', objectFit:'contain',
                 display: err ? 'none' : 'block' }} />
      {err && (
        <div className="vid-err">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" width="52" opacity=".3">
            <path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/>
          </svg>
          <span>Stream unavailable</span>
        </div>
      )}
    </div>
  )
}

function ColabPushCameraFeed({ camId }) {
  const vidRef = useRef(null)
  const ovlRef = useRef(null)
  const capRef = useRef(null)
  const runRef = useRef(false)
  const timerRef = useRef(null)
  const [err, setErr] = useState('')
  const [inferenceMs, setInferenceMs] = useState(null)
  const [facesCount, setFacesCount] = useState(0)

  const drawFaces = useCallback((faces) => {
    const canvas = ovlRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const w = canvas.width
    const h = canvas.height
    ctx.clearRect(0, 0, w, h)
    for (const f of faces || []) {
      const [x, y, bw, bh] = f.bbox || [0, 0, 0, 0]
      const col = f.known ? '#3fb950' : '#f85149'
      const pct = f.similarity ? ` ${Math.round(f.similarity * 100)}%` : ''
      const label = `${f.name || 'Unknown'}${pct}`
      ctx.strokeStyle = col
      ctx.lineWidth = 2
      ctx.strokeRect(x, y, bw, bh)
      ctx.font = 'bold 13px system-ui'
      const tw = ctx.measureText(label).width
      ctx.fillStyle = col
      ctx.fillRect(x, Math.max(0, y - 22), tw + 10, 22)
      ctx.fillStyle = '#0d1117'
      ctx.fillText(label, x + 5, Math.max(14, y - 6))
    }
  }, [])

  useEffect(() => {
    runRef.current = true
    const TARGET_PREVIEW_FPS = 15
    const TARGET_CYCLE_MS = Math.round(1000 / TARGET_PREVIEW_FPS)

    const sendFrame = async () => {
      if (!runRef.current) return
      const vid = vidRef.current
      const cap = capRef.current
      if (!vid || !cap || vid.readyState < 2) {
        timerRef.current = setTimeout(sendFrame, 120)
        return
      }
      const cctx = cap.getContext('2d')
      cctx.drawImage(vid, 0, 0, cap.width, cap.height)
      const t0 = performance.now()
      cap.toBlob(async (blob) => {
        if (!runRef.current || !blob) return
        try {
          const resp = await fetch(`/api/preview_frame/${encodeURIComponent(camId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/octet-stream' },
            body: blob,
            credentials: 'include',
          })
          if (resp.ok) {
            const data = await resp.json()
            const faces = data.faces || []
            drawFaces(faces)
            setFacesCount(faces.length)
            setInferenceMs(data.inference_ms ?? null)
            setErr('')
          } else {
            setErr(`Preview failed (${resp.status})`)
          }
        } catch {
          setErr('Preview request failed')
        }
        const rtt = performance.now() - t0
        timerRef.current = setTimeout(sendFrame, Math.max(1, TARGET_CYCLE_MS - rtt))
      }, 'image/jpeg', 0.70)
    }

    const start = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 640 },
            height: { ideal: 480 },
            facingMode: 'user',
            frameRate: { ideal: 30, max: 30 },
          },
        })
        if (!runRef.current) {
          stream.getTracks().forEach(t => t.stop())
          return
        }
        const vid = vidRef.current
        if (!vid) return
        vid.srcObject = stream
        setErr('')
        await vid.play().catch(() => {})
        sendFrame()
      } catch (e) {
        setErr(e?.message || 'Camera access denied')
      }
    }

    start()
    return () => {
      runRef.current = false
      if (timerRef.current) clearTimeout(timerRef.current)
      const vid = vidRef.current
      if (vid && vid.srcObject) {
        vid.srcObject.getTracks().forEach(t => t.stop())
        vid.srcObject = null
      }
    }
  }, [camId, drawFaces])

  return (
    <div className="vidbox camera-live-box" style={{ borderRadius: 0, border: 'none' }}>
      <video ref={vidRef} className="camera-live-video" autoPlay muted playsInline />
      <canvas ref={ovlRef} className="camera-live-ovl" width={640} height={480} />
      <canvas ref={capRef} width={640} height={480} style={{ display: 'none' }} />
      <div className="camera-live-metrics">
        <span>Faces: {facesCount}</span>
        <span>Inference: {inferenceMs == null ? '—' : `${inferenceMs} ms`}</span>
      </div>
      {err && <div className="camera-live-err">{err}</div>}
    </div>
  )
}

export default function Cameras() {
  const [camStats, setCamStats] = useState({})
  const [feed,     setFeed]     = useState([])
  const [camIds,   setCamIds]   = useState([])
  const [toggling, setToggling] = useState({})   // camId → bool (pending)
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
    const onAttendance = event => setFeed(prev => [event, ...prev].slice(0, 60))
    const onCamStatus  = ({ camera_id, status }) => {
      setCamStats(prev => ({
        ...prev,
        [camera_id]: { ...(prev[camera_id] || {}), status },
      }))
    }
    socket.on('attendance_marked', onAttendance)
    socket.on('camera_status',     onCamStatus)
    return () => {
      socket.off('attendance_marked', onAttendance)
      socket.off('camera_status',     onCamStatus)
    }
  }, [socket])

  const camAction = useCallback(async (camId, action) => {
    if (action === 'start')   await camerasApi.start(camId)
    if (action === 'stop')    await camerasApi.stop(camId)
    if (action === 'restart') await camerasApi.restart(camId)
    setTimeout(loadStats, 1500)
  }, [loadStats])

  const toggleRecognition = useCallback(async (camId, currentlyOn) => {
    setToggling(p => ({ ...p, [camId]: true }))
    await camerasApi.recognition(camId, !currentlyOn)
    await loadStats()
    setToggling(p => ({ ...p, [camId]: false }))
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
    <div style={{ display:'grid', gridTemplateColumns:'1fr 300px', gap:20 }}>
      {/* Camera feeds */}
      <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
        {camIds.map(camId => {
          const s             = camStats[camId] || {}
          const running        = s.status === 'running'
          const reconnecting   = s.status === 'reconnecting'
          const recOn          = s.recognition_enabled === true
          const isPending      = toggling[camId]

          return (
            <div key={camId} className="card" style={{ padding:0, overflow:'hidden' }}>
              {/* Header */}
              <div style={{
                display:'flex', alignItems:'center', justifyContent:'space-between',
                padding:'12px 16px', borderBottom:'1px solid var(--border)',
              }}>
                <div className="flex">
                  <span style={{ fontSize:14, fontWeight:700 }}>{camId}</span>
                  <span className={`sdot ${
                    running ? 'green' : reconnecting ? 'yellow' : s.status === 'error' ? 'red' : 'yellow'
                  }`}/>
                  <span style={{ fontSize:11, color:'var(--text3)', fontFamily:'Space Mono,monospace' }}>
                    {running ? 'LIVE' : reconnecting ? 'RECONNECTING' : (s.status||'STOPPED').toUpperCase()}
                  </span>
                </div>

                <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                  {/* Recognition toggle — only meaningful when running */}
                  {running && (
                    <button
                      className={`rec-toggle ${recOn ? 'on' : 'off'}`}
                      disabled={isPending}
                      onClick={() => toggleRecognition(camId, recOn)}
                    >
                      <span className="rec-dot" />
                      {isPending ? 'Wait...' : recOn ? 'Recognition ON' : 'Recognition OFF'}
                    </button>
                  )}

                  {!running && (
                    <button className="btn btn-ghost btn-sm" onClick={() => camAction(camId,'start')}>▶ Start</button>
                  )}
                  {running && (
                    <button className="btn btn-ghost btn-sm" onClick={() => camAction(camId,'stop')}>■ Stop</button>
                  )}
                  <button className="btn btn-ghost btn-sm" onClick={() => camAction(camId,'restart')}>↺ Restart</button>
                </div>
              </div>

              {/* Video feed */}
              {running ? (
                s.is_push_source ? <ColabPushCameraFeed camId={camId} /> : <CameraFeed camId={camId} />
              ) : reconnecting ? (
                <div className="vidbox" style={{ borderRadius:0, border:'none' }}>
                  <div className="vid-err" style={{ flexDirection: 'column', gap: 12 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, opacity: 0.6 }}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="#fbbf24" strokeWidth="1.4" width="48">
                        <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                        <path d="M2 17l10 5 10-5"/>
                        <path d="M2 12l10 5 10-5"/>
                      </svg>
                      <span style={{ color: '#fbbf24', fontSize: 13, fontWeight: 600 }}>Reconnecting…</span>
                      <span style={{ color: 'var(--text3)', fontSize: 11 }}>Camera will resume automatically</span>
                    </div>
                    <span className="spin" style={{ width: 20, height: 20, borderTopColor: '#fbbf24' }} />
                  </div>
                </div>
              ) : (
                <div className="vidbox" style={{ borderRadius:0, border:'none' }}>
                  <div className="vid-err" style={{ flexDirection: 'column', gap: 16 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, opacity: 0.5 }}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" width="52">
                        <path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/>
                      </svg>
                      <span>Camera is stopped</span>
                    </div>
                    <button className="btn btn-primary" onClick={() => camAction(camId, 'start')}>
                      Start Camera
                    </button>
                  </div>
                </div>
              )}

              {/* Footer stats */}
              <div style={{
                padding:'10px 16px',
                background:'var(--bg2)',
                display:'flex', gap:20, flexWrap:'wrap',
                fontSize:12, fontFamily:'Space Mono,monospace', color:'var(--text3)',
              }}>
                <span>Capture: <strong style={{color:'var(--secondary)'}}>{s.capture_fps||0} fps</strong></span>
                <span>Stream: <strong style={{color:'var(--text2)'}}>{s.stream_fps||0} fps</strong></span>
                <span>Faces: <strong style={{color:'var(--text2)'}}>{s.faces_detected||0}</strong></span>
                {recOn && <span>Marked today: <strong style={{color:'#4ade80'}}>{s.recognitions_today||0}</strong></span>}
                {!running && <span style={{color:'var(--text3)'}}>Stopped</span>}
              </div>
            </div>
          )
        })}
      </div>

      {/* Live detections sidebar */}
      <div className="card" style={{ alignSelf:'start', position:'sticky', top:80 }}>
        <div className="card-title">
          <span className="card-icon">⊕</span>
          Detections
          <span className="sdot green" style={{ marginLeft:4 }} />
        </div>
        <div className="log-list" style={{ maxHeight:520, overflowY:'auto' }}>
          {feed.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">📷</div>
              <div className="empty-title">No detections yet</div>
              <div className="empty-sub">Enable recognition on a camera to start marking attendance.</div>
            </div>
          ) : feed.map((r, i) => (
            <div key={i} className="log-item">
              <div className="log-av">{initials(r.student_name)}</div>
              <div className="log-info">
                <div className="log-name">{r.student_name || 'Unknown'}</div>
                <div className="log-time">{r.camera_id} · {r.timestamp}</div>
              </div>
              <span className="badge badge-green mono">{(r.confidence||0).toFixed(3)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
