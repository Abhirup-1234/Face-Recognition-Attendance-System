import { useState, useEffect, useCallback } from 'react'
import { classes as classesApi, classrooms as classroomsApi, students as studentsApi, cameras as camerasApi } from '../api'
import { useToast } from '../context/ToastContext'

export default function Manage() {
  const [tab, setTab] = useState('classes')
  return (
    <div>
      <div className="tabbar" style={{ maxWidth: 500, marginBottom: 20 }}>
        <button className={`tabbtn${tab === 'classes'  ? ' active' : ''}`} onClick={() => setTab('classes')}>⌾ Classes</button>
        <button className={`tabbtn${tab === 'cameras'  ? ' active' : ''}`} onClick={() => setTab('cameras')}>📷 Camera Assignments</button>
        <button className={`tabbtn${tab === 'students' ? ' active' : ''}`} onClick={() => setTab('students')}>◊ Students</button>
      </div>
      {tab === 'classes'  && <ClassesTab />}
      {tab === 'cameras'  && <CamerasTab />}
      {tab === 'students' && <StudentsTab />}
    </div>
  )
}

function ClassesTab() {
  const [classList, setClassList] = useState([])
  const [students,  setStudents]  = useState([])
  const [newClass,  setNewClass]  = useState('')
  const toast = useToast()

  useEffect(() => {
    classesApi.list().then(r => r?.ok && setClassList(r.data))
    studentsApi.list().then(r => r?.ok && setStudents(r.data))
  }, [])

  const addClass = async () => {
    const name = newClass.trim()
    if (!name) { toast('Enter a class name.', 'warning'); return }
    const res = await classesApi.add(name)
    if (res?.data?.ok) {
      toast(`${name} added.`, 'success')
      setNewClass('')
      classesApi.list().then(r => r?.ok && setClassList(r.data))
    } else {
      toast(res?.data?.error || 'Failed.', 'error')
    }
  }

  const deleteClass = async (name) => {
    const count = students.filter(s => s.class_name === name).length
    const msg = count > 0
      ? `${name} has ${count} enrolled student(s).\nRemoving only removes it from the dropdown — students are NOT deleted. Continue?`
      : `Remove class "${name}" from the dropdown?`
    if (!confirm(msg)) return
    const res = await classesApi.remove(name)
    if (res?.data?.ok) {
      toast(`${name} removed.`, 'success')
      setClassList(prev => prev.filter(c => c !== name))
    }
  }

  return (
    <div className="g2" style={{ gap: 20, alignItems: 'start' }}>
      <div className="card">
        <div className="card-title"><span className="card-icon">⌾</span> Add New Class</div>
        <p style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 16 }}>
          Use consistent naming like <code>10-A</code>, <code>11-Science</code>, or <code>12-Commerce-B</code>.
        </p>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ flex: 1, minWidth: 180 }}>
            <label className="form-label">Class Name</label>
            <input
              className="form-input" placeholder="e.g. 10-A or 11-Science"
              value={newClass} onChange={e => setNewClass(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addClass()}
            />
          </div>
          <button className="btn btn-primary" onClick={addClass}>+ Add Class</button>
        </div>
        <div style={{ marginTop: 20, fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--text3)', marginBottom: 10 }}>
          Naming Examples
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 16px', fontSize: 12.5, color: 'var(--text3)' }}>
          {[['10-A','Class 10, Sec A'],['10-B','Class 10, Sec B'],['11-Science','Class 11 Science'],['11-Commerce','Class 11 Commerce'],['11-Humanities','Class 11 Humanities'],['12-Science-A','Class 12 Sci, Sec A']].map(([n, d]) => (
            <div key={n}><code>{n}</code> — {d}</div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-title flex-sb">
          <span><span className="card-icon">▦</span> Current Classes</span>
          <span style={{ fontSize: 12, color: 'var(--text3)' }}>{classList.length} class(es)</span>
        </div>
        {classList.length === 0 ? (
          <div className="muted">No classes yet. Add one.</div>
        ) : (
          classList.map(cls => {
            const count = students.filter(s => s.class_name === cls).length
            return (
              <div key={cls} className="flex-sb" style={{ padding: '9px 0', borderBottom: '1px solid var(--border)' }}>
                <div className="flex">
                  <span style={{ fontSize: 13.5, fontWeight: 500 }}>{cls}</span>
                  {count > 0 && <span className="badge badge-blue">{count} student(s)</span>}
                </div>
                <button className="btn btn-danger btn-sm" onClick={() => deleteClass(cls)}>Remove</button>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

function CamerasTab() {
  const [camIds,    setCamIds]    = useState([])
  const [classes,   setClasses]   = useState([])
  const [classrooms,setClassrooms]= useState([])
  const [saved,     setSaved]     = useState({})
  const toast = useToast()

  useEffect(() => {
    camerasApi.stats().then(r => r?.ok && setCamIds(Object.keys(r.data)))
    classesApi.list().then(r => r?.ok && setClasses(r.data))
    classroomsApi.list().then(r => {
      if (r?.ok) {
        const map = {}
        r.data.forEach(c => { map[c.camera_id] = c })
        setClassrooms(map)
      }
    })
  }, [])

  const getField = (camId, field, fallback = '') => {
    const key = `${camId}-${field}`
    if (saved[key] !== undefined) return saved[key]
    const room = classrooms[camId] || {}
    if (field === 'room_id')    return room.classroom_id || camId.replace('CAM-', 'Room ')
    if (field === 'class_name') return room.class_name || ''
    if (field === 'floor')      return room.floor || 1
    return fallback
  }

  const setField = (camId, field, val) => setSaved(prev => ({ ...prev, [`${camId}-${field}`]: val }))

  const saveRoom = async camId => {
    const roomId = getField(camId, 'room_id')
    if (!roomId) { toast('Enter a Room ID.', 'warning'); return }
    const res = await classroomsApi.save(roomId, {
      camera_id:  camId,
      class_name: getField(camId, 'class_name'),
      floor:      getField(camId, 'floor'),
    })
    if (res?.data?.ok) toast(`Saved assignment for ${camId}.`, 'success')
    else toast('Failed to save.', 'error')
  }

  return (
    <div className="card">
      <div className="card-title"><span className="card-icon">📷</span> Camera to Classroom Assignment</div>
      <p style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 20 }}>
        Assign each camera to a physical classroom. This information appears in attendance reports.
      </p>
      {camIds.length === 0 ? (
        <div className="muted">No cameras configured.</div>
      ) : (
        camIds.map(camId => (
          <div key={camId} style={{ padding: '16px 0', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--secondary)', marginBottom: 12, fontFamily: 'Space Mono, monospace' }}>
              {camId}
            </div>
            <div className="form-row3">
              <div className="form-group">
                <label className="form-label">Room / Classroom ID</label>
                <input className="form-input" placeholder="e.g. Room 101"
                  value={getField(camId, 'room_id')}
                  onChange={e => setField(camId, 'room_id', e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Assigned Class</label>
                <select className="form-select"
                  value={getField(camId, 'class_name')}
                  onChange={e => setField(camId, 'class_name', e.target.value)}>
                  <option value="">-- Not assigned --</option>
                  {classes.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Floor</label>
                <input className="form-input" type="number" min="0" max="20"
                  value={getField(camId, 'floor', 1)}
                  onChange={e => setField(camId, 'floor', e.target.value)} />
              </div>
            </div>
            <div style={{ marginTop: 10 }}>
              <button className="btn btn-primary btn-sm" onClick={() => saveRoom(camId)}>Save</button>
            </div>
          </div>
        ))
      )}
    </div>
  )
}

function StudentsTab() {
  const [students,      setStudents]      = useState([])
  const [classes,       setClasses]       = useState([])
  const [activeClass,   setActiveClass]   = useState('')
  const [search,        setSearch]        = useState('')
  const toast = useToast()

  useEffect(() => {
    studentsApi.list().then(r => r?.ok && setStudents(r.data))
    classesApi.list().then(r => r?.ok && setClasses(r.data))
  }, [])

  const remove = async (sid, name) => {
    if (!confirm(`Remove ${name} (${sid})?\nThis deletes their face data.`)) return
    const res = await studentsApi.remove(sid)
    if (res?.data?.ok) {
      toast(`${name} removed.`, 'success')
      setStudents(prev => prev.filter(s => s.student_id !== sid))
    }
  }

  const filtered = students.filter(s => {
    const matchClass = !activeClass || s.class_name === activeClass
    const matchSearch = !search || [s.name, s.student_id, s.class_name].join(' ').toLowerCase().includes(search.toLowerCase())
    return matchClass && matchSearch
  })

  // Per-class summary
  const classCounts = {}
  students.forEach(s => { classCounts[s.class_name] = (classCounts[s.class_name] || 0) + 1 })

  return (
    <div className="card">
      <div className="card-title flex-sb" style={{ flexWrap: 'wrap', gap: 10 }}>
        <span><span className="card-icon">◊</span> Enrolled Students ({students.length})</span>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <div className="chips">
            <button className={`chip${!activeClass ? ' active' : ''}`} onClick={() => setActiveClass('')}>All</button>
            {classes.map(c => (
              <button key={c} className={`chip${activeClass === c ? ' active' : ''}`} onClick={() => setActiveClass(c)}>{c}</button>
            ))}
          </div>
          <input
            className="form-input" style={{ maxWidth: 180, padding: '6px 10px', fontSize: 12.5 }}
            placeholder="Search name / ID..." value={search} onChange={e => setSearch(e.target.value)}
          />
        </div>
      </div>

      <div className="table-wrap" style={{ maxHeight: 600, overflowY: 'auto' }}>
        <table>
          <thead>
            <tr><th>Name</th><th>Student ID</th><th>Class</th><th>Section</th><th>Roll No.</th><th>Enrolled On</th><th>Face Data</th><th></th></tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan={8} className="empty" style={{ padding: 40 }}>No students found.</td></tr>
            ) : (
              filtered.map(s => (
                <tr key={s.student_id}>
                  <td>
                    <div className="flex">
                      <div className="log-av" style={{ width: 30, height: 30, fontSize: 11 }}>
                        {(s.name || 'XX').slice(0, 2).toUpperCase()}
                      </div>
                      <span className="td-name">{s.name}</span>
                    </div>
                  </td>
                  <td style={{ fontFamily: 'Space Mono, monospace', fontSize: 12, color: 'var(--text3)' }}>{s.student_id}</td>
                  <td><span className="badge badge-blue">{s.class_name}</span></td>
                  <td style={{ fontSize: 13, color: 'var(--text3)' }}>{s.section}</td>
                  <td style={{ fontFamily: 'Space Mono, monospace', fontSize: 12 }}>{s.roll_no}</td>
                  <td style={{ fontSize: 12, color: 'var(--text3)' }}>{(s.enrolled_at || '').slice(0, 10)}</td>
                  <td><span className={`badge ${s.photo_path ? 'badge-green' : 'badge-red'}`}>{s.photo_path ? 'Enrolled' : 'No face data'}</span></td>
                  <td>
                    <button className="btn btn-danger btn-sm" onClick={() => remove(s.student_id, s.name)}>Remove</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {students.length > 0 && (
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 14, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {Object.entries(classCounts).map(([cls, cnt]) => (
            <span key={cls} className="badge badge-blue" style={{ fontSize: 12 }}>{cls}: {cnt}</span>
          ))}
        </div>
      )}
    </div>
  )
}
