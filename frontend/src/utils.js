/**
 * Shared frontend utilities — single source of truth.
 */

/**
 * Return up to 2-letter initials from a full name.
 * @param {string} name
 * @returns {string}
 */
export function initials(name) {
  return String(name || 'XX')
    .split(' ')
    .map(w => w[0] || '')
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

/**
 * Today's date in YYYY-MM-DD format.
 * @returns {string}
 */
export function today() {
  return new Date().toISOString().split('T')[0]
}
