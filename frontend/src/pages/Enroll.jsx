import { useState, useRef, useEffect, useCallback } from 'react'
import { useEnrollQueue } from '../context/EnrollQueueContext'
import { useToast } from '../context/ToastContext'
import { classes as classesApi, streams as streamsApi, sections as sectionsApi, students as studentsApi } from '../api'


const GUIDE_STEPS = [
  { id:'gs1', label:'1. Face forward',   count:'5 shots', until:5  },
  { id:'gs2', label:'2. Turn left',      count:'3 shots', until:8  },
  { id:'gs3', label:'3. Turn right',     count:'3 shots', until:11 },
  { id:'gs4', label:'4. Tilt up',        count:'2 shots', until:13 },
  { id:'gs5', label:'5. Tilt down',      count:'2 shots', until:15 },
  { id:'gs6', label:'6. Any expression', count:'rest',    until:20 },
]

function stepClass(n, step, i) {
  const prev = i === 0 ? 0 : GUIDE_STEPS[i-1].until
  if (n >= step.until) return 'guide-step done'
  if (n >= prev)       return 'guide-step active'
  return 'guide-step'
}

export default function Enroll() {
  const [studentId,  setStudentId]  = useState('')
  const [name,       setName]       = useState('')
  const [classVal,   setClassVal]   = useState('')
  const [streamVal,  setStreamVal]  = useState('')
  const [section,    setSection]    = useState('')
  const [rollNo,     setRollNo]     = useState('')
  const [tab,        setTab]        = useState('webcam')
  const [active,     setActive]     = useState(false)
  const [blobs,      setBlobs]      = useState([])
  const [upFiles,    setUpFiles]    = useState([])
  const [classList,   setClassList]   = useState([])
  const [streamList,  setStreamList]  = useState([])
  const [sectionList, setSectionList] = useState([])

  const videoRef  = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)
  const { addToQueue, removeFromQueue, queue, current, progress } = useEnrollQueue()
  const toast = useToast()

  useEffect(() => {
    classesApi.list().then(r => r?.ok && setClassList(r.data))
  }, [])

  // When class changes: load streams (XI/XII only), reset stream/section
  useEffect(() => {
    setStreamVal(''); setSection(''); setStreamList([]); setSectionList([])
    if (!classVal) return
    streamsApi.list(classVal).then(r => {
      if (r?.ok && r.data.length > 0) setStreamList(r.data)
      // For non-stream classes load sections immediately
      else if (r?.ok && r.data.length === 0) {
        sectionsApi.list(classVal, '').then(sr => {
          if (sr?.ok) {
            setSectionList(sr.data)
            if (sr.data.length === 1) setSection(sr.data[0])
          }
        })
      }
    })
  }, [classVal])

  // When stream changes: load sections
  useEffect(() => {
    setSection(''); setSectionList([])
    if (!classVal || !streamVal) return
    sectionsApi.list(classVal, streamVal).then(r => {
      if (r?.ok) {
        setSectionList(r.data)
        if (r.data.length === 1) setSection(r.data[0])
      }
    })
  }, [classVal, streamVal])



  // ── Camera ────────────────────────────────────────────────────────────────
  const stopCam = useCallback(() => {
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null }
    if (videoRef.current) videoRef.current.srcObject = null
    setActive(false)
  }, [])

  useEffect(() => () => stopCam(), []) // eslint-disable-line

  const startCam = async () => {
    if (streamRef.current) return
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { width:{ideal:1280}, height:{ideal:720} } })
      streamRef.current = s
      if (videoRef.current) { videoRef.current.srcObject = s; videoRef.current.play().catch(()=>{}) }
      setActive(true)
    } catch(err) {
      toast(err.name==='NotFoundError' ? 'No camera found.' :
            err.name==='NotAllowedError' ? 'Camera permission denied.' :
            err.name==='NotReadableError' ? 'Camera in use by another app.' :
            'Camera error: '+err.message, 'error')
    }
  }

  const capture = useCallback(() => {
    const v=videoRef.current, c=canvasRef.current
    if (!streamRef.current||!v||!c) return
    c.width=v.videoWidth||640; c.height=v.videoHeight||480
    c.getContext('2d').drawImage(v,0,0)
    v.style.outline='3px solid var(--success)'
    setTimeout(()=>{ if(videoRef.current) videoRef.current.style.outline='' },220)
    c.toBlob(b=>setBlobs(p=>[...p,b]),'image/jpeg',0.92)
  },[])

  useEffect(()=>{
    const h=e=>{
      if(e.code!=='Space') return
      const tag=document.activeElement?.tagName
      if(tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT') return
      if(!streamRef.current) return
      e.preventDefault(); capture()
    }
    window.addEventListener('keydown',h); return ()=>window.removeEventListener('keydown',h)
  },[capture])

  // ── Validation ────────────────────────────────────────────────────────────
  const validate = () => {
    if (!studentId.trim()) { toast('Student ID is required.','warning'); return false }
    if (!name.trim())      { toast('Name is required.','warning');        return false }
    if (!classVal)         { toast('Class is required.','warning');       return false }
    if (streamList.length>0 && !streamVal) { toast('Stream is required.','warning'); return false }
    if (!section)          { toast('Section is required.','warning');     return false }
    if (!rollNo||parseInt(rollNo)<1) { toast('Roll number is required.','warning'); return false }
    return true
  }
  const clearForm = () => { setStudentId(''); setName(''); setRollNo('') }

  const handleAddToQueue = () => {
    if (!validate()) return
    const meta = { student_id:studentId.trim(), name:name.trim(), class_name:classVal,
                   stream:streamVal, section, roll_no:rollNo }
    if (tab==='webcam') {
      if (blobs.length<3) { toast('Capture at least 3 photos first.','warning'); return }
      addToQueue(meta, blobs, [])
      clearForm(); setBlobs([]); stopCam()
    } else {
      if (upFiles.length===0) { toast('Upload at least one photo.','warning'); return }
      addToQueue(meta, [], upFiles)
      clearForm(); setUpFiles([])
    }
    toast('Added to enrollment queue!','success',2500)
  }



  const needsStream = streamList.length > 0

  return (
    <div className="g2" style={{ gap:20, alignItems:'start' }}>

      {/* ── Enrollment form ──────────────────────────────────────────────── */}
      <div className="card">
        <div className="card-title"><span className="card-icon">◊</span> New Student Enrollment</div>

        {/* Row 1: ID / Name / Class */}
        <div className="form-row3" style={{ marginBottom:14 }}>
          <div className="form-group">
            <label className="form-label">Student ID <span className="required">*</span></label>
            <input className="form-input" placeholder="e.g. S001" value={studentId} onChange={e=>setStudentId(e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Full Name <span className="required">*</span></label>
            <input className="form-input" placeholder="e.g. Arjun Sharma" value={name} onChange={e=>setName(e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Class <span className="required">*</span></label>
            <select className="form-select" value={classVal} onChange={e=>setClassVal(e.target.value)}>
              <option value="">Select class</option>
              {classList.map(c=><option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        </div>

        {/* Row 2: Stream (XI/XII only) / Section / Roll */}
        <div className={needsStream ? 'form-row3' : 'form-row'} style={{ marginBottom:20 }}>
          {needsStream && (
            <div className="form-group">
              <label className="form-label">Stream <span className="required">*</span></label>
              <select className="form-select" value={streamVal} onChange={e=>setStreamVal(e.target.value)}>
                <option value="">Select stream</option>
                {streamList.map(s=><option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          )}
          <div className="form-group">
            <label className="form-label">Section <span className="required">*</span></label>
            {sectionList.length > 0 ? (
              <select className="form-select" value={section} onChange={e=>setSection(e.target.value)}>
                <option value="">Select section</option>
                {sectionList.map(s=><option key={s} value={s}>Section {s}</option>)}
              </select>
            ) : (
              <div className="form-input" style={{ display:'flex', alignItems:'center', color:'var(--text3)', fontSize:13, opacity:0.6 }}>
                {!classVal ? 'Select a class first' : needsStream && !streamVal ? 'Select a stream first' : 'No sections — add in Manage'}
              </div>
            )}
          </div>
          <div className="form-group">
            <label className="form-label">Roll Number <span className="required">*</span></label>
            <input className="form-input" type="number" placeholder="1" min="1" value={rollNo} onChange={e=>setRollNo(e.target.value)} />
          </div>
        </div>

        {/* Tabs */}
        <div className="tabbar">
          <button className={`tabbtn${tab==='webcam'?' active':''}`} onClick={()=>setTab('webcam')}>📹 Webcam Capture</button>
          <button className={`tabbtn${tab==='upload'?' active':''}`} onClick={()=>{setTab('upload');stopCam()}}>↑ Upload Photos</button>
        </div>

        {tab==='webcam' && (
          <div className="wc-layout">
            <div className="wc-left">
              <div className="viewfinder">
                <video ref={videoRef} autoPlay playsInline muted id="wc-video"
                  onLoadedMetadata={()=>videoRef.current?.play().catch(()=>{})} />
                <canvas ref={canvasRef} style={{display:'none'}} />
                {!active && <div className="cam-idle">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" width="44" opacity=".3">
                    <path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/>
                  </svg>
                  <span>Camera not started</span>
                </div>}
                {active && <>
                  <div className="face-oval-wrap"><div className="face-oval"/><div className="oval-label">Position face inside</div></div>
                  <div className="shot-badge">{blobs.length} / 20</div>
                </>}
              </div>
              <div className="cam-ctrl">
                {!active && <button className="btn-cam btn-cam-start" onClick={startCam}>▶ Start Camera</button>}
                {active && <>
                  <button className="btn-cam btn-cam-capture" onClick={capture}>
                    ● Capture <kbd style={{background:'rgba(255,255,255,.15)',borderRadius:3,padding:'1px 5px',fontSize:11}}>Space</kbd>
                  </button>
                  <button className="btn-cam btn-cam-stop" onClick={stopCam}>■ Stop</button>
                </>}
              </div>
              <div style={{paddingTop:12}}>
                <button className="btn btn-primary btn-full" onClick={handleAddToQueue}>+ Add to Enrollment Queue</button>
              </div>
              <div style={{marginTop:14}}>
                <div className="flex-sb" style={{marginBottom:8}}>
                  <span style={{fontSize:12,color:blobs.length>=10?'var(--success)':'var(--warning)'}}>
                    {blobs.length>0?`${blobs.length} photo(s)${blobs.length<10?' — 10+ recommended':' — Good'}`:''}
                  </span>
                  {blobs.length>0 && <button style={{background:'none',border:'1px solid rgba(239,68,68,.3)',color:'var(--danger)',borderRadius:'var(--radius-sm)',padding:'4px 10px',fontSize:12,cursor:'pointer',fontFamily:"'Sora',sans-serif"}} onClick={()=>setBlobs([])}>Clear All</button>}
                </div>
                <div className="thumb-grid">
                  {blobs.length===0 ? <span className="no-photos">No photos yet</span>
                    : blobs.map((b,i)=>(
                      <div key={i} className="thumb filled">
                        <img src={URL.createObjectURL(b)} alt=""/>
                        <button className="thumb-rm" onClick={()=>setBlobs(p=>p.filter((_,idx)=>idx!==i))}>×</button>
                      </div>
                    ))}
                </div>
              </div>
            </div>
            <div className="wc-sidebar">
              <div className="guide-box">
                <div className="guide-title">Capture Guide</div>
                {GUIDE_STEPS.map((step,i)=>(
                  <div key={step.id} className={stepClass(blobs.length,step,i)}>
                    <span>{step.label}</span><span className="step-cnt">{step.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {tab==='upload' && (
          <div>
            <div className={`dz${upFiles.length>0?' dragover':''}`}
              onClick={()=>document.getElementById('file-input').click()}
              onDragOver={e=>e.preventDefault()}
              onDrop={e=>{e.preventDefault();setUpFiles(p=>[...p,...Array.from(e.dataTransfer.files).filter(f=>f.type.startsWith('image/'))])}}>
              <input id="file-input" type="file" accept="image/*" multiple style={{display:'none'}}
                onChange={e=>setUpFiles(p=>[...p,...Array.from(e.target.files)])}/>
              <div style={{fontSize:32,marginBottom:10}}>📁</div>
              <div style={{fontSize:14,fontWeight:600,marginBottom:4}}>Drop photos here or click to browse</div>
              <div style={{fontSize:12.5,color:'var(--text3)'}}>JPEG / PNG · 10+ photos recommended</div>
            </div>
            <div style={{paddingTop:16}}>
              <button className="btn btn-primary btn-full" onClick={handleAddToQueue}>+ Add to Enrollment Queue</button>
            </div>
            {upFiles.length>0 && (
              <div style={{marginTop:12}}>
                <div className="flex-sb" style={{marginBottom:8}}>
                  <span style={{fontSize:12,color:upFiles.length>=10?'var(--success)':'var(--warning)'}}>{upFiles.length} photo(s) selected</span>
                  <button style={{background:'none',border:'1px solid rgba(239,68,68,.3)',color:'var(--danger)',borderRadius:'var(--radius-sm)',padding:'4px 10px',fontSize:12,cursor:'pointer',fontFamily:"'Sora',sans-serif"}} onClick={()=>setUpFiles([])}>Clear</button>
                </div>
                <div className="thumb-grid">
                  {upFiles.slice(0,24).map((f,i)=>(
                    <div key={i} className="thumb filled">
                      <img src={URL.createObjectURL(f)} alt=""/>
                      <button className="thumb-rm" onClick={()=>setUpFiles(p=>p.filter((_,idx)=>idx!==i))}>×</button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Enrollment Queue (inline) ─────────────────────────────────────── */}
      <div style={{display:'flex',flexDirection:'column',gap:20}}>
        <div className="card">
          <div className="card-title">
            <span className="card-icon">⏳</span>
            Enrollment Queue
            {queue.length > 0 && (
              <span className="badge badge-orange" style={{marginLeft:6}}>{queue.length} pending</span>
            )}
          </div>
          {queue.length === 0 ? (
            <div className="empty">
              <div className="empty-icon">📭</div>
              <div className="empty-title">Queue is empty</div>
              <div className="empty-sub">Add students using the form on the left to start enrolling.</div>
            </div>
          ) : (
            <div style={{display:'flex',flexDirection:'column',gap:8}}>
              {queue.map((item, i) => {
                const isProcessing = i === 0 && current
                const photoUrl = item.blobs?.[0]
                  ? URL.createObjectURL(item.blobs[0])
                  : item.files?.[0]
                    ? URL.createObjectURL(item.files[0])
                    : null
                return (
                  <div key={item.id} style={{
                    display:'flex', alignItems:'center', gap:12,
                    padding:'12px 14px',
                    background: isProcessing ? 'rgba(37,99,235,.08)' : 'rgba(255,255,255,.02)',
                    border: `1px solid ${isProcessing ? 'rgba(37,99,235,.25)' : 'var(--border)'}`,
                    borderRadius:'var(--radius-sm)',
                    transition:'all .2s',
                  }}>
                    {/* Avatar: photo or number */}
                    <div style={{
                      width:34, height:34, borderRadius:'50%', flexShrink:0,
                      overflow:'hidden',
                      background: isProcessing
                        ? 'linear-gradient(135deg,var(--nps-blue),var(--nps-blue2))'
                        : 'rgba(255,255,255,.06)',
                      display:'flex', alignItems:'center', justifyContent:'center',
                      fontSize:13, fontWeight:800,
                      boxShadow: isProcessing ? '0 2px 10px rgba(37,99,235,.3)' : 'none',
                    }}>
                      {photoUrl ? (
                        <img src={photoUrl} alt="" style={{width:'100%',height:'100%',objectFit:'cover'}} />
                      ) : (
                        i + 1
                      )}
                    </div>
                    <div style={{flex:1, minWidth:0}}>
                      <div style={{fontSize:13.5,fontWeight:600,color:'var(--text)',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>
                        {item.meta.name}
                      </div>
                      <div style={{fontSize:11.5,color:'var(--text3)',marginTop:2,fontFamily:'Space Mono,monospace'}}>
                        {item.meta.student_id} · {item.meta.class_name}
                        {item.meta.stream ? ` · ${item.meta.stream}` : ''}
                        {` · Sec ${item.meta.section} · Roll ${item.meta.roll_no}`}
                      </div>
                      {isProcessing && (
                        <div style={{marginTop:6}}>
                          <div style={{height:3,borderRadius:999,background:'var(--border)',overflow:'hidden'}}>
                            <div style={{
                              height:'100%',
                              width:`${progress}%`,
                              background:'linear-gradient(90deg,var(--accent),var(--nps-blue,var(--accent)))',
                              borderRadius:999,
                              transition:'width .3s ease',
                            }}/>
                          </div>
                          <div style={{fontSize:10.5,color:'var(--text3)',marginTop:2}}>{Math.round(progress)}%</div>
                        </div>
                      )}
                    </div>
                    <span className={`badge ${isProcessing ? 'badge-blue' : 'badge-gray'}`} style={{flexShrink:0}}>
                      {isProcessing ? 'Processing…' : 'Queued'}
                    </span>
                    {/* Cancel button — hidden while item is processing */}
                    {!isProcessing && (
                      <button
                        onClick={() => removeFromQueue(item.id)}
                        title="Cancel enrollment"
                        style={{
                          flexShrink:0, width:26, height:26, borderRadius:'50%',
                          background:'rgba(239,68,68,.12)',
                          border:'1px solid rgba(239,68,68,.25)',
                          color:'var(--danger)', fontSize:14, fontWeight:700,
                          cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center',
                          transition:'all .15s', lineHeight:1,
                        }}
                        onMouseOver={e=>{e.currentTarget.style.background='rgba(239,68,68,.25)'}}
                        onMouseOut={e=>{e.currentTarget.style.background='rgba(239,68,68,.12)'}}
                      >×</button>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
