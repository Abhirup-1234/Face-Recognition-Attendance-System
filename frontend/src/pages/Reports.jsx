import { useState, useEffect, useCallback } from 'react'
import { attendance as attendanceApi, reports as reportsApi, classes as classesApi } from '../api'

function today() { return new Date().toISOString().split('T')[0] }

function confClass(c) {
  if (c >= 0.45) return 'badge-green'
  if (c >= 0.32) return 'badge-yellow'
  return 'badge-red'
}

export default function Reports() {
  const [date,     setDate]     = useState(today())
  const [classVal, setClassVal] = useState('')
  const [records,  setRecords]  = useState([])
  const [classes,  setClasses]  = useState([])
  const [loading,  setLoading]  = useState(false)
  const [search,   setSearch]   = useState('')

  useEffect(() => {
    classesApi.list().then(r => r?.ok && setClasses(r.data))
  }, [])

  const loadData = useCallback(async () => {
    setLoading(true)
    const res = await attendanceApi.get(date, classVal)
    if (res?.ok) setRecords(res.data)
    setLoading(false)
  }, [date, classVal])

  useEffect(() => { loadData() }, [loadData])

  const filtered = records.filter(r => {
    if (!search) return true
    const q = search.toLowerCase()
    return r.name?.toLowerCase().includes(q) ||
           r.student_id?.toLowerCase().includes(q) ||
           r.class_name?.toLowerCase().includes(q)
  })

  // KPIs
  const uniqueStudents = new Set(records.map(r => r.student_id)).size
  const avgConf = records.length > 0
    ? (records.reduce((a, r) => a + (r.confidence || 0), 0) / records.length).toFixed(3)
    : '—'

  return (
    <div>
      {/* Filters */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title"><span className="card-icon">▦</span> Filter Records</div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="form-group" style={{ flex: '0 0 220px' }}>
            <label className="form-label">📅 Date</label>
            <input
              type="date"
              className="form-input"
              value={date}
              onChange={e => setDate(e.target.value)}
              style={{ cursor: 'pointer', colorScheme: 'dark' }}
            />
          </div>
          <div className="form-group" style={{ flex: '0 0 180px' }}>
            <label className="form-label">Class</label>
            <select className="form-select" value={classVal} onChange={e => setClassVal(e.target.value)}>
              <option value="">All Classes</option>
              {classes.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div style={{ display: 'flex', gap: 8, paddingBottom: 1 }}>
            <button className="btn btn-primary" onClick={loadData} disabled={loading}>
              {loading ? <span className="spin" /> : '🔍'} Load
            </button>
            <a className="btn btn-ghost" href={reportsApi.pdfUrl(date, classVal)} download>↓ PDF</a>
            <a className="btn btn-ghost" href={reportsApi.excelUrl(date, classVal)} download>↓ Excel</a>
          </div>
        </div>
      </div>

      {/* KPIs */}
      {records.length > 0 && (
        <div className="g4" style={{ marginBottom: 16 }}>
          <div className="statcard sc-blue">
            <div className="stat-label">Unique Present</div>
            <div className="stat-value">{uniqueStudents}</div>
          </div>
          <div className="statcard sc-green">
            <div className="stat-label">Total Records</div>
            <div className="stat-value">{records.length}</div>
          </div>
          <div className="statcard sc-orange">
            <div className="stat-label">Date</div>
            <div className="stat-value" style={{ fontSize: 16 }}>{date}</div>
          </div>
          <div className="statcard sc-purple">
            <div className="stat-label">Avg Similarity</div>
            <div className="stat-value" style={{ fontSize: 22 }}>{avgConf}</div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="card">
        <div className="card-title flex-sb">
          <span><span className="card-icon">▦</span> Records</span>
          <input
            className="form-input"
            style={{ maxWidth: 180, padding: '6px 10px', fontSize: 12.5 }}
            placeholder="Filter rows..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        {loading ? (
          <div className="empty"><div className="spin" /></div>
        ) : filtered.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">📋</div>
            <div className="empty-title">No records found</div>
            <div className="empty-sub">Select a date and click Load.</div>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>ID</th>
                  <th>Class</th>
                  <th>Sec.</th>
                  <th>Roll</th>
                  <th>Time</th>
                  <th>Camera</th>
                  <th>Similarity</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => (
                  <tr key={i}>
                    <td>
                      <div className="flex">
                        <div className="log-av" style={{ width: 28, height: 28, fontSize: 10 }}>
                          {(r.name || 'XX').slice(0, 2).toUpperCase()}
                        </div>
                        <span className="td-name">{r.name}</span>
                      </div>
                    </td>
                    <td style={{ fontFamily: 'Space Mono, monospace', fontSize: 12, color: 'var(--text3)' }}>{r.student_id}</td>
                    <td><span className="badge badge-blue">{r.class_name}</span></td>
                    <td style={{ fontSize: 13, color: 'var(--text3)' }}>{r.section}</td>
                    <td style={{ fontFamily: 'Space Mono, monospace', fontSize: 12 }}>{r.roll_no}</td>
                    <td style={{ fontFamily: 'Space Mono, monospace', fontSize: 12 }}>
                      {(r.detected_at || '').slice(11, 19)}
                    </td>
                    <td style={{ fontFamily: 'Space Mono, monospace', fontSize: 12, color: 'var(--text3)' }}>{r.camera_id}</td>
                    <td>
                      <span className={`badge ${confClass(r.confidence || 0)} mono`}>
                        {(r.confidence || 0).toFixed(3)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
