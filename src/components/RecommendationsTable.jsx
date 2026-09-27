import { formatMoney, formatQty } from '../utils/format.js'
import Sparkline from './Sparkline.jsx'

const DAY_SHORT = { Monday: 'Mon', Tuesday: 'Tue', Wednesday: 'Wed', Thursday: 'Thu', Friday: 'Fri', Saturday: 'Sat', Sunday: 'Sun' }

function riskBadge(risk) {
  if (risk === null || risk === undefined) return <span className="pending-note">-</span>
  const pct = Math.round(risk * 100)
  const tone = pct >= 25 ? 'bad' : pct >= 10 ? 'warn' : 'good'
  return <span className={`badge badge-${tone}`}>{pct}%</span>
}

function Deliveries({ deliveries, unit }) {
  return (
    <ul className="delivery-list">
      {deliveries.map((d) => (
        <li key={d.day} className={d.firm ? 'firm' : 'planned'} title={d.firm ? 'Order now' : 'Planned: re-check stock on the day'}>
          <span className="delivery-day">{DAY_SHORT[d.day] ?? d.day}</span>
          {formatQty(d.qty, unit)}
        </li>
      ))}
    </ul>
  )
}

function VersusHabit({ rec, unit }) {
  if (rec.habit_order_qty === null || rec.habit_order_qty === undefined) return <span className="pending-note">-</span>
  const diff = rec.order_qty - rec.habit_order_qty
  if (Math.abs(diff) < 1e-9) return <span className="muted">Same</span>
  return (
    <span className={diff > 0 ? 'diff-up' : 'diff-down'}>
      {diff > 0 ? '+' : '-'}{formatQty(Math.abs(diff), unit)}
    </span>
  )
}

export default function RecommendationsTable({ ingredients }) {
  return (
    <div className="inventory-table-wrap">
      <table className="inventory-table recommendations-table">
        <thead>
          <tr>
            <th>Ingredient</th>
            <th>Trend</th>
            <th>Likely use</th>
            <th>On hand Mon</th>
            <th>Order</th>
            <th>vs usual</th>
            <th>Run-out risk</th>
            <th>Leftover risk</th>
          </tr>
        </thead>
        <tbody>
          {ingredients.map((row) => {
            const rec = row.recommendation
            const f = row.forecast
            return (
              <tr key={row.ingredient_id}>
                <td>
                  <span className="ingredient-name">{row.name}</span>
                  {f.event_adjustment_pct ? (
                    <span className="event-chip">{f.event_adjustment_pct > 0 ? '+' : ''}{f.event_adjustment_pct}% event</span>
                  ) : null}
                </td>
                <td><Sparkline values={row.history.map((h) => h.usage)} width={72} height={24} /></td>
                <td>
                  {f.p10 != null && f.p90 != null ? (
                    <>
                      <span className="range-main">{formatQty(f.p50, row.unit)}</span>
                      <span className="range-sub">{formatQty(f.p10)} to {formatQty(f.p90, row.unit)}</span>
                    </>
                  ) : (
                    formatQty(f.point, row.unit)
                  )}
                </td>
                <td>{rec.on_hand === null ? <span className="pending-note">No count</span> : formatQty(rec.on_hand, row.unit)}</td>
                <td>
                  <span className="order-total">{formatQty(rec.order_qty, row.unit)}</span>
                  {rec.packs ? <span className="range-sub">{rec.packs} packs of {formatQty(rec.pack_size)}</span> : null}
                  {rec.deliveries.length > 1 && <Deliveries deliveries={rec.deliveries} unit={row.unit} />}
                </td>
                <td><VersusHabit rec={rec} unit={row.unit} /></td>
                <td>{riskBadge(rec.stockout_risk)}</td>
                <td>{rec.perishable ? formatMoney(rec.expected_waste_cost) : <span className="muted">Keeps</span>}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
