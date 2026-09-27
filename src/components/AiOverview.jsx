import { useEffect, useState } from 'react'
import { fetchForecastSummary } from '../utils/api.js'
import PlainAnswer from './PlainAnswer.jsx'

const STYLES = [
  { key: 'summary', label: 'Summary' },
  { key: 'detailed', label: 'Detailed' },
]

// Overview of the latest forecast run, written by Snowflake Cortex: a few bullets
// (Summary) or two paragraphs (Detailed). Each style is fetched once per run.
export default function AiOverview({ restaurantId, runAt, model }) {
  const [style, setStyle] = useState('summary')
  const [texts, setTexts] = useState({})
  const [error, setError] = useState('')

  // A new run (or another restaurant) starts from scratch, reset during render
  // (see "resetting state when a prop changes":
  // https://react.dev/learn/you-might-not-need-an-effect).
  const runKey = `${restaurantId}:${runAt}`
  const [syncedFor, setSyncedFor] = useState(runKey)
  if (syncedFor !== runKey) {
    setSyncedFor(runKey)
    setTexts({})
    setError('')
  }

  const text = texts[style]

  useEffect(() => {
    if (text !== undefined) return undefined
    const controller = new AbortController()
    fetchForecastSummary(restaurantId, { style, signal: controller.signal })
      .then((data) => setTexts((prev) => ({ ...prev, [style]: data.summary })))
      .catch((err) => { if (err.name !== 'AbortError') setError(err.message) })
    return () => controller.abort()
  }, [restaurantId, runAt, style, text])

  function choose(next) {
    setError('')
    setStyle(next)
  }

  const loading = text === undefined && !error

  return (
    <section className="ai-card" aria-label="AI overview" aria-busy={loading}>
      <div className="ai-card-head">
        <h2>Overview</h2>
        <div className="segmented" role="tablist" aria-label="Overview length">
          {STYLES.map((s) => (
            <button
              key={s.key}
              type="button"
              role="tab"
              aria-selected={style === s.key}
              className={style === s.key ? 'active' : undefined}
              onClick={() => choose(s.key)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
      {loading && (
        <div className="skeleton ai-skeleton">
          <div className="skeleton-line" />
          <div className="skeleton-line" />
          <div className="skeleton-line short" />
        </div>
      )}
      {error && <p className="field-error" role="alert">{error}</p>}
      {text !== undefined && <div className="ai-summary"><PlainAnswer text={text} /></div>}
      <p className="ai-credit">Written by Snowflake Cortex{model ? ` (${model})` : ''} from your forecast numbers only.</p>
    </section>
  )
}
