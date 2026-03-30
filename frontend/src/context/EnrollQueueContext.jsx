import {
  createContext, useContext, useReducer,
  useEffect, useRef, useCallback, useState
} from 'react'
import { students as studentsApi } from '../api'
import { useToast } from './ToastContext'

const QueueContext = createContext(null)

const STATUS = { WAITING: 'waiting', ENROLLING: 'enrolling', DONE: 'done', ERROR: 'error' }

function reducer(state, action) {
  switch (action.type) {
    case 'ADD':
      return { ...state, items: [...state.items, action.item] }
    case 'UPDATE':
      return {
        ...state,
        items: state.items.map(i =>
          i.id === action.id ? { ...i, ...action.updates } : i
        ),
      }
    case 'REMOVE':
      return { ...state, items: state.items.filter(i => i.id !== action.id) }
    case 'CLEAR_DONE':
      return { ...state, items: state.items.filter(i => i.status !== STATUS.DONE) }
    default:
      return state
  }
}

let _qid = 0

export function EnrollQueueProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, { items: [] })
  const [collapsed, setCollapsed] = useState(false)
  const processingRef = useRef(false)
  const toast = useToast()

  // Auto-process queue sequentially
  useEffect(() => {
    async function processNext() {
      if (processingRef.current) return
      const next = state.items.find(i => i.status === STATUS.WAITING)
      if (!next) return

      processingRef.current = true
      dispatch({ type: 'UPDATE', id: next.id, updates: { status: STATUS.ENROLLING, progress: 10, message: 'Uploading photos...' } })

      const fd = new FormData()
      fd.append('student_id',  next.studentData.student_id)
      fd.append('name',        next.studentData.name)
      fd.append('class_name',  next.studentData.class_name)
      fd.append('section',     next.studentData.section)
      fd.append('roll_no',     next.studentData.roll_no)
      next.photos.forEach((blob, i) => fd.append('photos', blob, `photo_${i}.jpg`))
      next.files?.forEach(f => fd.append('photos', f))

      dispatch({ type: 'UPDATE', id: next.id, updates: { progress: 50, message: 'Building face embeddings...' } })

      try {
        const res = await studentsApi.enroll(fd)
        dispatch({ type: 'UPDATE', id: next.id, updates: { progress: 90, message: 'Finalising...' } })

        if (res?.data?.ok) {
          dispatch({ type: 'UPDATE', id: next.id, updates: { status: STATUS.DONE, progress: 100, message: 'Enrolled successfully' } })
          toast(`${next.studentData.name} enrolled successfully!`, 'success')
          // Auto-remove after 5s
          setTimeout(() => dispatch({ type: 'REMOVE', id: next.id }), 5000)
        } else {
          const err = res?.data?.error || 'Unknown error'
          dispatch({ type: 'UPDATE', id: next.id, updates: { status: STATUS.ERROR, progress: 0, message: err } })
          toast(`Failed to enroll ${next.studentData.name}: ${err}`, 'error', 8000)
        }
      } catch (e) {
        dispatch({ type: 'UPDATE', id: next.id, updates: { status: STATUS.ERROR, progress: 0, message: e.message } })
        toast(`Network error enrolling ${next.studentData.name}`, 'error')
      } finally {
        processingRef.current = false
      }
    }

    processNext()
  }, [state.items, toast])

  const addToQueue = useCallback((studentData, photos, files = []) => {
    dispatch({
      type: 'ADD',
      item: {
        id:          ++_qid,
        studentData,
        photos,
        files,
        status:      STATUS.WAITING,
        progress:    0,
        message:     'Waiting...',
      },
    })
  }, [])

  const removeFromQueue = useCallback(id => dispatch({ type: 'REMOVE', id }), [])
  const clearDone       = useCallback(() => dispatch({ type: 'CLEAR_DONE' }), [])

  const visible = state.items.length > 0

  return (
    <QueueContext.Provider value={{ items: state.items, addToQueue, removeFromQueue, clearDone, collapsed, setCollapsed, visible }}>
      {children}
      {visible && <QueuePanel />}
    </QueueContext.Provider>
  )
}

function QueuePanel() {
  const { items, removeFromQueue, clearDone, collapsed, setCollapsed } = useContext(QueueContext)

  const waiting   = items.filter(i => i.status === 'waiting').length
  const enrolling = items.filter(i => i.status === 'enrolling').length
  const done      = items.filter(i => i.status === 'done').length
  const errors    = items.filter(i => i.status === 'error').length

  return (
    <div className="queue-panel">
      <div className="queue-header" onClick={() => setCollapsed(c => !c)}>
        <div className="queue-header-title">
          {enrolling > 0 && <span className="spin" />}
          <span>
            Enrollment Queue — {items.length} student{items.length !== 1 ? 's' : ''}
          </span>
          {done > 0 && <span className="badge badge-green">{done} done</span>}
          {errors > 0 && <span className="badge badge-red">{errors} failed</span>}
          {waiting > 0 && <span className="badge badge-yellow">{waiting} waiting</span>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {done > 0 && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={e => { e.stopPropagation(); clearDone() }}
              style={{ fontSize: 11 }}
            >
              Clear done
            </button>
          )}
          <span style={{ color: 'var(--text3)', fontSize: 13 }}>{collapsed ? '▲' : '▼'}</span>
        </div>
      </div>

      {!collapsed && (
        <div className="queue-body">
          {items.map(item => (
            <QueueItem key={item.id} item={item} onRemove={removeFromQueue} />
          ))}
        </div>
      )}
    </div>
  )
}

function QueueItem({ item, onRemove }) {
  const statusClass = {
    waiting:   'status-waiting',
    enrolling: 'status-enrolling',
    done:      'status-done',
    error:     'status-error',
  }[item.status] || ''

  const statusLabel = {
    waiting:   'Waiting',
    enrolling: 'Enrolling...',
    done:      'Done ✓',
    error:     'Failed',
  }[item.status] || item.status

  return (
    <div className="queue-item">
      <div className="queue-item-header">
        <div>
          <div className="queue-item-name">{item.studentData.name}</div>
          <div className="queue-item-class">
            {item.studentData.class_name}-{item.studentData.section} &middot; Roll {item.studentData.roll_no}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className={`queue-item-status ${statusClass}`}>{statusLabel}</span>
          {(item.status === 'done' || item.status === 'error') && (
            <button
              className="btn btn-ghost btn-sm"
              style={{ padding: '2px 8px', fontSize: 11 }}
              onClick={() => onRemove(item.id)}
            >✕</button>
          )}
        </div>
      </div>

      {item.status === 'enrolling' && (
        <div className="queue-item-progress">
          <div className="pbar-wrap">
            <div className="pbar" style={{ width: `${item.progress}%` }} />
          </div>
          <div className="queue-item-msg">{item.message}</div>
        </div>
      )}

      {item.status === 'error' && (
        <div className="queue-item-msg" style={{ color: 'var(--danger)' }}>
          {item.message}
        </div>
      )}

      {item.status === 'waiting' && (
        <div className="queue-item-msg">
          {(item.photos?.length || 0) + (item.files?.length || 0)} photo(s) ready
        </div>
      )}
    </div>
  )
}

export const useEnrollQueue = () => useContext(QueueContext)
