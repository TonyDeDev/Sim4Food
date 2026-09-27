import { formatDay, formatMoney } from '../utils/format.js'

// Replays past weeks: what our orders would have wasted and missed vs what was actually bought.
export default function OrderBacktest({ backtest }) {
  if (!backtest) return null
  const { ours, actual } = backtest
  return (
    <section className="backtest-section" aria-label="Order backtest">
      <div className="section-head">
        <h2>How our orders would have done</h2>
        <p className="hint">
          Last {backtest.weeks} weeks, replayed on your real sales and stock counts, against what you actually bought.
        </p>
      </div>
      <div className="inventory-table-wrap">
        <table className="inventory-table">
          <thead>
            <tr>
              <th>Week of</th>
              <th>Your waste</th>
              <th>Our waste</th>
              <th>Your missed sales</th>
              <th>Our missed sales</th>
            </tr>
          </thead>
          <tbody>
            {backtest.by_week.map((w) => (
              <tr key={w.week}>
                <td>{formatDay(w.week)}</td>
                <td>{formatMoney(w.actual_waste)}</td>
                <td className={w.ours_waste < w.actual_waste ? 'better' : undefined}>{formatMoney(w.ours_waste)}</td>
                <td>{formatMoney(w.actual_lost)}</td>
                <td className={w.ours_lost < w.actual_lost ? 'better' : undefined}>{formatMoney(w.ours_lost)}</td>
              </tr>
            ))}
            <tr className="total-row">
              <td>Total</td>
              <td>{formatMoney(actual.waste_cost)}</td>
              <td className={ours.waste_cost < actual.waste_cost ? 'better' : undefined}>{formatMoney(ours.waste_cost)}</td>
              <td>{formatMoney(actual.lost_margin)}</td>
              <td className={ours.lost_margin < actual.lost_margin ? 'better' : undefined}>{formatMoney(ours.lost_margin)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  )
}
