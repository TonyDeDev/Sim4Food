import { useEffect, useState } from 'react'
import { fetchForecastSummary, fetchWhatIfSummary } from '../utils/api.js'
import PlainAnswer from './PlainAnswer.jsx'

const STYLES = [
  { key: 'summary', label: 'Summary' },
  { key: 'detailed', label: 'Detailed' },
]

// Overview written by Snowflake Cortex, grounded only in numbers already on
// screen: a few bullets (Summary) or two paragraphs (Detailed). `kind` picks
// which result this reads and which endpoint it asks:
// - 'forecast': the latest stored forecast run (runAt identifies it).
// - 'whatif': a just-run simulation (simulateResult identifies it - there is
//   no stored "latest run" for a scenario that's re-run on every slider move).
// Each style is fetched once per result, then cached in this component.
export default function AiOverview({ kind, restaurantId, runAt, simulateResult, model }) {
  const [style, setStyle] = useState('summary')
  const [texts, setTexts] = useState({})
  const [error, setError] = useState('')

  // A new result (or another restaurant) starts from scratch, reset during
  // render (see "resetting state when a prop changes":
  // https://react.dev/learn/you-might-not-need-an-effect).
  const resultKey = kind === 'whatif' ? simulateResult : runAt
  const runKey = `${restaurantId}:${kind}:${resultKey}`
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
    const request = kind === 'whatif'
      ? fetchWhatIfSummary(restaurantId, simulateResult, { style, signal: controller.signal })
      : fetchForecastSummary(restaurantId, { style, signal: controller.signal })
    request
      .then((data) => setTexts((prev) => ({ ...prev, [style]: data.summary })))
      .catch((err) => { if (err.name !== 'AbortError') setError(err.message) })
    return () => controller.abort()
  }, [kind, restaurantId, runAt, simulateResult, style, text])

  function choose(next) {
    setError('')
    setStyle(next)
  }

  const loading = text === undefined && !error
  const source = kind === 'whatif' ? 'this simulation' : 'your forecast'

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
      <p className="ai-credit">Written by Snowflake Cortex{model ? ` (${model})` : ''} from {source} numbers only.</p>
    </section>
  )
}
