export function formatDate(iso) {
  if (!iso) return null
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function formatTime(iso) {
  if (!iso) return null
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

export function formatDateTime(iso) {
  if (!iso) return null
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

const DAY_MS = 24 * 60 * 60 * 1000

// "2026-09-28" (a Monday) -> "Sep 28 - Oct 4". Parsed as a local date so the day never shifts.
export function formatWeekRange(isoMonday) {
  if (!isoMonday) return null
  const [y, m, d] = isoMonday.split('-').map(Number)
  const start = new Date(y, m - 1, d)
  const end = new Date(start.getTime() + 6 * DAY_MS)
  const fmt = (date) => date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  return `${fmt(start)} - ${fmt(end)}`
}

export function formatDay(iso) {
  if (!iso) return null
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// Quantities in the ingredient's unit: whole numbers stay whole, "each" needs no label.
export function formatQty(value, unit) {
  if (value === null || value === undefined) return '-'
  const n = Number(value)
  const text = n.toLocaleString(undefined, { maximumFractionDigits: n >= 100 ? 0 : 1 })
  return unit && unit !== 'each' ? `${text} ${unit}` : text
}

export function formatMoney(value, { cents = false } = {}) {
  if (value === null || value === undefined) return '-'
  const n = Number(value)
  const text = Math.abs(n).toLocaleString(undefined, {
    minimumFractionDigits: cents ? 2 : 0,
    maximumFractionDigits: cents ? 2 : 0,
  })
  return `${n < 0 ? '-' : ''}$${text}`
}

export function formatPct(value, digits = 0) {
  if (value === null || value === undefined) return '-'
  return `${(Number(value) * 100).toFixed(digits)}%`
}
