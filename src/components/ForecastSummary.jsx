import { useEffect, useState } from 'react'
import { fetchForecastSummary } from '../utils/api.js'

// Plain-English summary of the latest forecast run, written by Snowflake Cortex.
export default function ForecastSummary({ restaurantId, runAt, model }) {
  const [state, setState] = useState({ status: 'loading' })
  const [reloadKey, setReloadKey] = useState(0)

  // Reset synchronously during render when the run or a manual refresh changes,
  // rather than inside the effect (see "resetting state when a prop changes":
  // https://react.dev/learn/you-might-not-need-an-effect).
  const requestKey = `${restaurantId}:${runAt}:${reloadKey}`
  const [syncedFor, setSyncedFor] = useState(null)
  if (syncedFor !== requestKey) {
    setSyncedFor(requestKey)
    setState({ status: 'loading' })
  }

  useEffect(() => {
    const controller = new AbortController()
    fetchForecastSummary(restaurantId, { refresh: reloadKey > 0, signal: controller.signal })
      .then((data) => setState({ status: 'ok', text: data.summary }))
      .catch((err) => { if (err.name !== 'AbortError') setState({ status: 'error', message: err.message }) })
    return () => controller.abort()
  }, [restaurantId, runAt, reloadKey])

  return (
    <section className="ai-card" aria-label="AI order summary" aria-busy={state.status === 'loading'}>
      <div className="ai-card-head">
        <h2>This week in plain words</h2>
        <button
          type="button"
          className="btn-link"
          onClick={() => setReloadKey((k) => k + 1)}
          disabled={state.status === 'loading'}
        >
          Rewrite
        </button>
      </div>
      {state.status === 'loading' && (
        <div className="skeleton ai-skeleton">
          <div className="skeleton-line" />
          <div className="skeleton-line" />
          <div className="skeleton-line short" />
        </div>
      )}
      {state.status === 'error' && <p className="field-error" role="alert">{state.message}</p>}
      {state.status === 'ok' && <p className="ai-summary">{state.text}</p>}
      <p className="ai-credit">Written by Snowflake Cortex{model ? ` (${model})` : ''} from your forecast numbers only.</p>
    </section>
  )
}
