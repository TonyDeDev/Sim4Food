import { useEffect, useState } from 'react'
import { fetchLatestForecast, runForecast } from '../utils/api.js'
import { formatDateTime } from '../utils/format.js'

function Sparkline({ values }) {
  const nums = values.filter((v) => v !== null && v !== undefined)
  if (nums.length < 2) return <span className="pending-note">Not enough history</span>

  const w = 90
  const h = 28
  const pad = 3
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  const range = max - min || 1
  const points = nums.map((v, i) => {
    const x = pad + (i / (nums.length - 1)) * (w - pad * 2)
    const y = h - pad - ((v - min) / range) * (h - pad * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width={w} height={h} className="sparkline" role="img" aria-label="Usage trend over recent weeks">
      <polyline points={points} fill="none" stroke="var(--deep-green)" strokeWidth="1.5" />
    </svg>
  )
}

export default function ForecastOverview({ restaurantId }) {
  const [state, setState] = useState({ status: 'loading' })
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState('')

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    fetchLatestForecast(restaurantId)
      .then((data) => { if (!cancelled) setState({ status: 'ok', runAt: data.run_at, forecast: data.forecast }) })
      .catch((err) => { if (!cancelled) setState({ status: 'error', message: err.message }) })
    return () => { cancelled = true }
  }, [restaurantId])

  async function handleRun() {
    setRunError('')
    setRunning(true)
    try {
      const data = await runForecast(restaurantId)
      setState({ status: 'ok', runAt: data.run_at, forecast: data.forecast })
    } catch (err) {
      setRunError(err.message || 'Could not run the forecast. Please try again.')
    } finally {
      setRunning(false)
    }
  }

  if (state.status === 'loading') return <p className="hint">Loading…</p>
  if (state.status === 'error') return <p className="field-error" role="alert">{state.message}</p>

  const { runAt, forecast } = state

  return (
    <>
      <div className="forecast-run-bar">
        <p className="hint">
          {running ? 'Training the forecast…' : runAt ? `Last run: ${formatDateTime(runAt)}` : 'No forecast has been run yet.'}
        </p>
        <button type="button" className="btn-pastel" onClick={handleRun} disabled={running}>
          {running ? 'Running…' : runAt ? 'Re-run forecast' : 'Run forecast'}
        </button>
      </div>
      {runError && <p className="field-error" role="alert">{runError}</p>}

      {!forecast ? (
        <p className="hint">Click "Run forecast" to train a model on your uploaded sales and recipes.</p>
      ) : forecast.data.weeks_of_history === 0 ? (
        <p className="hint">Upload sales, recipes, and menu data, then run the forecast.</p>
      ) : (
        <ForecastResults forecast={forecast} />
      )}
    </>
  )
}

function ForecastResults({ forecast }) {
  const { data, accuracy, ingredients } = forecast

  return (
    <>
      <section className="stat-grid stat-grid-3" aria-label="Forecast summary">
        <div className="stat-card">
          <p className="stat-label">Weeks of history</p>
          <p className="stat-value">{data.weeks_of_history}</p>
          <p className="stat-sub">{data.first_week} to {data.last_week}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Forecasting for</p>
          <p className="stat-value">Next week</p>
          <p className="stat-sub">{data.forecast_week}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Forecast confidence</p>
          <p className="stat-value">
            {accuracy?.band_coverage ? `${Math.round(accuracy.band_coverage.inside_p10_p90 * 100)}%` : '—'}
          </p>
          <p className="stat-sub">
            {accuracy?.band_coverage
              ? 'how often actual usage landed in our predicted range'
              : 'not enough history yet to check'}
          </p>
        </div>
      </section>

      {data.status !== 'established' && (
        <section className="alert-card" aria-label="Forecast confidence">
          <div className="alert-card-head">
            <h2>{data.status === 'learning' ? 'Still learning' : 'Getting sharper'}</h2>
          </div>
          <p className="alert-subtitle">{data.message}</p>
        </section>
      )}

      <div className="inventory-table-wrap">
        <table className="inventory-table">
          <thead>
            <tr>
              <th>Ingredient</th>
              <th>Recent trend</th>
              <th>Next week (P50)</th>
              <th>Range (P10-P90)</th>
            </tr>
          </thead>
          <tbody>
            {ingredients.map((row) => (
              <tr key={row.ingredient_id}>
                <td>{row.name}</td>
                <td><Sparkline values={row.history.map((h) => h.usage)} /></td>
                <td>{(row.forecast.p50 ?? row.forecast.point)} {row.unit}</td>
                <td>
                  {row.forecast.p10 != null && row.forecast.p90 != null
                    ? `${row.forecast.p10} - ${row.forecast.p90} ${row.unit}`
                    : <span className="pending-note">Not enough data yet</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
