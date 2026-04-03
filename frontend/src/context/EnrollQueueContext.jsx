import { createContext, useContext, useState, useRef, useCallback } from 'react'
import { students as studentsApi } from '../api'

const EnrollQueueContext = createContext(null)

export function EnrollQueueProvider({ children }) {
  const [queue,    setQueue]    = useState([])   // exposed so consumers can watch length
  const [current,  setCurrent]  = useState(null) // item currently being processed
  const [progress, setProgress] = useState(0)    // 0–100
  const processing = useRef(false)

  // Process items one by one
  const processNext = useCallback(async (q) => {
    if (processing.current || q.length === 0) return
    processing.current = true

    const item = q[0]
    setCurrent(item)
    setProgress(0)

    try {
      // Build FormData
      const fd = new FormData()
      const meta = item.meta
      fd.append('student_id', meta.student_id)
      fd.append('name',       meta.name)
      fd.append('class_name', meta.class_name)
      fd.append('section',    meta.section)
      fd.append('roll_no',    meta.roll_no)
      fd.append('stream',     meta.stream || '')

      const images = [...(item.blobs || []), ...(item.files || [])]
      images.forEach((img, i) => {
        if (img instanceof Blob) fd.append('photos', img, `capture_${i}.jpg`)
        else                      fd.append('photos', img)
      })

      // Fake progress while uploading
      let tick = 0
      const timer = setInterval(() => {
        tick += Math.random() * 12
        setProgress(Math.min(tick, 90))
      }, 300)

      const res = await studentsApi.enroll(fd)
      clearInterval(timer)
      setProgress(100)

      if (!res?.data?.ok) {
        console.warn('Enrollment failed for', meta.name, res?.data?.error)
      }
    } catch (err) {
      console.error('Enrollment error:', err)
    }

    await new Promise(r => setTimeout(r, 600)) // brief pause so user sees 100%

    setQueue(prev => {
      const next = prev.slice(1)
      setCurrent(null)
      setProgress(0)
      processing.current = false
      // Recursively process the next item
      setTimeout(() => processNext(next), 50)
      return next
    })
  }, [])

  const addToQueue = useCallback((meta, blobs, files) => {
    const item = { id: Date.now(), meta, blobs, files }
    setQueue(prev => {
      const next = [...prev, item]
      if (!processing.current) processNext(next)
      return next
    })
  }, [processNext])

  return (
    <EnrollQueueContext.Provider value={{ addToQueue, queue }}>
      {children}
      {/* Queue panel — fixed to bottom-RIGHT corner, never centred */}
      {(queue.length > 0 || current) && (
        <QueuePanel queue={queue} current={current} progress={progress} />
      )}
    </EnrollQueueContext.Provider>
  )
}

function QueuePanel({ queue, current, progress }) {
  return (
    <div style={{
      position: 'fixed',
      bottom: 24,
      right: 24,          // ← pinned to the right
      left: 'auto',       // ← never centred
      width: 320,
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      boxShadow: '0 8px 32px rgba(0,0,0,.45)',
      zIndex: 1000,
      overflow: 'hidden',
      fontFamily: "'Sora', sans-serif",
    }}>
      {/* Header */}
      <div style={{
        padding: '10px 14px',
        background: 'var(--surface2)',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text1)' }}>
          Enrollment Queue
        </span>
        <span style={{
          fontSize: 11.5, fontWeight: 700, letterSpacing: '.5px',
          background: 'var(--accent)', color: '#fff',
          borderRadius: 20, padding: '2px 9px',
        }}>
          {queue.length} pending
        </span>
      </div>

      {/* Current item */}
      {current && (
        <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontSize: 12.5, color: 'var(--text1)', fontWeight: 600 }}>
              Processing: {current.meta.name}
            </span>
            <span style={{ fontSize: 11.5, color: 'var(--accent)', fontFamily: 'Space Mono, monospace' }}>
              {Math.round(progress)}%
            </span>
          </div>
          {/* Progress bar */}
          <div style={{
            height: 5, borderRadius: 999,
            background: 'var(--border)',
            overflow: 'hidden',
          }}>
            <div style={{
              height: '100%',
              width: `${progress}%`,
              background: 'linear-gradient(90deg, var(--accent), var(--accent2, var(--accent)))',
              borderRadius: 999,
              transition: 'width .3s ease',
            }} />
          </div>
          <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>
            {current.meta.class_name} · Section {current.meta.section} · Roll {current.meta.roll_no}
          </div>
        </div>
      )}

      {/* Pending items */}
      {queue.length > 1 && (
        <div style={{ maxHeight: 160, overflowY: 'auto', padding: '6px 0' }}>
          {queue.slice(1).map((item, i) => (
            <div key={item.id} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '6px 14px',
            }}>
              <div style={{
                width: 26, height: 26, borderRadius: '50%',
                background: 'var(--surface2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 10.5, fontWeight: 700, color: 'var(--text3)',
                flexShrink: 0,
              }}>
                {i + 2}
              </div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12.5, color: 'var(--text1)', fontWeight: 500,
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {item.meta.name}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text3)' }}>
                  {item.meta.class_name} · {item.blobs?.length || item.files?.length || 0} photos
                </div>
              </div>
              <span style={{
                marginLeft: 'auto', fontSize: 10.5, color: 'var(--text3)',
                background: 'var(--surface2)', borderRadius: 20, padding: '2px 7px',
                flexShrink: 0,
              }}>queued</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function useEnrollQueue() {
  const ctx = useContext(EnrollQueueContext)
  if (!ctx) throw new Error('useEnrollQueue must be used within EnrollQueueProvider')
  return ctx
}
