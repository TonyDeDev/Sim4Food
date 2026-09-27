import { formatDay, formatMoney } from '../utils/format.js'

// Replays past weeks: perishable leftovers and lost profit with our orders vs what was actually bought.
export default function OrderBacktest({ backtest }) {
  if (!backtest) return null
  const { ours, actual } = backtest
  return (
    <section className="backtest-section" aria-label="Order backtest">
      <div className="section-head">
        <h2>How our orders would have done</h2>
        <p className="hint">
          Last {backtest.weeks} weeks, replayed on your real sales and stock counts, against what you actually bought.
          Leftovers are perishable stock still on the shelf at the end of the week; lost profit is from running out.
        </p>
      </div>
      <div className="inventory-table-wrap">
        <table className="inventory-table">
          <thead>
            <tr>
              <th>Week of</th>
              <th>Your leftovers</th>
              <th>Our leftovers</th>
              <th>Your lost profit</th>
              <th>Our lost profit</th>
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
