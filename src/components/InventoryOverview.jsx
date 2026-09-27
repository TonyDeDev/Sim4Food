import { useEffect, useState } from 'react'
import { fetchInventory, fetchLatestForecast } from '../utils/api.js'
import { formatDate, formatTime } from '../utils/format.js'

export default function InventoryOverview({ restaurantId }) {
  const [state, setState] = useState({ status: 'loading' })
  // undefined = still loading, null = never run - kept separate from the
  // main inventory fetch so a failure here never blocks the stock listing.
  const [forecastRunAt, setForecastRunAt] = useState(undefined)

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    fetchInventory(restaurantId)
      .then((data) => { if (!cancelled) setState({ status: 'ok', data }) })
      .catch((err) => { if (!cancelled) setState({ status: 'error', message: err.message }) })
    return () => { cancelled = true }
  }, [restaurantId])

  useEffect(() => {
    let cancelled = false
    setForecastRunAt(undefined)
    fetchLatestForecast(restaurantId)
      .then((data) => { if (!cancelled) setForecastRunAt(data.run_at) })
      .catch(() => { if (!cancelled) setForecastRunAt(null) })
    return () => { cancelled = true }
  }, [restaurantId])

  if (state.status === 'loading') return <p className="hint">Loading inventory…</p>
  if (state.status === 'error') return <p className="field-error" role="alert">{state.message}</p>

  const { ingredients, summary } = state.data
  if (ingredients.length === 0) {
    return <p className="hint">Upload ingredients, sales, and an inventory count to see your current stock.</p>
  }

  return (
    <>
      <section className="stat-grid" aria-label="Inventory summary">
        <div className="stat-card">
          <p className="stat-label">Ingredients tracked</p>
          <p className="stat-value">{summary.total}</p>
          <p className="stat-sub">uploaded</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Stock counts uploaded</p>
          <p className="stat-value">{summary.tracked}</p>
          <p className="stat-sub">of {summary.total}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Last forecast</p>
          <p className="stat-value">
            {forecastRunAt === undefined ? '…' : forecastRunAt ? formatDate(forecastRunAt) : 'Not run yet'}
          </p>
          <p className="stat-sub">
            {forecastRunAt ? formatTime(forecastRunAt) : 'run it from the Forecast tab'}
          </p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Stockout forecast</p>
          <p className="stat-value">—</p>
          <p className="stat-sub">from the simulation model, coming soon</p>
        </div>
      </section>

      {summary.missing_count > 0 && (
        <section className="alert-card" aria-label="Ingredients missing a stock count">
          <div className="alert-card-head">
            <h2>{summary.missing_count} ingredient{summary.missing_count === 1 ? '' : 's'} missing a stock count</h2>
          </div>
          <p className="alert-subtitle">Upload an inventory count for these to start tracking them here.</p>
        </section>
      )}

      <div className="inventory-table-wrap">
        <table className="inventory-table">
          <thead>
            <tr>
              <th>Ingredient</th>
              <th>On hand</th>
              <th>Avg. used / day</th>
              <th>Est. runway</th>
            </tr>
          </thead>
          <tbody>
            {ingredients.map((row) => (
              <tr key={row.ingredient_id}>
                <td>{row.name}</td>
                <td>{row.qty_on_hand === null ? 'No count uploaded' : `${row.qty_on_hand} ${row.unit}`}</td>
                <td>{row.avg_daily_consumption ? `${row.avg_daily_consumption} ${row.unit}` : '—'}</td>
                <td><span className="pending-note">Pending forecast</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
