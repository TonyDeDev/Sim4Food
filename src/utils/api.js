// Strip any trailing slash so a `.env` value like "http://localhost:8000/"
// doesn't produce a double-slash path (e.g. ":8000//api/inventory") that
// FastAPI's router won't match.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '')

export const RECORD_FIELDS = [
  { key: 'ingredients', label: 'Ingredients' },
  { key: 'menu', label: 'Menu' },
  { key: 'recipes', label: 'Recipes' },
  { key: 'sales', label: 'POS / sales history' },
  { key: 'purchases', label: 'Purchases' },
  { key: 'inventory_counts', label: 'Inventory counts' },
]

// FastAPI lives on a different origin (:8000 vs :3000), so the session
// cookie set by the Next.js auth routes only reaches it with
// credentials: 'include' - and only because both sides share the same
// "localhost" host (cookies aren't port-scoped). FastAPI's CORS config
// must allow_credentials for this to work (see backend/app/main.py).
export async function fetchInventory(restaurantId) {
  const params = new URLSearchParams({ restaurant_id: restaurantId })
  const response = await fetch(`${API_URL}/api/inventory?${params}`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Could not load inventory (${response.status})`)
  return response.json()
}

// Headline numbers for the Home tab: revenue, waste, stock health, next event.
export async function fetchHomeSummary(restaurantId) {
  const params = new URLSearchParams({ restaurant_id: restaurantId })
  const response = await fetch(`${API_URL}/api/home-summary?${params}`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Could not load the summary (${response.status})`)
  return response.json()
}

// {file_type: file_name} for whatever has actually been persisted - the
// source of truth for "what's already uploaded", since a client-only
// files map resets to empty on every fresh login/session restore.
export async function fetchUploadStatus(restaurantId) {
  const params = new URLSearchParams({ restaurant_id: restaurantId })
  const response = await fetch(`${API_URL}/api/uploads?${params}`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Could not load upload status (${response.status})`)
  return response.json()
}

// The forecast only trains when explicitly triggered (the Simulate button),
// not on every page view - GET reads whatever was last stored (cheap, no
// training), POST actually runs the model and stores the new result.
// Both return {run_at, forecast}; run_at/forecast are null if never run.
export async function fetchLatestForecast(restaurantId) {
  const params = new URLSearchParams({ restaurant_id: restaurantId })
  const response = await fetch(`${API_URL}/api/forecast?${params}`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Could not load the forecast (${response.status})`)
  return response.json()
}

export async function runForecast(restaurantId) {
  const params = new URLSearchParams({ restaurant_id: restaurantId })
  const response = await fetch(`${API_URL}/api/forecast?${params}`, { method: 'POST', credentials: 'include' })
  if (!response.ok) throw new Error(`Could not run the forecast (${response.status})`)
  return response.json()
}

export async function uploadRecordFile(restaurantId, fileType, file) {
  const body = new FormData()
  body.append('file', file)
  const params = new URLSearchParams({ restaurant_id: restaurantId, file_type: fileType })
  const response = await fetch(`${API_URL}/api/upload?${params}`, {
    method: 'POST',
    body,
    credentials: 'include',
  })
  const result = await response.json().catch(() => null)
  if (!response.ok || !result || result.status !== 'ok') {
    throw new Error(result?.errors?.[0] || result?.detail || `Upload failed (${response.status})`)
  }
  return result
}

// --- Auth + restaurants: same origin as the Next.js app, so cookies are
// sent automatically without needing credentials: 'include'. ---

async function postJson(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const result = await response.json().catch(() => null)
  if (!response.ok) throw new Error(result?.error || `Request failed (${response.status})`)
  return result
}

export async function signup({ first, last, email, password }) {
  const result = await postJson('/api/auth/signup', { first, last, email, password })
  return result.user
}

export async function login({ email, password }) {
  const result = await postJson('/api/auth/login', { email, password })
  return result.user
}

export async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' })
}

export async function getSession() {
  const response = await fetch('/api/auth/session')
  const result = await response.json().catch(() => ({ user: null }))
  return result.user
}

export async function listRestaurants() {
  const response = await fetch('/api/restaurants')
  if (!response.ok) throw new Error('Could not load your businesses.')
  const result = await response.json()
  return result.restaurants
}

export async function createRestaurant({ name, type, location }) {
  const result = await postJson('/api/restaurants', { name, type, location })
  return result.restaurant
}
