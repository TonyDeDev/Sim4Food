export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export const RECORD_FIELDS = [
  { key: 'ingredients', label: 'Ingredients' },
  { key: 'menu', label: 'Menu' },
  { key: 'recipes', label: 'Recipes' },
  { key: 'sales', label: 'POS / sales history' },
  { key: 'purchases', label: 'Purchases' },
  { key: 'inventory_counts', label: 'Inventory counts' },
]

export async function uploadRecordFile(restaurantId, fileType, file) {
  const body = new FormData()
  body.append('file', file)
  const params = new URLSearchParams({ restaurant_id: restaurantId, file_type: fileType })
  const response = await fetch(`${API_URL}/api/upload?${params}`, { method: 'POST', body })
  const result = await response.json().catch(() => null)
  if (!response.ok || !result || result.status !== 'ok') {
    throw new Error(result?.errors?.[0] || result?.detail || `Upload failed (${response.status})`)
  }
  return result
}
