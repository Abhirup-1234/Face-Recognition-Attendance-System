import { useState, useEffect, useRef } from 'react'
import { settings as settingsApi, attendance as attendanceApi, system as systemApi } from '../api'
import { useToast } from '../context/ToastContext'

function Toggle({ value, onChange, label, sub }) {
  return (
    <div className="toggle-wrap" onClick={() => onChange(!value)}>
      <div className={`toggle${value ? ' on' : ''}`} />
      <div>
        <div className="toggle-label">{label}</div>
        {sub && <div className="toggle-sub">{sub}</div>}
      </div>
    </div>
  )
}

function RangeRow({ label, value, min, max, step, onChange, leftLabel, rightLabel, desc, format }) {
  const display = format ? format(value) : value
  return (
    <div className="range-row">
      <div className="range-header">
        <span className="range-name">{label}</span>
        <span className="range-val">{display}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value))} />
      {(leftLabel || rightLabel) && (
        <div className="range-labels"><span>{leftLabel}</span><span>{rightLabel}</span></div>
      )}
      {desc && <div className="range-desc">{desc}</div>}
    </div>
  )
}

function today() { return new Date().toISOString().split('T')[0] }

export default function Settings() {
  const toast = useToast()

  const [s, setS] = useState({
    REC_THRESHOLD:          0.50,
    DET_THRESH:             0.50,
    CONFIRM_FRAMES:         3,
    EMBEDDINGS_PER_STUDENT: 20,
    USE_DSHOW:              false,
    PROCESS_EVERY_N:        5,
    STREAM_FPS:             10,
    FRAME_WIDTH:            1280,
    FRAME_HEIGHT:           720,
    ENABLE_CLAHE:           true,
    CLAHE_CLIP_LIMIT:       2.5,
    ENABLE_DENOISE:         true,
    SUPER_RES_SCALE:        2,
    SCHOOL_NAME:            'Narula Public School',
    ADMIN_DISPLAY_NAME:     'Administrator',
  })
  const [sysInfo,   setSysInfo]   = useState({})
  const [newPass,   setNewPass]   = useState('')
  const [confPass,  setConfPass]  = useState('')
  const [saving,    setSaving]    = useState(false)
  const [saveMsg,   setSaveMsg]   = useState('')
  const [backing,   setBacking]   = useState(false)
  const [restoring, setRestoring] = useState(false)
  const restoreRef = useRef(null)

  useEffect(() => {
    fetch('/api/settings', { credentials: 'include' })
      .then(r => r.json())
      .then(d => { if (d) setS(prev => ({ ...prev, ...d })) })
      .catch(() => {})
    fetch('/api/stats', { credentials: 'include' })
      .then(r => r.json())
      .then(d => setSysInfo({ enrolled: d.enrolled || 0 }))
      .catch(() => {})
  }, [])

  const set = (key, val) => setS(prev => ({ ...prev, [key]: val }))

  const save = async () => {
    setSaving(true)
    const res = await settingsApi.save(s)
    if (res?.data?.ok) {
      toast('Settings saved successfully.', 'success')
      setSaveMsg('Saved')
    } else {
      toast('Failed to save settings.', 'error')
      setSaveMsg('Failed')
    }
    setSaving(false)
    setTimeout(() => setSaveMsg(''), 4000)
  }

  const changePassword = async () => {
    if (!newPass) { toast('Enter a new password.', 'warning'); return }
    if (newPass !== confPass) { toast('Passwords do not match.', 'error'); return }
    if (newPass.length < 6) { toast('Password must be at least 6 characters.', 'warning'); return }
    const res = await settingsApi.password(newPass)
    if (res?.data?.ok) {
      toast('Password changed. Logging out...', 'success')
      setTimeout(() => { window.location.href = '/logout' }, 2000)
    } else {
      toast('Failed to change password.', 'error')
    }
  }

  const clearToday = async () => {
    if (!confirm('Clear all attendance records for today?')) return
    const res = await attendanceApi.clearDay(today())
    if (res?.data?.ok) toast("Today's attendance cleared.", 'success')
  }

  const clearAll = async () => {
    if (!confirm('Delete ALL attendance records? Cannot be undone.')) return
    const res = await attendanceApi.clearAll()
    if (res?.data?.ok) toast('All attendance records cleared.', 'success')
  }

  const resetAll = async () => {
    if (!confirm('Reset EVERYTHING? All students and attendance will be deleted.')) return
    if (!confirm('Are you absolutely sure?')) return
    const res = await systemApi.resetAll()
    if (res?.data?.ok) { toast('System reset.', 'success'); setTimeout(() => window.location.href = '/', 2000) }
  }

  const createBackup = async () => {
    setBacking(true)
    try {
      const res = await fetch('/api/backup/create', { method: 'POST', credentials: 'include' })
      if (!res.ok) { toast('Backup failed.', 'error'); return }
      const blob = await res.blob()
      const cd   = res.headers.get('Content-Disposition') || ''
      const name = cd.match(/filename="?([^"]+)"?/)?.[1] || 'facetrack_backup.zip'
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href = url; a.download = name; a.click()
      URL.revokeObjectURL(url)
      toast('Backup downloaded.', 'success')
    } catch { toast('Backup failed.', 'error') }
    finally { setBacking(false) }
  }

  const restoreBackup = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = '' // reset so same file can be re-selected
    if (!confirm(`Restore from "${file.name}"? Current data will be overwritten.`)) return
    setRestoring(true)
    try {
      const res = await systemApi.restoreBackup(file)
      if (res?.data?.ok) {
        toast('Backup restored. Cameras restarting…', 'success')
      } else {
        toast(res?.data?.error || 'Restore failed.', 'error')
      }
    } catch { toast('Restore failed.', 'error') }
    finally { setRestoring(false) }
  }

  return (
    <div>
      <div className="g2" style={{ gap: 20, alignItems: 'start' }}>

        {/* ── Left column ──────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Recognition */}
          <div className="card">
            <div className="card-title"><span className="card-icon">⚙</span> Recognition Settings</div>
            <RangeRow label="Recognition Threshold" value={s.REC_THRESHOLD} min={0.20} max={0.80} step={0.01}
              onChange={v => set('REC_THRESHOLD', v)} format={v => v.toFixed(2)}
              leftLabel="Relaxed (matches more easily)" rightLabel="Strict (fewer false matches)"
              desc="ArcFace cosine similarity cutoff. Genuine matches score ~0.40–0.75. Start at 0.40 and raise if unknown people are being matched." />
            <RangeRow label="Detection Confidence" value={s.DET_THRESH} min={0.20} max={0.90} step={0.01}
              onChange={v => set('DET_THRESH', v)} format={v => v.toFixed(2)}
              leftLabel="Sensitive (detects more faces)" rightLabel="Strict (fewer false detections)"
              desc="RetinaFace detection confidence. Raise if non-face objects are being detected." />
            <RangeRow label="Confirm Frames" value={s.CONFIRM_FRAMES} min={1} max={10} step={1}
              onChange={v => set('CONFIRM_FRAMES', v)}
              leftLabel="Faster (1 frame)" rightLabel="More stable (10 frames)"
              desc="Consecutive recognitions required before marking attendance." />
            <RangeRow label="Stored Embeddings per Student" value={s.EMBEDDINGS_PER_STUDENT} min={5} max={50} step={1}
              onChange={v => set('EMBEDDINGS_PER_STUDENT', v)}
              desc="More embeddings = better accuracy but more memory. Applied on next enrollment." />
          </div>

          {/* Camera */}
          <div className="card">
            <div className="card-title"><span className="card-icon">📷</span> Camera Settings</div>
            <div className="setting-row">
              <div className="setting-info">
                <div className="setting-label">Use DirectShow Backend (Windows)</div>
                <div className="setting-desc">Older camera API. Only enable if default backend fails.</div>
              </div>
              <div className="setting-ctrl">
                <Toggle value={s.USE_DSHOW} onChange={v => set('USE_DSHOW', v)} />
              </div>
            </div>
            <RangeRow label="Process Every N Frames" value={s.PROCESS_EVERY_N} min={1} max={15} step={1}
              onChange={v => set('PROCESS_EVERY_N', v)}
              leftLabel="Every frame (high CPU)" rightLabel="Every 15th (light)"
              desc="Run face detection on 1 in every N frames." />
            <RangeRow label="Stream FPS" value={s.STREAM_FPS} min={1} max={30} step={1}
              onChange={v => set('STREAM_FPS', v)}
              desc="MJPEG stream frame rate to the browser." />
            <div className="form-row" style={{ marginTop: 14 }}>
              <div className="form-group">
                <label className="form-label">Frame Width</label>
                <input type="number" className="form-input" value={s.FRAME_WIDTH} min="320" max="1920"
                  onChange={e => set('FRAME_WIDTH', parseInt(e.target.value))} />
              </div>
              <div className="form-group">
                <label className="form-label">Frame Height</label>
                <input type="number" className="form-input" value={s.FRAME_HEIGHT} min="240" max="1080"
                  onChange={e => set('FRAME_HEIGHT', parseInt(e.target.value))} />
              </div>
            </div>
          </div>

          {/* Preprocessing */}
          <div className="card">
            <div className="card-title"><span className="card-icon">🌙</span> Image Preprocessing</div>
            <div className="setting-row">
              <div className="setting-info">
                <div className="setting-label">CLAHE Contrast Enhancement</div>
                <div className="setting-desc">Improves contrast in dim classrooms.</div>
              </div>
              <div className="setting-ctrl"><Toggle value={s.ENABLE_CLAHE} onChange={v => set('ENABLE_CLAHE', v)} /></div>
            </div>
            <RangeRow label="CLAHE Clip Limit" value={s.CLAHE_CLIP_LIMIT} min={0.5} max={6.0} step={0.1}
              onChange={v => set('CLAHE_CLIP_LIMIT', v)} format={v => v.toFixed(1)}
              leftLabel="Subtle" rightLabel="Aggressive" />
            <div className="setting-row">
              <div className="setting-info">
                <div className="setting-label">Bilateral Denoising</div>
                <div className="setting-desc">Reduces grain without blurring face edges.</div>
              </div>
              <div className="setting-ctrl"><Toggle value={s.ENABLE_DENOISE} onChange={v => set('ENABLE_DENOISE', v)} /></div>
            </div>
            <RangeRow label="Upscale Factor for Small Faces" value={s.SUPER_RES_SCALE} min={1} max={4} step={0.5}
              onChange={v => set('SUPER_RES_SCALE', v)} format={v => `${v}x`}
              leftLabel="No upscale (1x)" rightLabel="4x (corner cameras)"
              desc="Upscales frames before detection. Helps cameras far from students." />
          </div>
        </div>

        {/* ── Right column ─────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* School info */}
          <div className="card">
            <div className="card-title"><span className="card-icon">🏫</span> School Information</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="form-group">
                <label className="form-label">School Name</label>
                <input className="form-input" value="Narula Public School" disabled
                  style={{ opacity: .6, cursor: 'not-allowed' }} title="School name is fixed" />
              </div>
              <div className="form-group">
                <label className="form-label">Admin Name</label>
                <input className="form-input" placeholder="e.g. Mr. Principal"
                  value={s.ADMIN_DISPLAY_NAME} onChange={e => set('ADMIN_DISPLAY_NAME', e.target.value)} />
              </div>
            </div>
          </div>

          {/* Security */}
          <div className="card">
            <div className="card-title"><span className="card-icon">🔒</span> Security</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="form-group">
                <label className="form-label">New Password</label>
                <input type="password" className="form-input" placeholder="Leave blank to keep current"
                  value={newPass} onChange={e => setNewPass(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Confirm New Password</label>
                <input type="password" className="form-input" placeholder="Repeat new password"
                  value={confPass} onChange={e => setConfPass(e.target.value)} />
              </div>
              <button className="btn btn-ghost btn-sm" style={{ alignSelf: 'flex-start' }} onClick={changePassword}>
                🔒 Change Password
              </button>
            </div>
          </div>

          {/* System info */}
          <div className="card">
            <div className="card-title"><span className="card-icon">⊕</span> System Info</div>
            <div className="info-row"><span className="info-key">Enrolled Students</span><span className="info-val">{sysInfo.enrolled || 0}</span></div>
            <div className="info-row"><span className="info-key">Detector</span><span className="info-val" style={{ color: 'var(--success)' }}>RetinaFace ✓</span></div>
            <div className="info-row"><span className="info-key">Recognizer</span><span className="info-val" style={{ color: 'var(--success)' }}>ArcFace ✓</span></div>
          </div>

          {/* Backup & Restore */}
          <div className="card">
            <div className="card-title"><span className="card-icon">🗂</span> Backup &amp; Restore</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ fontSize: 12, color: 'var(--text3)', lineHeight: 1.7 }}>
                Backup includes: students, attendance, embeddings, and settings.<br/>
                <strong style={{ color: 'var(--text2)' }}>Note:</strong> Passwords (.env) are not included for security.
              </div>
              <button className="btn btn-ghost" onClick={createBackup} disabled={backing}>
                {backing ? <span className="spin" /> : '⬇'} {backing ? 'Creating…' : 'Create Backup'}
              </button>
              <button className="btn btn-ghost" onClick={() => restoreRef.current?.click()} disabled={restoring}>
                {restoring ? <span className="spin" /> : '⬆'} {restoring ? 'Restoring…' : 'Restore from Backup'}
              </button>
              <input ref={restoreRef} type="file" accept=".zip" style={{ display: 'none' }}
                onChange={restoreBackup} />
            </div>
          </div>

          {/* Data management */}
          <div className="card">
            <div className="card-title"><span className="card-icon">💾</span> Data Management</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <a className="btn btn-ghost" href={`/reports/excel?date=${today()}`} download>↓ Export Today (Excel)</a>
              <a className="btn btn-ghost" href={`/reports/pdf?date=${today()}`} download>↓ Export Today (PDF)</a>
              <hr style={{ borderColor: 'var(--border)' }} />
              <button className="btn btn-danger" onClick={clearToday}>🗑 Clear Today's Attendance</button>
              <button className="btn btn-danger" onClick={clearAll}>⚠ Clear All Attendance Records</button>
              <button className="btn btn-danger" onClick={resetAll}>⚠ Reset Everything</button>
            </div>
          </div>

          {/* Tips */}
          <div className="card">
            <div className="card-title"><span className="card-icon">💡</span> Tips</div>
            <div style={{ fontSize: 13, color: 'var(--text3)', lineHeight: 1.9 }}>
              <div>📷 <strong style={{ color: 'var(--text2)' }}>Corner cameras:</strong> Increase Upscale Factor to 2–3×</div>
              <div>🌙 <strong style={{ color: 'var(--text2)' }}>Low light:</strong> Enable CLAHE + Denoising</div>
              <div>👥 <strong style={{ color: 'var(--text2)' }}>Better accuracy:</strong> Enroll 15+ photos per student</div>
              <div>⚡ <strong style={{ color: 'var(--text2)' }}>High CPU:</strong> Increase Process Every N Frames</div>
              <div>🎯 <strong style={{ color: 'var(--text2)' }}>False positives:</strong> Raise Recognition Threshold</div>
            </div>
          </div>
        </div>
      </div>

      {/* Floating save button */}
      <div style={{ position: 'fixed', bottom: 24, right: 24, display: 'flex', alignItems: 'center', gap: 10, zIndex: 200 }}>
        {saveMsg && (
          <span style={{
            fontSize: 12, color: saveMsg === 'Saved' ? 'var(--success)' : 'var(--danger)',
            background: 'var(--bg2)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)', padding: '5px 10px',
          }}>
            {saveMsg}
          </span>
        )}
        <button className="btn btn-primary" style={{ boxShadow: '0 4px 20px rgba(79,70,229,.45)' }}
          onClick={save} disabled={saving}>
          {saving ? <span className="spin" /> : '✓'} Save All Settings
        </button>
      </div>
    </div>
  )
}
