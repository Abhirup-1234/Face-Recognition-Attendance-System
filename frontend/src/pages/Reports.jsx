import { useState, useEffect, useCallback } from 'react'
import {
  attendance as attendanceApi,
  reports as reportsApi,
  classes as classesApi,
  streams as streamsApi,
  sections as sectionsApi,
} from '../api'

function today() { return new Date().toISOString().split('T')[0] }

// Confidence color — green ≥ 0.45, amber ≥ 0.32, red below
function confColor(c) {
  if (c >= 0.45) return { color: '#4ade80', bg: 'rgba(22,163,74,.12)',  border: 'rgba(22,163,74,.25)' }
  if (c >= 0.32) return { color: '#fbbf24', bg: 'rgba(234,179,8,.12)',  border: 'rgba(234,179,8,.25)' }
  return           { color: '#f87171', bg: 'rgba(239,68,68,.12)',  border: 'rgba(239,68,68,.25)' }
}

// Thin colored confidence bar
function ConfBar({ value }) {
  const { color } = confColor(value)
  const pct = Math.min(100, Math.round(value * 100))
  return (
    <div style={{ display:'flex', alignItems:'center', gap:8 }}>
      <div style={{ flex:1, height:3, background:'rgba(255,255,255,.07)', borderRadius:99, overflow:'hidden' }}>
        <div style={{ width:`${pct}%`, height:'100%', background:color, borderRadius:99,
                      transition:'width .4s ease', boxShadow:`0 0 6px ${color}` }} />
      </div>
      <span style={{ fontSize:11.5, fontFamily:'Space Mono,monospace', color, fontWeight:700, minWidth:36, textAlign:'right' }}>
        {value.toFixed(3)}
      </span>
    </div>
  )
}

