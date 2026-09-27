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
