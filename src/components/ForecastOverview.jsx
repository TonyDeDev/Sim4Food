import { useEffect, useState } from 'react'
import AiOverview from './AiOverview.jsx'
import { fetchInsightsStatus, fetchLatestForecast, runForecast } from '../utils/api.js'
import { formatDateTime, formatDay, formatMoney, formatPct, formatWeekRange } from '../utils/format.js'
import OrderBacktest from './OrderBacktest.jsx'
import RecommendationsTable from './RecommendationsTable.jsx'
import StatCard from './StatCard.jsx'

export default function ForecastOverview({ restaurantId }) {
  const [state, setState] = useState({ status: 'loading' })
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState('')
  const [assistant, setAssistant] = useState(null)

  // Reset to loading synchronously during render when restaurantId changes,
  // rather than inside the effect (see "resetting state when a prop
  // changes": https://react.dev/learn/you-might-not-need-an-effect).
  const [syncedFor, setSyncedFor] = useState(null)
  if (syncedFor !== restaurantId) {
    setSyncedFor(restaurantId)
    setState({ status: 'loading' })
  }

  useEffect(() => {
    let cancelled = false
    fetchLatestForecast(restaurantId)
      .then((data) => { if (!cancelled) setState({ status: 'ok', runAt: data.run_at, forecast: data.forecast }) })
      .catch((err) => { if (!cancelled) setState({ status: 'error', message: err.message }) })
    return () => { cancelled = true }
  }, [restaurantId])

  useEffect(() => {
    let cancelled = false
    fetchInsightsStatus()
      .then((data) => { if (!cancelled) setAssistant(data) })
      .catch(() => { if (!cancelled) setAssistant({ configured: false }) })
    return () => { cancelled = true }
  }, [])

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
  // Runs stored before order recommendations existed have no savings block: ask for a re-run.
  const ready = forecast?.ingredients?.length > 0 && forecast.savings

  return (
    <>
      <div className="forecast-run-bar">
        <p className="hint">
          {running ? 'Training the forecast and simulating your week…' : runAt ? `Last run: ${formatDateTime(runAt)}` : 'No forecast has been run yet.'}
        </p>
        <button type="button" className="btn-pastel" onClick={handleRun} disabled={running}>
          {running ? 'Running…' : runAt ? 'Re-run forecast' : 'Run forecast'}
        </button>
      </div>
      {runError && <p className="field-error" role="alert">{runError}</p>}

      {!forecast ? (
        <p className="hint">Click &quot;Run forecast&quot; to train a model on your uploaded sales and recipes.</p>
      ) : !ready ? (
        <p className="hint">
          {forecast.ingredients?.length > 0
            ? 'This forecast was made before order recommendations existed. Re-run it to see what to order.'
            : forecast.data.message}
        </p>
      ) : (
        <ForecastResults forecast={forecast} restaurantId={restaurantId} runAt={runAt} assistant={assistant} />
      )}
    </>
  )
}

function ForecastResults({ forecast, restaurantId, runAt, assistant }) {
  const { data, accuracy, savings, events, ingredients } = forecast
  const methods = accuracy?.methods
  const coverage = accuracy?.band_coverage
  const backtest = savings.order_backtest
  const leftoverChange = backtest?.waste_reduction_pct

  return (
    <>
      <section className="stat-grid" aria-label="Forecast summary">
        <StatCard
          label="Order for the week of"
          value={formatWeekRange(data.target_week)}
          sub={`based on sales through ${formatDay(data.based_on_sales_through)}`}
        />
        <StatCard
          label="Perishable leftovers vs your orders"
          value={leftoverChange != null ? `${leftoverChange > 0 ? '-' : '+'}${Math.round(Math.abs(leftoverChange))}%` : '-'}
          tone={leftoverChange > 0 ? 'good' : leftoverChange < 0 ? 'warn' : undefined}
          sub={backtest
            ? `last ${backtest.weeks} weeks replayed: ${formatMoney(backtest.total_savings)} net after lost profit`
            : 'needs stock counts and purchases'}
        />
        <StatCard
          label="Forecast error"
          value={methods ? formatPct(methods.xgboost.wape, 1) : '-'}
          sub={methods
            ? `lower is better: same-weekday average ${formatPct(methods.dish_baseline.wape, 1)}, repeating last week ${formatPct(methods.naive_last_week.wape, 1)}`
            : 'not enough history yet to check'}
        />
        <StatCard
          label="Range hit rate"
          value={coverage ? formatPct(coverage.inside_p10_p90) : '-'}
          sub={coverage
            ? `actual use landed in our likely range (target ${formatPct(coverage.target_inside)})`
            : 'not enough history yet to check'}
        />
      </section>

      {(data.status !== 'established' || data.stale) && (
        <section className="alert-card" aria-label="Forecast confidence">
          <div className="alert-card-head">
            <h2>{data.stale ? 'Your sales data is out of date' : data.status === 'learning' ? 'Still learning' : 'Getting sharper'}</h2>
          </div>
          <p className="alert-subtitle">{data.message}</p>
          <p className="alert-footer">{data.method_reason}</p>
        </section>
      )}

      {events.length > 0 && (
        <section className="alert-card" aria-label="Events this week">
          {events.map((ev) => (
            <div key={`${ev.name}-${ev.start_date}`} className="event-line">
              <span className={`badge ${ev.type === 'deal' ? 'badge-warn' : 'badge-neutral'}`}>{ev.type === 'deal' ? 'Deal' : 'Holiday'}</span>
              <span className="event-name">{ev.name}</span>
              <span className="hint">
                {formatDay(ev.start_date)}{ev.end_date !== ev.start_date ? ` to ${formatDay(ev.end_date)}` : ''}
                {ev.lift_pct != null
                  ? `: ${ev.lift_pct > 0 ? '+' : ''}${ev.lift_pct}% on the dishes it covers (${ev.lift_source === 'owner' ? 'your estimate' : 'learned from your past events'})`
                  : ': no past events like it yet, so no change is applied'}
              </span>
            </div>
          ))}
        </section>
      )}

      {assistant?.configured ? (
        <AiOverview kind="forecast" restaurantId={restaurantId} runAt={runAt} model={assistant.model} />
      ) : assistant && (
        <p className="hint ai-off">The AI assistant (Snowflake Cortex) is not set up on this server yet.</p>
      )}

      <div className="section-head">
        <h2>What to order</h2>
        <p className="hint">
          Deliveries on {savings.delivery_days.join(' and ')}, as in your purchase history. The first delivery is firm;
          later ones are a plan to re-check against your stock on the day.
          {data.gap_weeks > 0 && (
            <> Stock on hand is projected to {formatDay(data.target_week)} from your last count, assuming no
            deliveries since {formatDay(data.based_on_sales_through)}. Upload a fresh count for a sharper order.</>
          )}
        </p>
      </div>
      <RecommendationsTable ingredients={ingredients} />

      <OrderBacktest backtest={backtest} />
    </>
  )
}