export default function Reports() {
  const [date,        setDate]        = useState(today())
  const [classVal,    setClassVal]    = useState('')
  const [streamVal,   setStreamVal]   = useState('')
  const [sectionVal,  setSectionVal]  = useState('')
  const [classList,   setClassList]   = useState([])
  const [streamList,  setStreamList]  = useState([])
  const [sectionList, setSectionList] = useState([])
  const [records,     setRecords]     = useState([])
  const [loading,     setLoading]     = useState(false)
  const [search,      setSearch]      = useState('')

  useEffect(() => { classesApi.list().then(r => r?.ok && setClassList(r.data)) }, [])

  useEffect(() => {
    setStreamVal(''); setSectionVal(''); setStreamList([]); setSectionList([])
    if (!classVal) return
    streamsApi.list(classVal).then(r => {
      if (r?.ok && r.data.length > 0) setStreamList(r.data)
      else sectionsApi.list(classVal,'').then(sr => { if (sr?.ok) setSectionList(sr.data) })
    })
  }, [classVal])

  useEffect(() => {
    setSectionVal(''); setSectionList([])
    if (!classVal || !streamVal) return
    sectionsApi.list(classVal, streamVal).then(r => { if (r?.ok) setSectionList(r.data) })
  }, [classVal, streamVal])

  const loadData = useCallback(async () => {
    setLoading(true)
    const res = await attendanceApi.get(date, classVal, streamVal, sectionVal)
    if (res?.ok) setRecords(res.data)
    setLoading(false)
  }, [date, classVal, streamVal, sectionVal])

  useEffect(() => { loadData() }, [loadData])

  // Deduplicate: first detection per student for the summary
  const unique = Object.values(
    records.reduce((acc, r) => {
      if (!acc[r.student_id]) acc[r.student_id] = r
      return acc
    }, {})
  )

  const avgConf = unique.length > 0
    ? unique.reduce((a, r) => a + (r.confidence||0), 0) / unique.length
    : 0

  const filtered = records.filter(r => {
    if (!search) return true
    const q = search.toLowerCase()
    return r.name?.toLowerCase().includes(q) ||
           r.student_id?.toLowerCase().includes(q) ||
           r.class_name?.toLowerCase().includes(q)
  })

  const needsStream = streamList.length > 0

  // Format the active filter label for the header
  const filterLabel = [
    classVal || 'All Classes',
    streamVal,
    sectionVal ? `Section ${sectionVal}` : ''
  ].filter(Boolean).join(' · ')

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:20 }}>

      {/* ── Filter bar ────────────────────────────────────────────────────── */}
      <div className="card" style={{ padding:'16px 20px' }}>
        <div style={{ display:'flex', gap:12, flexWrap:'wrap', alignItems:'flex-end' }}>

          {/* Date */}
          <div className="form-group" style={{ flex:'0 0 180px' }}>
            <label className="form-label">Date</label>
            <input type="date" className="form-input" value={date}
              onChange={e => setDate(e.target.value)}
              style={{ cursor:'pointer', colorScheme:'dark' }} />
          </div>

          {/* Class */}
          <div className="form-group" style={{ flex:'0 0 130px' }}>
            <label className="form-label">Class</label>
            <select className="form-select" value={classVal} onChange={e => setClassVal(e.target.value)}>
              <option value="">All</option>
              {classList.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          {/* Stream */}
          {classVal && needsStream && (
            <div className="form-group" style={{ flex:'0 0 150px' }}>
              <label className="form-label">Stream</label>
              <select className="form-select" value={streamVal} onChange={e => setStreamVal(e.target.value)}>
                <option value="">All Streams</option>
                {streamList.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          )}

          {/* Section */}
          {classVal && sectionList.length > 0 && (
            <div className="form-group" style={{ flex:'0 0 130px' }}>
              <label className="form-label">Section</label>
              <select className="form-select" value={sectionVal} onChange={e => setSectionVal(e.target.value)}>
                <option value="">All</option>
                {sectionList.map(s => <option key={s} value={s}>Sec {s}</option>)}
              </select>
            </div>
          )}

          {/* Actions */}
          <div style={{ display:'flex', gap:8, marginLeft:'auto', paddingBottom:1 }}>
            <button className="btn btn-primary" onClick={loadData} disabled={loading} style={{ minWidth:90 }}>
              {loading ? <span className="spin" /> : '↻ Refresh'}
            </button>
            <a className="btn btn-ghost"
              href={reportsApi.pdfUrl(date, classVal, streamVal, sectionVal)} download>
              ↓ PDF
            </a>
            <a className="btn btn-ghost"
              href={reportsApi.excelUrl(date, classVal, streamVal, sectionVal)} download>
              ↓ Excel
            </a>
          </div>
        </div>
      </div>

      {/* ── Summary row ───────────────────────────────────────────────────── */}
      <div className="g4">
        <div className="statcard sc-blue">
          <div className="stat-label">Students Present</div>
          <div className="stat-value">{unique.length}</div>
          <div className="stat-sub">{filterLabel}</div>
          <div className="stat-icon">🎓</div>
        </div>
        <div className="statcard sc-green">
          <div className="stat-label">Total Detections</div>
          <div className="stat-value">{records.length}</div>
          <div className="stat-sub">inc. multiple per student</div>
          <div className="stat-icon">📸</div>
        </div>
        <div className="statcard sc-purple">
          <div className="stat-label">Avg Confidence</div>
          <div className="stat-value" style={{ fontSize:28 }}>
            {unique.length > 0 ? avgConf.toFixed(3) : '—'}
          </div>
          <div className="stat-sub">ArcFace cosine similarity</div>
          <div className="stat-icon">🎯</div>
        </div>
        <div className="statcard sc-orange">
          <div className="stat-label">Date</div>
          <div className="stat-value" style={{ fontSize:18, letterSpacing:'-0.5px' }}>
            {new Date(date + 'T00:00').toLocaleDateString('en-IN', { day:'numeric', month:'short' })}
          </div>
          <div className="stat-sub">{new Date(date + 'T00:00').toLocaleDateString('en-IN', { weekday:'long', year:'numeric' })}</div>
          <div className="stat-icon">📅</div>
        </div>
      </div>

      {/* ── Table ─────────────────────────────────────────────────────────── */}
      <div className="card" style={{ padding:0, overflow:'hidden' }}>

        {/* Table header bar */}
        <div style={{
          display:'flex', alignItems:'center', justifyContent:'space-between',
          padding:'14px 20px', borderBottom:'1px solid var(--border)',
        }}>
          <div>
            <div style={{ fontSize:14, fontWeight:700, color:'var(--text)' }}>Attendance Records</div>
            <div style={{ fontSize:12, color:'var(--text3)', marginTop:2 }}>
              {filtered.length} record(s) · {date}
              {filterLabel !== 'All Classes' ? ` · ${filterLabel}` : ''}
            </div>
          </div>
          <input
            className="form-input"
            style={{ maxWidth:200, padding:'7px 12px', fontSize:12.5 }}
            placeholder="Search student..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        {/* Table body */}
        {loading ? (
          <div className="empty"><div className="spin" /></div>
        ) : filtered.length === 0 ? (
          <div className="empty">
            <div className="empty-icon" style={{ fontSize:44, opacity:.3 }}>📋</div>
            <div className="empty-title">No records found</div>
            <div className="empty-sub">
              {records.length === 0
                ? 'No attendance data for this date / filter.'
                : 'No results match your search.'}
            </div>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ paddingLeft:20 }}>Student</th>
                  <th>Class</th>
                  <th>Stream</th>
                  <th>Section</th>
                  <th>Roll</th>
                  <th>Time</th>
                  <th>Camera</th>
                  <th style={{ minWidth:160 }}>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => {
                  const conf = r.confidence || 0
                  const { color: cc } = confColor(conf)
                  return (
                    <tr key={i}>
                      <td style={{ paddingLeft:20 }}>
                        <div className="flex">
                          <div className="log-av" style={{ width:32, height:32, fontSize:11, flexShrink:0 }}>
                            {(r.name||'??').slice(0,2).toUpperCase()}
                          </div>
                          <div>
                            <div className="td-name" style={{ fontSize:13.5 }}>{r.name}</div>
                            <div style={{ fontSize:11, color:'var(--text3)', fontFamily:'Space Mono,monospace' }}>
                              {r.student_id}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="badge badge-blue">{r.class_name}</span>
                      </td>
                      <td style={{ fontSize:12, color:'var(--text3)' }}>
                        {r.stream || <span style={{ opacity:.3 }}>—</span>}
                      </td>
                      <td>
                        {r.section
                          ? <span style={{ fontFamily:'Space Mono,monospace', fontSize:12, fontWeight:700, color:'var(--secondary)' }}>
                              {r.section}
                            </span>
                          : <span style={{ opacity:.3 }}>—</span>}
                      </td>
                      <td style={{ fontFamily:'Space Mono,monospace', fontSize:12, color:'var(--text2)' }}>
                        {r.roll_no}
                      </td>
                      <td style={{ fontFamily:'Space Mono,monospace', fontSize:12, color:'var(--text2)' }}>
                        {(r.detected_at||'').slice(11,19)}
                      </td>
                      <td style={{ fontFamily:'Space Mono,monospace', fontSize:11, color:'var(--text3)' }}>
                        {r.camera_id}
                      </td>
                      <td style={{ paddingRight:20 }}>
                        <ConfBar value={conf} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Table footer */}
        {filtered.length > 0 && (
          <div style={{
            padding:'10px 20px', borderTop:'1px solid var(--border)',
            display:'flex', justifyContent:'space-between', alignItems:'center',
            background:'rgba(255,255,255,.02)',
          }}>
            <span style={{ fontSize:12, color:'var(--text3)' }}>
              Showing {filtered.length} of {records.length} record(s)
            </span>
            <div style={{ display:'flex', gap:12, fontSize:12, color:'var(--text3)' }}>
              <span>
                <span style={{ color:'#4ade80' }}>●</span> ≥0.45 High
              </span>
              <span>
                <span style={{ color:'#fbbf24' }}>●</span> ≥0.32 Medium
              </span>
              <span>
                <span style={{ color:'#f87171' }}>●</span> Low
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
