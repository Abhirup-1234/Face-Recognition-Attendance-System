import { createContext, useContext, useState, useRef, useCallback } from 'react'
import { students as studentsApi } from '../api'

const EnrollQueueContext = createContext(null)

export function EnrollQueueProvider({ children, onEnrolled }) {
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

      if (res?.data?.ok) {
        // Notify App.jsx to increment the sidebar count live
        onEnrolled?.()
      } else {
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
  }, [onEnrolled])

  const addToQueue = useCallback((meta, blobs, files) => {
    const item = { id: Date.now(), meta, blobs, files }
    setQueue(prev => {
      const next = [...prev, item]
      if (!processing.current) processNext(next)
      return next
    })
  }, [processNext])

  // Cancel a queued item (only items that are NOT currently processing)
  const removeFromQueue = useCallback((itemId) => {
    setQueue(prev => prev.filter((item, idx) => {
      // Don't allow removing index 0 while it's being processed
      if (idx === 0 && processing.current) return true
      return item.id !== itemId
    }))
  }, [])

  return (
    <EnrollQueueContext.Provider value={{ addToQueue, removeFromQueue, queue, current, progress }}>
      {children}
    </EnrollQueueContext.Provider>
  )
}

export function useEnrollQueue() {
  const ctx = useContext(EnrollQueueContext)
  if (!ctx) throw new Error('useEnrollQueue must be used within EnrollQueueProvider')
  return ctx
}
