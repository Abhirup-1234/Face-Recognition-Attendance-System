import { useState, useEffect, useCallback } from 'react'
import { classes as classesApi, streams as streamsApi, sections as sectionsApi,
         classrooms as classroomsApi, students as studentsApi, cameras as camerasApi } from '../api'
import { useToast } from '../context/ToastContext'

const STREAM_CLASSES = new Set(['XI','XII'])
const FIXED_STREAMS  = ['Science','Commerce','Humanities']

export default function Manage() {
  const [tab, setTab] = useState('students')
  return (
    <div>
      <div className="tabbar" style={{maxWidth:580,marginBottom:20}}>
        <button className={`tabbtn${tab==='students'?' active':''}`} onClick={()=>setTab('students')}>◊ Students</button>
        <button className={`tabbtn${tab==='classes'?' active':''}`} onClick={()=>setTab('classes')}>⌾ Classes &amp; Sections</button>
        <button className={`tabbtn${tab==='cameras'?' active':''}`} onClick={()=>setTab('cameras')}>📷 Camera Assignments</button>
      </div>
      {tab==='students' && <StudentsTab/>}
      {tab==='classes'  && <ClassesTab/>}
      {tab==='cameras'  && <CamerasTab/>}
    </div>
  )
}

// ── Classes & Sections tab ────────────────────────────────────────────────────
function ClassesTab() {
  const [classList,  setClassList]  = useState([])
  // Map: "cls" or "cls::stream" → section[]
  const [secMap,     setSecMap]     = useState({})
  const [students,   setStudents]   = useState([])
  const [newClass,   setNewClass]   = useState('')
  const [newSecFor,  setNewSecFor]  = useState({})
  const toast = useToast()

  const loadAll = useCallback(async () => {
    const [cr, sr] = await Promise.all([classesApi.list(), studentsApi.list()])
    const classes = cr?.ok ? cr.data : []
    setClassList(classes)
    if (sr?.ok) setStudents(sr.data)

    const map = {}
    for (const cls of classes) {
      if (STREAM_CLASSES.has(cls)) {
        for (const stream of FIXED_STREAMS) {
          const r = await sectionsApi.list(cls, stream)
          map[`${cls}::${stream}`] = r?.ok ? r.data : []
        }
      } else {
        const r = await sectionsApi.list(cls, '')
        map[cls] = r?.ok ? r.data : []
      }
    }
    setSecMap(map)
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  const addClass = async () => {
    const name = newClass.trim()
    if (!name) { toast('Enter a class name.','warning'); return }
    const res = await classesApi.add(name)
    if (res?.data?.ok) { toast(`Class ${name} added.`,'success'); setNewClass(''); loadAll() }
    else toast(res?.data?.error||'Failed.','error')
  }

  const deleteClass = async (name) => {
    const count = students.filter(s=>s.class_name===name).length
    if (!confirm(count>0
      ? `${name} has ${count} enrolled student(s). Only removes from dropdown — students are NOT deleted. Continue?`
      : `Remove class "${name}"?`)) return
    const res = await classesApi.remove(name)
    if (res?.data?.ok) { toast(`${name} removed.`,'success'); loadAll() }
  }

  const addSection = async (cls, stream) => {
    const key = stream ? `${cls}::${stream}` : cls
    const sec = (newSecFor[key]||'').trim().toUpperCase()
    if (!sec) { toast('Enter a section label.','warning'); return }
    const res = await sectionsApi.add(cls, sec, stream)
    if (res?.data?.ok) { toast(`Section ${sec} added.`,'success'); setNewSecFor(p=>({...p,[key]:''})); loadAll() }
    else toast(res?.data?.error||'Failed.','error')
  }

  const deleteSection = async (cls, stream, sec) => {
    const enrolled = students.filter(s=>s.class_name===cls && s.stream===(stream||'') && s.section===sec)
    if (enrolled.length>0) { toast(`${enrolled.length} student(s) enrolled — remove them first.`,'error'); return }
    if (!confirm(`Remove Section ${sec} from Class ${cls}${stream?'/'+stream:''}?`)) return
    const res = await sectionsApi.remove(cls, sec, stream)
    if (res?.data?.ok) { toast(`Section ${sec} removed.`,'success'); loadAll() }
    else toast(res?.data?.error||'Failed.','error')
  }

  // Render section block for a given cls+stream combo
  const renderSections = (cls, stream) => {
    const key  = stream ? `${cls}::${stream}` : cls
    const secs = secMap[key] || []
    return (
      <div style={{paddingLeft:stream?24:12,marginTop:6}}>
        {secs.map(sec => {
          const cnt = students.filter(s=>s.class_name===cls && s.stream===(stream||'') && s.section===sec).length
          return (
            <div key={sec} style={{display:'flex',alignItems:'center',justifyContent:'space-between',
              background:'rgba(255,255,255,.03)',borderRadius:'var(--radius-xs)',
              padding:'6px 10px',border:'1px solid var(--border)',marginBottom:4}}>
              <div className="flex">
                <span style={{fontSize:13,color:'var(--secondary)',fontFamily:'Space Mono,monospace',fontWeight:700}}>
                  Section {sec}
                </span>
                <span className="badge badge-green" style={{fontSize:11}}>{cnt} student{cnt === 1 ? '' : 's'}</span>
              </div>
              <button className="btn btn-danger btn-sm" style={{padding:'3px 10px',fontSize:11}}
                onClick={()=>deleteSection(cls,stream,sec)}>Remove</button>
            </div>
          )
        })}
        <div style={{display:'flex',gap:6,marginTop:4}}>
          <input className="form-input" style={{flex:1,padding:'5px 10px',fontSize:12}}
            placeholder="New section (e.g. B)" maxLength={3}
            value={newSecFor[key]||''}
            onChange={e=>setNewSecFor(p=>({...p,[key]:e.target.value}))}
            onKeyDown={e=>e.key==='Enter'&&addSection(cls,stream)}/>
          <button className="btn btn-ghost btn-sm" onClick={()=>addSection(cls,stream)}>+ Add Section</button>
        </div>
      </div>
    )
  }

  return (
    <div style={{ width: '100%' }}>
      {/* Class list — scrollable so page never grows unbounded */}
      <div className="card" style={{display:'flex',flexDirection:'column', height: 'calc(100vh - 200px)', minHeight: 400}}>
        <div className="card-title flex-sb" style={{flexShrink:0}}>
          <span><span className="card-icon">▦</span> Classes &amp; Sections</span>
          <span style={{fontSize:12,color:'var(--text3)'}}>{classList.length} class(es)</span>
        </div>
        <div style={{overflowY:'auto',flex:1,marginRight:-4,paddingRight:4}}>
        {classList.length===0 ? <div className="muted">No classes yet.</div>
          : classList.map(cls => {
            const totalCount = students.filter(s=>s.class_name===cls).length
            const isStream   = STREAM_CLASSES.has(cls)
            const totalSecs  = isStream
              ? FIXED_STREAMS.reduce((acc, st) => acc + (secMap[`${cls}::${st}`]||[]).length, 0)
              : (secMap[cls]||[]).length

            return (
              <div key={cls} style={{padding:'12px 0',borderBottom:'1px solid var(--border)'}}>
                <div className="flex-sb" style={{marginBottom:6}}>
                  <div className="flex">
                    <span style={{fontSize:14,fontWeight:700}}>Class {cls}</span>
                    {isStream && <span className="badge badge-orange" style={{fontSize:11}}>{FIXED_STREAMS.length} stream{FIXED_STREAMS.length === 1 ? '' : 's'}</span>}
                    <span className="badge badge-cyan" style={{fontSize:11}}>{totalSecs} section{totalSecs === 1 ? '' : 's'}</span>
                    <span className="badge badge-blue">{totalCount} student{totalCount === 1 ? '' : 's'}</span>
                  </div>
                </div>

                {isStream ? (
                  // XI/XII: show stream → sections tree
                  FIXED_STREAMS.map(stream => {
                    const streamCount = students.filter(s=>s.class_name===cls && s.stream===stream).length
                    const streamSecs  = (secMap[`${cls}::${stream}`]||[]).length
                    return (
                      <div key={stream} style={{paddingLeft:12,marginBottom:10}}>
                        <div className="flex" style={{marginBottom:4}}>
                          <span style={{fontSize:13,fontWeight:600,color:'var(--warning)'}}>⟁ {stream}</span>
                          <span className="badge badge-cyan" style={{fontSize:11}}>{streamSecs} section{streamSecs === 1 ? '' : 's'}</span>
                          <span className="badge badge-yellow" style={{fontSize:11}}>{streamCount} student{streamCount === 1 ? '' : 's'}</span>
                        </div>
                        {renderSections(cls, stream)}
                      </div>
                    )
                  })
                ) : renderSections(cls, '')}
              </div>
            )
          })
        }
        </div>{/* end scroll container */}
      </div>
    </div>
  )
}

// ── Camera Assignments ────────────────────────────────────────────────────────
function CamerasTab() {
  const [camIds,    setCamIds]    = useState([])
  const [classes,   setClasses]   = useState([])
  const [classrooms,setClassrooms]= useState({})
  const [saved,     setSaved]     = useState({})
  const toast = useToast()

  useEffect(() => {
    camerasApi.stats().then(r => r?.ok && setCamIds(Object.keys(r.data)))
    classesApi.list().then(r => r?.ok && setClasses(r.data))
    classroomsApi.list().then(r => {
      if (r?.ok) { const m={}; r.data.forEach(c=>{m[c.camera_id]=c}); setClassrooms(m) }
    })
  },[])

  const getField = (camId, field, fallback='') => {
    const key=`${camId}-${field}`
    if (saved[key]!==undefined) return saved[key]
    const room=classrooms[camId]||{}
    if (field==='room_id')    return room.classroom_id||camId.replace('CAM-','Room ')
    if (field==='class_name') return room.class_name||''
    if (field==='floor')      return room.floor||1
    return fallback
  }
  const setField=(camId,field,val)=>setSaved(p=>({...p,[`${camId}-${field}`]:val}))

  const saveRoom=async camId=>{
    const roomId=getField(camId,'room_id')
    if(!roomId){toast('Enter a Room ID.','warning');return}
    const res=await classroomsApi.save(roomId,{camera_id:camId,class_name:getField(camId,'class_name'),floor:getField(camId,'floor')})
    if(res?.data?.ok) toast(`Saved ${camId}.`,'success'); else toast('Failed.','error')
  }

  return (
    <div className="card">
      <div className="card-title"><span className="card-icon">📷</span> Camera to Classroom Assignment</div>
      {camIds.length===0 ? <div className="muted">No cameras configured.</div>
        : camIds.map(camId=>(
          <div key={camId} style={{padding:'16px 0',borderBottom:'1px solid var(--border)'}}>
            <div style={{fontSize:14,fontWeight:700,color:'var(--secondary)',marginBottom:12,fontFamily:'Space Mono,monospace'}}>{camId}</div>
            <div className="form-row3">
              <div className="form-group">
                <label className="form-label">Room ID</label>
                <input className="form-input" placeholder="e.g. Room 101" value={getField(camId,'room_id')} onChange={e=>setField(camId,'room_id',e.target.value)}/>
              </div>
              <div className="form-group">
                <label className="form-label">Assigned Class</label>
                <select className="form-select" value={getField(camId,'class_name')} onChange={e=>setField(camId,'class_name',e.target.value)}>
                  <option value="">-- Not assigned --</option>
                  {classes.map(c=><option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Floor</label>
                <input className="form-input" type="number" min="0" max="20" value={getField(camId,'floor',1)} onChange={e=>setField(camId,'floor',e.target.value)}/>
              </div>
            </div>
            <div style={{marginTop:10}}><button className="btn btn-primary btn-sm" onClick={()=>saveRoom(camId)}>Save</button></div>
          </div>
        ))}
    </div>
  )
}

// ── Edit Student Modal ────────────────────────────────────────────────────────
function EditStudentModal({ student, classList, onClose, onSaved }) {
  const [name,       setName]       = useState(student.name)
  const [classVal,   setClassVal]   = useState(student.class_name)
  const [streamVal,  setStreamVal]  = useState(student.stream || '')
  const [section,    setSection]    = useState(student.section)
  const [rollNo,     setRollNo]     = useState(student.roll_no || '')
  const [streamList, setStreamList] = useState([])
  const [sectionList,setSectionList]= useState([])
  const [saving,     setSaving]     = useState(false)
  const toast = useToast()

  useEffect(() => {
    setStreamVal(''); setSectionList([]); setStreamList([])
    if (!classVal) return
    streamsApi.list(classVal).then(r => {
      if (r?.ok && r.data.length > 0) setStreamList(r.data)
      else if (r?.ok) {
        sectionsApi.list(classVal, '').then(sr => {
          if (sr?.ok) setSectionList(sr.data)
        })
      }
    })
  }, [classVal])

  useEffect(() => {
    setSectionList([])
    if (!classVal) return
    if (streamList.length > 0 && !streamVal) return
    sectionsApi.list(classVal, streamVal).then(r => {
      if (r?.ok) setSectionList(r.data)
    })
  }, [classVal, streamVal, streamList.length])

  // Restore original stream/section after loading
  useEffect(() => {
    if (streamList.length > 0) setStreamVal(student.stream || '')
  }, [streamList])
  useEffect(() => {
    if (sectionList.length > 0) setSection(student.section)
  }, [sectionList])

  const needsStream = streamList.length > 0

  const save = async () => {
    if (!name.trim()) { toast('Name is required.','warning'); return }
    if (!classVal)    { toast('Class is required.','warning'); return }
    if (!section)     { toast('Section is required.','warning'); return }
    setSaving(true)
    const res = await studentsApi.update(student.student_id, {
      name: name.trim(), class_name: classVal,
      stream: streamVal, section, roll_no: parseInt(rollNo) || 0,
    })
    setSaving(false)
    if (res?.data?.ok) {
      toast(`${name} updated.`, 'success')
      onSaved()
    } else {
      toast(res?.data?.error || 'Failed to update.', 'error')
    }
  }

  return (
    <div style={{
      position:'fixed', inset:0, zIndex:2000,
      display:'flex', alignItems:'center', justifyContent:'center',
      background:'rgba(0,0,0,.6)', backdropFilter:'blur(4px)',
    }} onClick={e => e.target===e.currentTarget && onClose()}>
      <div style={{
        background:'var(--surface)', border:'1px solid var(--border)',
        borderRadius:'var(--radius)', padding:28, width:520, maxWidth:'95vw',
        boxShadow:'0 16px 48px rgba(0,0,0,.5)',
        fontFamily:"'Sora', sans-serif",
      }}>
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:20}}>
          <div style={{fontSize:15,fontWeight:700,color:'var(--text)'}}>✏ Edit Student</div>
          <button onClick={onClose} style={{
            background:'none', border:'none', color:'var(--text3)',
            fontSize:20, cursor:'pointer', lineHeight:1, padding:'2px 6px',
          }}>×</button>
        </div>

        <div style={{fontSize:11.5,color:'var(--text3)',marginBottom:16,fontFamily:'Space Mono,monospace'}}>
          ID: {student.student_id}
        </div>

        {/* Photo preview */}
        {student.photo_path && (
          <div style={{display:'flex',justifyContent:'center',marginBottom:16}}>
            <img
              src={studentsApi.photoUrl(student.student_id)}
              alt={student.name}
              style={{
                width:80, height:80, borderRadius:'50%', objectFit:'cover',
                border:'2px solid var(--border)',
                boxShadow:'0 2px 12px rgba(0,0,0,.3)',
              }}
              onError={e=>{ e.currentTarget.style.display='none' }}
            />
          </div>
        )}

        <div className="form-row" style={{marginBottom:14}}>
          <div className="form-group">
            <label className="form-label">Full Name <span className="required">*</span></label>
            <input className="form-input" value={name} onChange={e=>setName(e.target.value)} placeholder="Student name" />
          </div>
        </div>

        <div className="form-row3" style={{marginBottom:14}}>
          <div className="form-group">
            <label className="form-label">Class <span className="required">*</span></label>
            <select className="form-select" value={classVal} onChange={e=>setClassVal(e.target.value)}>
              <option value="">Select class</option>
              {classList.map(c=><option key={c} value={c}>{c}</option>)}
            </select>
          </div>
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
              <input className="form-input" value={section}
                onChange={e=>setSection(e.target.value.toUpperCase())}
                placeholder="Section" maxLength={3}/>
            )}
          </div>
        </div>

        <div className="form-row" style={{marginBottom:20}}>
          <div className="form-group">
            <label className="form-label">Roll Number</label>
            <input className="form-input" type="number" min="1" value={rollNo}
              onChange={e=>setRollNo(e.target.value)} placeholder="Roll number" />
          </div>
        </div>

        <div style={{display:'flex',gap:10,justifyContent:'flex-end'}}>
          <button className="btn btn-ghost" onClick={onClose} disabled={saving}>Cancel</button>
          <button className="btn btn-primary" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Students tab ──────────────────────────────────────────────────────────────
function StudentsTab() {
  const [students,   setStudents]   = useState([])
  const [classes,    setClasses]    = useState([])
  const [secMap,     setSecMap]     = useState({})
  const [activeClass,setActiveClass]= useState('')
  const [activeSec,  setActiveSec]  = useState('')
  const [activeStream,setActiveStream]=useState('')
  const [search,     setSearch]     = useState('')
  const [editTarget, setEditTarget] = useState(null) // student being edited
  const toast = useToast()

  const loadAll = useCallback(async () => {
    const [sr,cr] = await Promise.all([studentsApi.list(), classesApi.list()])
    if (sr?.ok) setStudents(sr.data)
    const cls = cr?.ok ? cr.data : []; setClasses(cls)
    const map={}
    for (const c of cls) {
      if (STREAM_CLASSES.has(c)) {
        for (const stream of FIXED_STREAMS) {
          const r = await sectionsApi.list(c,stream)
          map[`${c}::${stream}`] = r?.ok ? r.data : []
        }
      } else {
        const r = await sectionsApi.list(c,'')
        map[c] = r?.ok ? r.data : []
      }
    }
    setSecMap(map)
  },[])

  useEffect(()=>{loadAll()},[loadAll])
  useEffect(()=>{setActiveSec('');setActiveStream('')},[activeClass])
  useEffect(()=>{setActiveSec('')},[activeStream])

  const remove = async (sid, name) => {
    if (!confirm(`Remove ${name} (${sid})?\nThis deletes their face data.`)) return
    const res = await studentsApi.remove(sid)
    if (res?.data?.ok) { toast(`${name} removed.`,'success'); setStudents(p=>p.filter(s=>s.student_id!==sid)) }
  }

  const isStreamClass = activeClass && STREAM_CLASSES.has(activeClass)
  const currentSections = isStreamClass && activeStream
    ? (secMap[`${activeClass}::${activeStream}`]||[])
    : (!isStreamClass && activeClass)
      ? (secMap[activeClass]||[])
      : []

  const filtered = students.filter(s => {
    const matchClass  = !activeClass  || s.class_name===activeClass
    const matchStream = !isStreamClass||!activeStream||s.stream===activeStream
    const matchSec    = !activeSec    || s.section===activeSec
    const matchSearch = !search || [s.name,s.student_id,s.class_name].join(' ').toLowerCase().includes(search.toLowerCase())
    return matchClass && matchStream && matchSec && matchSearch
  })

  return (
    <>
      {editTarget && (
        <EditStudentModal
          student={editTarget}
          classList={classes}
          onClose={() => setEditTarget(null)}
          onSaved={() => { setEditTarget(null); loadAll() }}
        />
      )}
      <div className="card">
        <div className="card-title flex-sb" style={{flexWrap:'wrap',gap:10}}>
          <span><span className="card-icon">◊</span> Enrolled Students ({students.length})</span>
          <input className="form-input" style={{maxWidth:180,padding:'6px 10px',fontSize:12.5}}
            placeholder="Search..." value={search} onChange={e=>setSearch(e.target.value)}/>
        </div>

        {/* Class chips */}
        <div className="chips" style={{marginBottom:8}}>
          <button className={`chip${!activeClass?' active':''}`} onClick={()=>setActiveClass('')}>All</button>
          {classes.map(c=>(
            <button key={c} className={`chip${activeClass===c?' active':''}`} onClick={()=>setActiveClass(c)}>{c}</button>
          ))}
        </div>

        {/* Stream chips — XI/XII only */}
        {isStreamClass && (
          <div className="chips" style={{marginBottom:8}}>
            <button className={`chip${!activeStream?' active':''}`} style={{fontSize:11,padding:'4px 12px'}} onClick={()=>setActiveStream('')}>All Streams</button>
            {FIXED_STREAMS.map(s=>(
              <button key={s} className={`chip${activeStream===s?' active':''}`} style={{fontSize:11,padding:'4px 12px'}} onClick={()=>setActiveStream(s)}>{s}</button>
            ))}
          </div>
        )}

        {/* Section chips */}
        {currentSections.length>0 && (
          <div className="chips" style={{marginBottom:16}}>
            <button className={`chip${!activeSec?' active':''}`} style={{fontSize:11,padding:'4px 12px'}} onClick={()=>setActiveSec('')}>All Sections</button>
            {currentSections.map(s=>(
              <button key={s} className={`chip${activeSec===s?' active':''}`} style={{fontSize:11,padding:'4px 12px'}} onClick={()=>setActiveSec(s)}>Section {s}</button>
            ))}
          </div>
        )}

        <div className="table-wrap" style={{maxHeight:540,overflowY:'auto'}}>
          <table>
            <thead><tr><th>Name</th><th>Student ID</th><th>Class</th><th>Stream</th><th>Sec</th><th>Roll</th><th>Enrolled On</th><th>Face Data</th><th style={{minWidth:110}}></th></tr></thead>
            <tbody>
              {filtered.length===0 ? <tr><td colSpan={9} className="empty" style={{padding:40}}>No students found.</td></tr>
                : filtered.map(s=>(
                  <tr key={s.student_id}>
                    <td><div className="flex">
                      {s.photo_path ? (
                        <img
                          src={studentsApi.photoUrl(s.student_id)}
                          alt={s.name}
                          style={{
                            width:30, height:30, borderRadius:'50%', objectFit:'cover',
                            flexShrink:0, border:'1px solid var(--border)',
                          }}
                          onError={e=>{
                            e.currentTarget.style.display='none'
                            e.currentTarget.nextSibling?.style && (e.currentTarget.nextSibling.style.display='flex')
                          }}
                        />
                      ) : null}
                      <div className="log-av" style={{
                        width:30, height:30, fontSize:11,
                        display: s.photo_path ? 'none' : 'flex',
                      }}>{(s.name||'XX').slice(0,2).toUpperCase()}</div>
                      <span className="td-name">{s.name}</span>
                    </div></td>
                    <td style={{fontFamily:'Space Mono,monospace',fontSize:12,color:'var(--text3)'}}>{s.student_id}</td>
                    <td><span className="badge badge-blue">{s.class_name}</span></td>
                    <td style={{fontSize:12,color:'var(--text3)'}}>{s.stream||'—'}</td>
                    <td style={{fontFamily:'Space Mono,monospace',fontSize:12}}>{s.section}</td>
                    <td style={{fontFamily:'Space Mono,monospace',fontSize:12}}>{s.roll_no}</td>
                    <td style={{fontSize:12,color:'var(--text3)'}}>{(s.enrolled_at||'').slice(0,10)}</td>
                    <td><span className={`badge ${s.photo_path?'badge-green':'badge-red'}`}>{s.photo_path?'Enrolled':'No face data'}</span></td>
                    <td>
                      <div style={{display:'flex',gap:6}}>
                        <button className="btn btn-ghost btn-sm"
                          onClick={()=>setEditTarget(s)}
                          style={{fontSize:11,padding:'3px 10px'}}
                        >✏ Edit</button>
                        <button className="btn btn-danger btn-sm"
                          onClick={()=>remove(s.student_id,s.name)}
                        >Remove</button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
