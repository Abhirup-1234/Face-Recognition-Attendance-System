import { useState, useRef, useEffect, useCallback } from 'react'
import { useEnrollQueue } from '../context/EnrollQueueContext'
import { useToast } from '../context/ToastContext'
import { students as studentsApi, classes as classesApi } from '../api'

const GUIDE_STEPS = [
  { id: 'gs1', label: '1. Face forward',  count: '5 shots', until: 5  },
  { id: 'gs2', label: '2. Turn left',     count: '3 shots', until: 8  },
  { id: 'gs3', label: '3. Turn right',    count: '3 shots', until: 11 },
  { id: 'gs4', label: '4. Tilt up',       count: '2 shots', until: 13 },
  { id: 'gs5', label: '5. Tilt down',     count: '2 shots', until: 15 },
  { id: 'gs6', label: '6. Any expression',count: 'rest',    until: 20 },
]

function StepClass(n, step, i) {
  const prev = i === 0 ? 0 : GUIDE_STEPS[i - 1].until
  if (n >= step.until) return 'guide-step done'
  if (n >= prev)       return 'guide-step active'
  return 'guide-step'
}

export default function Enroll() {
  // Form state
  const [studentId, setStudentId] = useState('')
  const [name,      setName]      = useState('')
  const [classVal,  setClassVal]  = useState('')
  const [section,   setSection]   = useState('')
  const [rollNo,    setRollNo]    = useState('')

  // Webcam state
  const [tab,      setTab]      = useState('webcam')
  const [stream,   setStream]   = useState(null)
  const [blobs,    setBlobs]    = useState([])
  const [upFiles,  setUpFiles]  = useState([])
  const videoRef = useRef(null)
  const canvasRef = useRef(null)

  // Data
  const [classList,  setClassList]  = useState([])
  const [studentList,setStudentList]= useState([])
  const [search,     setSearch]     = useState('')

  const { addToQueue } = useEnrollQueue()
  const toast = useToast()

  useEffect(() => {
    classesApi.list().then(r => r?.ok && setClassList(r.data))
    studentsApi.list().then(r => r?.ok && setStudentList(r.data))
  }, [])

  // Camera
  const startCam = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' } })
      setStream(s)
      if (videoRef.current) videoRef.current.srcObject = s
    } catch (e) {
      toast('Camera access denied: ' + e.message, 'error')
    }
  }

  const stopCam = useCallback(() => {
    if (stream) { stream.getTracks().forEach(t => t.stop()); setStream(null) }
    if (videoRef.current) videoRef.current.srcObject = null
  }, [stream])

  useEffect(() => () => stopCam(), [stopCam])

  const capture = useCallback(() => {
    if (!stream || !videoRef.current || !canvasRef.current) return
    const v = videoRef.current, c = canvasRef.current
    c.width = v.videoWidth || 640; c.height = v.videoHeight || 480
    c.getContext('2d').drawImage(v, 0, 0)
    // Flash effect
    if (videoRef.current) {
      videoRef.current.style.outline = '3px solid var(--success)'
      setTimeout(() => { if (videoRef.current) videoRef.current.style.outline = '' }, 220)
    }
    c.toBlob(b => setBlobs(prev => [...prev, b]), 'image/jpeg', 0.92)
  }, [stream])

  // Space bar capture
  useEffect(() => {
    const handler = e => {
      if (e.code !== 'Space') return
      const tag = document.activeElement?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (!stream) return
      e.preventDefault()
      capture()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [stream, capture])

  const removeBlob = i => setBlobs(prev => prev.filter((_, idx) => idx !== i))

  const validate = () => {
    if (!studentId.trim()) { toast('Student ID is required.', 'warning'); return false }
    if (!name.trim())      { toast('Name is required.', 'warning'); return false }
    if (!classVal)         { toast('Class is required.', 'warning'); return false }
    if (!section.trim())   { toast('Section is required.', 'warning'); return false }
    if (!rollNo || parseInt(rollNo) < 1) { toast('Roll number is required.', 'warning'); return false }
    return true
  }

  const clearForm = () => {
    setStudentId(''); setName(''); setSection(''); setRollNo('')
    // Keep class — useful for batch enrollment
  }

  const handleAddToQueue = () => {
    if (!validate()) return

    if (tab === 'webcam') {
      if (blobs.length < 3) { toast('Capture at least 3 photos first.', 'warning'); return }
      addToQueue(
        { student_id: studentId.trim(), name: name.trim(), class_name: classVal, section: section.trim(), roll_no: rollNo },
        blobs,
        []
      )
      clearForm(); setBlobs([]); stopCam()
    } else {
      if (upFiles.length === 0) { toast('Upload at least one photo.', 'warning'); return }
      addToQueue(
        { student_id: studentId.trim(), name: name.trim(), class_name: classVal, section: section.trim(), roll_no: rollNo },
        [],
        upFiles
      )
      clearForm(); setUpFiles([])
    }

    toast('Added to enrollment queue!', 'success', 2500)
    // Refresh student list after a moment
    setTimeout(() => studentsApi.list().then(r => r?.ok && setStudentList(r.data)), 2000)
  }

  const handleRemoveStudent = async (sid, sname) => {
    if (!confirm(`Remove ${sname} (${sid})?`)) return
    const res = await studentsApi.remove(sid)
    if (res?.data?.ok) {
      toast(`${sname} removed.`, 'success')
      setStudentList(prev => prev.filter(s => s.student_id !== sid))
    }
  }

  const filtered = studentList.filter(s => {
    if (!search) return true
    const q = search.toLowerCase()
    return s.name?.toLowerCase().includes(q) || s.student_id?.toLowerCase().includes(q) || s.class_name?.toLowerCase().includes(q)
  })

  return (
    <div className="g2" style={{ gap: 20, alignItems: 'start' }}>
      {/* Enrollment form */}
      <div className="card">
        <div className="card-title"><span className="card-icon">◊</span> New Student Enrollment</div>

        {/* Student details */}
        <div className="form-row3" style={{ marginBottom: 16 }}>
          <div className="form-group">
            <label className="form-label">Student ID <span className="required">*</span></label>
            <input className="form-input" placeholder="e.g. S001" value={studentId} onChange={e => setStudentId(e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Full Name <span className="required">*</span></label>
            <input className="form-input" placeholder="e.g. Arjun Sharma" value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Class <span className="required">*</span></label>
            <select className="form-select" value={classVal} onChange={e => setClassVal(e.target.value)}>
              <option value="">Select class</option>
              {classList.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
        </div>
        <div className="form-row" style={{ marginBottom: 20 }}>
          <div className="form-group">
            <label className="form-label">Section <span className="required">*</span></label>
            <input className="form-input" placeholder="A / B / C" value={section} onChange={e => setSection(e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Roll Number <span className="required">*</span></label>
            <input className="form-input" type="number" placeholder="1" min="1" value={rollNo} onChange={e => setRollNo(e.target.value)} />
          </div>
        </div>

        {/* Tabs */}
        <div className="tabbar">
          <button className={`tabbtn${tab === 'webcam' ? ' active' : ''}`} onClick={() => { setTab('webcam'); stopCam() }}>
            📹 Webcam Capture
          </button>
          <button className={`tabbtn${tab === 'upload' ? ' active' : ''}`} onClick={() => { setTab('upload'); stopCam() }}>
            ↑ Upload Photos
          </button>
        </div>

        {/* Webcam tab */}
        {tab === 'webcam' && (
          <div className="wc-layout">
            <div className="wc-left">
              <div className="viewfinder" id="viewfinder">
                <video ref={videoRef} autoPlay playsInline muted id="wc-video" />
                <canvas ref={canvasRef} style={{ display: 'none' }} />
                {!stream && (
                  <div className="cam-idle">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" width="44" opacity=".3">
                      <path d="M23 7l-7 5 7 5V7z" /><rect x="1" y="5" width="15" height="14" rx="2" />
                    </svg>
                    <span>Camera not started</span>
                  </div>
                )}
                {stream && (
                  <>
                    <div className="face-oval-wrap">
                      <div className="face-oval" />
                      <div className="oval-label">Position face inside</div>
                    </div>
                    <div className="shot-badge">{blobs.length} / 20</div>
                  </>
                )}
              </div>

              <div className="cam-ctrl">
                {!stream && (
                  <button className="btn-cam btn-cam-start" onClick={startCam}>▶ Start Camera</button>
                )}
                {stream && (
                  <>
                    <button className="btn-cam btn-cam-capture" onClick={capture}>
                      ● Capture <kbd style={{ background: 'rgba(255,255,255,.15)', borderRadius: 3, padding: '1px 5px', fontSize: 11 }}>Space</kbd>
                    </button>
                    <button className="btn-cam btn-cam-stop" onClick={stopCam}>■ Stop</button>
                  </>
                )}
              </div>

              {/* Add to Queue button */}
              <div style={{ paddingTop: 12 }}>
                <button className="btn btn-primary btn-full" onClick={handleAddToQueue}>
                  + Add to Enrollment Queue
                </button>
              </div>

              {/* Thumbnails */}
              <div style={{ marginTop: 14 }}>
                <div className="flex-sb" style={{ marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: blobs.length >= 10 ? 'var(--success)' : 'var(--warning)' }}>
                    {blobs.length > 0 ? `${blobs.length} photo(s)${blobs.length < 10 ? ' — 10+ recommended' : ' — Good'}` : ''}
                  </span>
                  {blobs.length > 0 && (
                    <button
                      style={{ background: 'none', border: '1px solid rgba(239,68,68,.3)', color: 'var(--danger)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', fontSize: 12, cursor: 'pointer', fontFamily: "'Sora', sans-serif" }}
                      onClick={() => setBlobs([])}
                    >
                      Clear All
                    </button>
                  )}
                </div>
                <div className="thumb-grid">
                  {blobs.length === 0 ? (
                    <span className="no-photos">No photos yet</span>
                  ) : (
                    blobs.map((b, i) => (
                      <div key={i} className="thumb filled">
                        <img src={URL.createObjectURL(b)} alt="" />
                        <button className="thumb-rm" onClick={() => removeBlob(i)}>×</button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* Guide */}
            <div className="wc-sidebar">
              <div className="guide-box">
                <div className="guide-title">Capture Guide</div>
                {GUIDE_STEPS.map((step, i) => (
                  <div key={step.id} className={StepClass(blobs.length, step, i)}>
                    <span>{step.label}</span>
                    <span className="step-cnt">{step.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Upload tab */}
        {tab === 'upload' && (
          <div>
            <div
              className={`dz${upFiles.length > 0 ? ' dragover' : ''}`}
              onClick={() => document.getElementById('file-input').click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => {
                e.preventDefault()
                const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'))
                setUpFiles(prev => [...prev, ...files])
              }}
            >
              <input id="file-input" type="file" accept="image/*" multiple style={{ display: 'none' }}
                onChange={e => setUpFiles(prev => [...prev, ...Array.from(e.target.files)])} />
              <div style={{ fontSize: 32, marginBottom: 10 }}>📁</div>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Drop photos here or click to browse</div>
              <div style={{ fontSize: 12.5, color: 'var(--text3)' }}>JPEG / PNG · 10+ photos recommended</div>
            </div>

            {upFiles.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div className="flex-sb" style={{ marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: upFiles.length >= 10 ? 'var(--success)' : 'var(--warning)' }}>
                    {upFiles.length} photo(s) selected
                  </span>
                  <button
                    style={{ background: 'none', border: '1px solid rgba(239,68,68,.3)', color: 'var(--danger)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', fontSize: 12, cursor: 'pointer', fontFamily: "'Sora', sans-serif" }}
                    onClick={() => setUpFiles([])}
                  >
                    Clear
                  </button>
                </div>
                <div className="thumb-grid">
                  {upFiles.slice(0, 24).map((f, i) => (
                    <div key={i} className="thumb filled">
                      <img src={URL.createObjectURL(f)} alt="" />
                      <button className="thumb-rm" onClick={() => setUpFiles(prev => prev.filter((_, idx) => idx !== i))}>×</button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div style={{ paddingTop: 16 }}>
              <button className="btn btn-primary btn-full" onClick={handleAddToQueue}>
                + Add to Enrollment Queue
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Enrolled students */}
      <div className="card">
        <div className="card-title flex-sb">
          <span><span className="card-icon">👥</span> Enrolled Students ({studentList.length})</span>
          <input
            className="form-input" style={{ maxWidth: 180, padding: '6px 10px', fontSize: 12.5 }}
            placeholder="Search..." value={search} onChange={e => setSearch(e.target.value)}
          />
        </div>
        <div className="table-wrap" style={{ maxHeight: 500, overflowY: 'auto' }}>
          <table>
            <thead>
              <tr><th>Name</th><th>Class</th><th>Roll</th><th>Enrolled</th><th></th></tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={5} className="empty" style={{ padding: 32 }}>No students enrolled yet.</td></tr>
              ) : (
                filtered.map(s => (
                  <tr key={s.student_id}>
                    <td>
                      <div className="flex">
                        <div className="log-av" style={{ width: 30, height: 30, fontSize: 11 }}>
                          {(s.name || 'XX').slice(0, 2).toUpperCase()}
                        </div>
                        <div>
                          <div className="td-name">{s.name}</div>
                          <div style={{ fontSize: 11.5, color: 'var(--text3)', fontFamily: 'Space Mono, monospace' }}>{s.student_id}</div>
                        </div>
                      </div>
                    </td>
                    <td><span className="badge badge-blue">{s.class_name}</span></td>
                    <td className="mono">{s.roll_no}</td>
                    <td style={{ fontSize: 12, color: 'var(--text3)' }}>{(s.enrolled_at || '').slice(0, 10)}</td>
                    <td>
                      <button className="btn btn-danger btn-sm" onClick={() => handleRemoveStudent(s.student_id, s.name)}>
                        Remove
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
