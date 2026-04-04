/**
 * Centralised API layer — class / stream / section hierarchy.
 */

const BASE = ''

async function request(method, url, body = null, isForm = false) {
  const opts = { method, credentials: 'include', headers: {} }
  if (body) {
    if (isForm) { opts.body = body }
    else { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body) }
  }
  const res = await fetch(BASE + url, opts)
  if (res.status === 401 || res.status === 302) { window.location.href = '/login'; return null }
  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, status: res.status, data }
}

function buildQS(params) {
  return Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join('&')
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export const auth = {
  status: ()           => request('GET',  '/api/auth/status'),
  login:  (user, pass) => request('POST', '/login', { username: user, password: pass }),
  logout: ()           => request('GET',  '/logout'),
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
export const stats = { get: () => request('GET', '/api/stats') }

// ── Students ──────────────────────────────────────────────────────────────────
export const students = {
  list:   (cls, stream, section) => {
    const qs = buildQS({ class: cls, stream, section })
    return request('GET', `/api/students${qs ? '?' + qs : ''}`)
  },
  remove: (id)       => request('DELETE', `/api/students/${id}`),
  enroll: (formData) => request('POST', '/api/enroll', formData, true),
}

// ── Cameras ───────────────────────────────────────────────────────────────────
export const cameras = {
  stats:       ()              => request('GET',  '/api/cameras'),
  start:       (id)            => request('POST', `/api/cameras/${id}/start`),
  stop:        (id)            => request('POST', `/api/cameras/${id}/stop`),
  restart:     (id)            => request('POST', `/api/cameras/${id}/restart`),
  recognition: (id, enabled)   => request('POST', `/api/cameras/${id}/recognition`, { enabled }),
  snapshot:    (id)            => `/snapshot/${id}`,
}

// ── Attendance ────────────────────────────────────────────────────────────────
export const attendance = {
  get: (date, cls, stream, section) => {
    const qs = buildQS({ date, class: cls, stream, section })
    return request('GET', `/api/attendance?${qs}`)
  },
  clearDay: (date) => request('DELETE', `/api/attendance/clear?date=${date}`),
  clearAll: ()     => request('DELETE', '/api/attendance/clear_all'),
}

// ── Reports ───────────────────────────────────────────────────────────────────
export const reports = {
  pdfUrl: (date, cls, stream, section) => {
    const qs = buildQS({ date, class: cls, stream, section })
    return `/reports/pdf?${qs}`
  },
  excelUrl: (date, cls, stream, section) => {
    const qs = buildQS({ date, class: cls, stream, section })
    return `/reports/excel?${qs}`
  },
}

// ── Classes ───────────────────────────────────────────────────────────────────
export const classes = {
  list:   ()     => request('GET',    '/api/classes'),
  add:    (name) => request('POST',   '/api/classes', { name }),
  remove: (name) => request('DELETE', `/api/classes/${encodeURIComponent(name)}`),
}

// ── Streams (read-only from server) ──────────────────────────────────────────
export const streams = {
  list: (cls) => request('GET', `/api/streams?class=${encodeURIComponent(cls)}`),
}

// ── Sections ──────────────────────────────────────────────────────────────────
export const sections = {
  list: (cls, stream = '') => {
    const qs = buildQS({ class: cls, stream })
    return request('GET', `/api/sections?${qs}`)
  },
  add: (class_name, section, stream = '') =>
    request('POST', '/api/sections', { class_name, section, stream }),
  remove: (class_name, section, stream = '') => {
    // Use __none__ as placeholder for empty stream in the URL path
    const s = stream || '__none__'
    return request('DELETE',
      `/api/sections/${encodeURIComponent(class_name)}/${encodeURIComponent(s)}/${encodeURIComponent(section)}`)
  },
}

// ── Classrooms ────────────────────────────────────────────────────────────────
export const classrooms = {
  list: ()         => request('GET',  '/api/classrooms'),
  save: (id, data) => request('POST', `/api/classrooms/${encodeURIComponent(id)}`, data),
}

// ── Settings ──────────────────────────────────────────────────────────────────
export const settings = {
  save:     (data) => request('POST', '/api/settings', data),
  password: (pass) => request('POST', '/api/settings/password', { password: pass }),
}

// ── System ────────────────────────────────────────────────────────────────────
export const system = {
  resetAll:      ()     => request('DELETE', '/api/reset_all'),
  createBackup:  ()     => request('POST',   '/api/backup/create'),
  restoreBackup: (file) => {
    const fd = new FormData()
    fd.append('backup', file)
    return request('POST', '/api/backup/restore', fd, true)
  },
}
