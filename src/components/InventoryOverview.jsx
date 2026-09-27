import { useEffect, useMemo, useState } from 'react'
import { fetchHomeSummary, fetchInventory, fetchLatestForecast } from '../utils/api.js'
import { formatDate, formatDateTime } from '../utils/format.js'
import StatCard from './StatCard.jsx'

const LOW_RUNWAY_DAYS = 3

function money(value) {
  return `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

function changeText(pct, { positiveIsGood }) {
  if (pct === null || pct === undefined) return { text: 'no prior week to compare', good: null }
  const sign = pct > 0 ? '+' : ''
  const good = pct === 0 ? null : positiveIsGood ? pct > 0 : pct < 0
  return { text: `${sign}${pct}% vs prior week`, good }
}

function runwayDays(row) {
  if (row.qty_on_hand === null || !row.avg_daily_consumption) return null
  return row.qty_on_hand / row.avg_daily_consumption
}

function stockStatus(row) {
  if (row.qty_on_hand === null) return { label: 'No count', tone: 'neutral' }
  if (row.qty_on_hand <= 0) return { label: 'Out', tone: 'bad' }
  const days = runwayDays(row)
  if (days !== null && days < LOW_RUNWAY_DAYS) return { label: 'Low', tone: 'warn' }
  return { label: 'OK', tone: 'good' }
}

function Skeleton() {
  return (
    <section className="stat-grid" aria-label="Loading summary" aria-busy="true">
      {Array.from({ length: 4 }).map((_, i) => (
        <div className="stat-card skeleton" key={i}>
          <div className="skeleton-line skeleton-line-label" />
          <div className="skeleton-line skeleton-line-value" />
          <div className="skeleton-line skeleton-line-sub" />
        </div>
      ))}
    </section>
  )
}

export default function InventoryOverview({ restaurantId }) {
  const [inventoryState, setInventoryState] = useState({ status: 'loading' })
  const [summaryState, setSummaryState] = useState({ status: 'loading' })
  // undefined = still loading, null = never run/failed - kept separate so a
  // failure here never blocks the rest of the tab.
  const [forecastRunAt, setForecastRunAt] = useState(undefined)
  const [search, setSearch] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  // Reset all three to their loading state synchronously during render when
  // the restaurant or a manual retry changes, rather than inside each
  // effect (see "resetting state when a prop changes":
  // https://react.dev/learn/you-might-not-need-an-effect).
  const requestKey = `${restaurantId}:${reloadKey}`
  const [syncedFor, setSyncedFor] = useState(null)
  if (syncedFor !== requestKey) {
    setSyncedFor(requestKey)
    setInventoryState({ status: 'loading' })
    setSummaryState({ status: 'loading' })
    setForecastRunAt(undefined)
  }

  useEffect(() => {
    let cancelled = false
    fetchInventory(restaurantId)
      .then((data) => { if (!cancelled) setInventoryState({ status: 'ok', data }) })
      .catch((err) => { if (!cancelled) setInventoryState({ status: 'error', message: err.message }) })
    return () => { cancelled = true }
  }, [restaurantId, reloadKey])

  useEffect(() => {
    let cancelled = false
    fetchHomeSummary(restaurantId)
      .then((data) => { if (!cancelled) setSummaryState({ status: 'ok', data }) })
      .catch((err) => { if (!cancelled) setSummaryState({ status: 'error', message: err.message }) })
    return () => { cancelled = true }
  }, [restaurantId, reloadKey])

  useEffect(() => {
    let cancelled = false
    fetchLatestForecast(restaurantId)
      .then((data) => { if (!cancelled) setForecastRunAt(data.run_at) })
      .catch(() => { if (!cancelled) setForecastRunAt(null) })
    return () => { cancelled = true }
  }, [restaurantId, reloadKey])

  const rows = useMemo(() => {
    if (inventoryState.status !== 'ok') return []
    const list = inventoryState.data.ingredients
    const filtered = search.trim()
      ? list.filter((row) => row.name.toLowerCase().includes(search.trim().toLowerCase()))
      : list
    // Most urgent first: out, then low (soonest runway), then the rest by name.
    const rank = (row) => {
      const status = stockStatus(row).tone
      if (status === 'bad') return 0
      if (status === 'warn') return 1
      return 2
    }
    return [...filtered].sort((a, b) => {
      const diff = rank(a) - rank(b)
      if (diff !== 0) return diff
      const da = runwayDays(a)
      const db = runwayDays(b)
      if (da !== null && db !== null && da !== db) return da - db
      return a.name.localeCompare(b.name)
    })
  }, [inventoryState, search])

  if (inventoryState.status === 'error') {
    return (
      <p className="field-error" role="alert">
        {inventoryState.message}{' '}
        <button type="button" className="btn-link" onClick={() => setReloadKey((k) => k + 1)}>Retry</button>
      </p>
    )
  }

  if (inventoryState.status === 'loading') return <Skeleton />

  const { summary } = inventoryState.data
  if (inventoryState.data.ingredients.length === 0) {
    return <p className="hint">Upload ingredients, sales, and an inventory count to see your current stock.</p>
  }

  const home = summaryState.status === 'ok' ? summaryState.data : null

  return (
    <>
      <section className="stat-grid" aria-label="Business summary">
        {summaryState.status === 'loading' ? (
          <>
            <div className="stat-card skeleton"><div className="skeleton-line skeleton-line-label" /><div className="skeleton-line skeleton-line-value" /><div className="skeleton-line skeleton-line-sub" /></div>
            <div className="stat-card skeleton"><div className="skeleton-line skeleton-line-label" /><div className="skeleton-line skeleton-line-value" /><div className="skeleton-line skeleton-line-sub" /></div>
            <div className="stat-card skeleton"><div className="skeleton-line skeleton-line-label" /><div className="skeleton-line skeleton-line-value" /><div className="skeleton-line skeleton-line-sub" /></div>
            <div className="stat-card skeleton"><div className="skeleton-line skeleton-line-label" /><div className="skeleton-line skeleton-line-value" /><div className="skeleton-line skeleton-line-sub" /></div>
          </>
        ) : summaryState.status === 'error' ? (
          <p className="field-error" role="alert">
            {summaryState.message}{' '}
            <button type="button" className="btn-link" onClick={() => setReloadKey((k) => k + 1)}>Retry</button>
          </p>
        ) : (
          <>
            <StatCard
              label="Revenue (7 days)"
              value={home.revenue.as_of ? money(home.revenue.last7) : '-'}
              delta={home.revenue.as_of ? changeText(home.revenue.change_pct, { positiveIsGood: true }) : null}
              sub={home.revenue.as_of ? `through ${formatDate(home.revenue.as_of)}` : 'upload sales to see this'}
            />

            <StatCard
              label="Waste cost (last week)"
              value={home.waste.week_start ? money(home.waste.last_week_cost) : '-'}
              delta={home.waste.week_start ? changeText(home.waste.change_pct, { positiveIsGood: false }) : null}
              sub={home.waste.top_ingredient ? `most: ${home.waste.top_ingredient}` : 'no waste recorded yet'}
            />

            <StatCard
              label="Stock health"
              value={home.stock.out_count > 0
                ? `${home.stock.out_count} out`
                : home.stock.low_count > 0
                  ? `${home.stock.low_count} low`
                  : 'All OK'}
              tone={home.stock.out_count > 0 ? 'bad' : home.stock.low_count > 0 ? 'warn' : 'good'}
              sub={home.stock.most_urgent
                ? `${home.stock.most_urgent}: ${home.stock.most_urgent_days}d left`
                : `${money(home.stock.stock_value)} on hand`}
            />

            <StatCard
              label="Next event"
              value={home.next_event ? home.next_event.name : 'None planned'}
              sub={home.next_event
                ? home.next_event.days_until === 0 ? 'starts today' : `in ${home.next_event.days_until} day${home.next_event.days_until === 1 ? '' : 's'}`
                : 'upload deals and holidays under Records'}
            />
          </>
        )}
      </section>

      {summary.missing_count > 0 && (
        <section className="alert-card" aria-label="Ingredients missing a stock count">
          <div className="alert-card-head">
            <h2>{summary.missing_count} ingredient{summary.missing_count === 1 ? '' : 's'} missing a stock count</h2>
          </div>
          <p className="alert-subtitle">Upload an inventory count for these to start tracking them here.</p>
        </section>
      )}

      {forecastRunAt === null && (
        <section className="alert-card" aria-label="Forecast status">
          <div className="alert-card-head">
            <h2>No forecast yet</h2>
          </div>
          <p className="alert-subtitle">Run one from the Forecast tab to get order recommendations.</p>
        </section>
      )}
      {forecastRunAt && (
        <p className="hint last-forecast-hint">Last forecast: {formatDateTime(forecastRunAt)}</p>
      )}

      <div className="table-toolbar">
        <input
          type="search"
          className="table-search"
          placeholder="Search ingredients…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search ingredients"
        />
      </div>

      <div className="inventory-table-wrap">
        <table className="inventory-table">
          <thead>
            <tr>
              <th>Ingredient</th>
              <th>On hand</th>
              <th>Avg. used / day</th>
              <th>Est. runway</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const days = runwayDays(row)
              const status = stockStatus(row)
              return (
                <tr key={row.ingredient_id}>
                  <td>{row.name}</td>
                  <td>{row.qty_on_hand === null ? 'No count uploaded' : `${row.qty_on_hand} ${row.unit}`}</td>
                  <td>{row.avg_daily_consumption ? `${row.avg_daily_consumption} ${row.unit}` : '-'}</td>
                  <td>{days === null ? <span className="pending-note">Not enough data</span> : `${days.toFixed(1)} days`}</td>
                  <td><span className={`badge badge-${status.tone}`}>{status.label}</span></td>
                </tr>
              )
            })}
            {rows.length === 0 && (
              <tr><td colSpan={5} className="hint">No ingredients match &quot;{search}&quot;.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  )
}
