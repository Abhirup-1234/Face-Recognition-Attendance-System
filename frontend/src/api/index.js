/**
 * Centralised API layer.
 * All fetch calls go through here so error handling is consistent.
 */

const BASE = ''  // same origin — Flask handles everything

async function request(method, url, body = null, isForm = false) {
  const opts = {
    method,
    credentials: 'include',  // include session cookie
    headers: {},
  }

  if (body) {
    if (isForm) {
      opts.body = body  // FormData — let browser set content-type
    } else {
      opts.headers['Content-Type'] = 'application/json'
      opts.body = JSON.stringify(body)
    }
  }

  const res = await fetch(BASE + url, opts)

  // Handle auth expiry — redirect to login
  if (res.status === 401 || res.status === 302) {
    window.location.href = '/login'
    return null
  }

  const data = await res.json().catch(() => ({}))
  return { ok: res.ok, status: res.status, data }
}

// ── Auth ─────────────────────────────────────────────────────────────────────
export const auth = {
  status: ()              => request('GET',  '/api/auth/status'),
  login:  (user, pass)    => request('POST', '/login', { username: user, password: pass }),
  logout: ()              => request('GET',  '/logout'),
}

// ── Dashboard ────────────────────────────────────────────────────────────────
export const stats = {
  get: () => request('GET', '/api/stats'),
}

// ── Students ─────────────────────────────────────────────────────────────────
export const students = {
  list:    (cls = '')  => request('GET', `/api/students${cls ? `?class=${encodeURIComponent(cls)}` : ''}`),
  remove:  (id)        => request('DELETE', `/api/students/${id}`),
  enroll:  (formData)  => request('POST', '/api/enroll', formData, true),
}

// ── Cameras ──────────────────────────────────────────────────────────────────
export const cameras = {
  stats:   ()           => request('GET',  '/api/cameras'),
  start:   (id)         => request('POST', `/api/cameras/${id}/start`),
  stop:    (id)         => request('POST', `/api/cameras/${id}/stop`),
  restart: (id)         => request('POST', `/api/cameras/${id}/restart`),
  snapshot:(id)         => `/snapshot/${id}`,
}

// ── Attendance ───────────────────────────────────────────────────────────────
export const attendance = {
  get:      (date, cls = '') =>
    request('GET', `/api/attendance?date=${date}${cls ? `&class=${encodeURIComponent(cls)}` : ''}`),
  clearDay: (date)           => request('DELETE', `/api/attendance/clear?date=${date}`),
  clearAll: ()               => request('DELETE', '/api/attendance/clear_all'),
}

// ── Reports ──────────────────────────────────────────────────────────────────
export const reports = {
  pdfUrl:   (date, cls = '') => `/reports/pdf?date=${date}${cls ? `&class=${encodeURIComponent(cls)}` : ''}`,
  excelUrl: (date, cls = '') => `/reports/excel?date=${date}${cls ? `&class=${encodeURIComponent(cls)}` : ''}`,
}

// ── Classes ──────────────────────────────────────────────────────────────────
export const classes = {
  list:   ()     => request('GET',  '/api/classes'),
  add:    (name) => request('POST', '/api/classes', { name }),
  remove: (name) => request('DELETE', `/api/classes/${encodeURIComponent(name)}`),
}

// ── Classrooms ───────────────────────────────────────────────────────────────
export const classrooms = {
  list:   ()              => request('GET',  '/api/classrooms'),
  save:   (id, data)      => request('POST', `/api/classrooms/${encodeURIComponent(id)}`, data),
}

// ── Settings ─────────────────────────────────────────────────────────────────
export const settings = {
  save:     (data)  => request('POST', '/api/settings', data),
  password: (pass)  => request('POST', '/api/settings/password', { password: pass }),
}

// ── Reset ────────────────────────────────────────────────────────────────────
export const system = {
  resetAll: () => request('DELETE', '/api/reset_all'),
}
