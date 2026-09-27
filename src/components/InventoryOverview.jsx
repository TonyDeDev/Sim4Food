const STATUS_LABEL = { critical: 'Critical', watch: 'Watch', ok: 'Healthy', unknown: 'Unknown' }

// Placeholder data in the exact shape GET /api/inventory returns (see
// backend/sim/inventory.py's build_inventory_report). Swap MOCK_DATA for a
// real fetch once the forecasting teammate's numbers are ready to wire in -
// the markup below does not need to change.
const MOCK_DATA = {
  summary: { tracked: 12, critical: 1, watch: 3, ok: 8 },
  ingredients: [
    { ingredient_id: 'eggs', name: 'Eggs', unit: 'dozen', qty_on_hand: 2.0, avg_daily_consumption: 2.2, days_remaining: 0.9, status: 'critical' },
    { ingredient_id: 'chicken', name: 'Chicken breast', unit: 'kg', qty_on_hand: 4.5, avg_daily_consumption: 3.1, days_remaining: 1.5, status: 'watch' },
    { ingredient_id: 'romaine', name: 'Romaine lettuce', unit: 'kg', qty_on_hand: 6.0, avg_daily_consumption: 2.8, days_remaining: 2.1, status: 'watch' },
    { ingredient_id: 'tomato', name: 'Tomato', unit: 'kg', qty_on_hand: 9.0, avg_daily_consumption: 3.4, days_remaining: 2.6, status: 'watch' },
    { ingredient_id: 'bun', name: 'Burger bun', unit: 'each', qty_on_hand: 62.0, avg_daily_consumption: 8.0, days_remaining: 7.8, status: 'ok' },
    { ingredient_id: 'cheddar', name: 'Cheddar', unit: 'kg', qty_on_hand: 5.0, avg_daily_consumption: 0.6, days_remaining: 8.3, status: 'ok' },
    { ingredient_id: 'penne', name: 'Penne pasta', unit: 'kg', qty_on_hand: 12.0, avg_daily_consumption: 1.1, days_remaining: 10.9, status: 'ok' },
    { ingredient_id: 'cream', name: 'Heavy cream', unit: 'L', qty_on_hand: 8.0, avg_daily_consumption: 0.7, days_remaining: 11.4, status: 'ok' },
    { ingredient_id: 'parmesan', name: 'Parmesan', unit: 'kg', qty_on_hand: 3.0, avg_daily_consumption: 0.2, days_remaining: 15.0, status: 'ok' },
    { ingredient_id: 'fries_frozen', name: 'Frozen fries', unit: 'kg', qty_on_hand: 30.0, avg_daily_consumption: 1.9, days_remaining: 15.8, status: 'ok' },
    { ingredient_id: 'tortilla', name: 'Tortilla wrap', unit: 'each', qty_on_hand: 80.0, avg_daily_consumption: 5.0, days_remaining: 16.0, status: 'ok' },
    { ingredient_id: 'beef_patty', name: 'Beef patty 6oz', unit: 'each', qty_on_hand: 96.0, avg_daily_consumption: 5.4, days_remaining: 17.8, status: 'ok' },
  ],
}

function formatDays(days) {
  if (days === null || days === undefined) return 'Not enough data'
  if (days <= 0) return 'Out of stock'
  return `~${days} day${days === 1 ? '' : 's'}`
}

export default function InventoryOverview() {
  const { ingredients, summary } = MOCK_DATA
  const topAlert = ingredients.find((row) => row.status === 'critical' || row.status === 'watch')

  return (
    <>
      <section className="stat-grid" aria-label="Inventory summary">
        <div className="stat-card">
          <p className="stat-label">Ingredients tracked</p>
          <p className="stat-value">{summary.tracked}</p>
          <p className="stat-sub">of {ingredients.length} uploaded</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Critical</p>
          <p className="stat-value">{summary.critical}</p>
          <p className="stat-sub">reorder now</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Watch</p>
          <p className="stat-value">{summary.watch}</p>
          <p className="stat-sub">order soon</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Healthy</p>
          <p className="stat-value">{summary.ok}</p>
          <p className="stat-sub">stocked for now</p>
        </div>
      </section>

      {topAlert && (
        <section className="alert-card" aria-label="Most urgent ingredient">
          <div className="alert-card-head">
            <h2>{topAlert.name} — reorder recommended</h2>
            <span className={`priority-badge ${topAlert.status}`}>{STATUS_LABEL[topAlert.status]}</span>
          </div>
          <p className="alert-subtitle">Estimate: stockout in {formatDays(topAlert.days_remaining)}</p>
          <div className="stock-bar">
            <div
              className={`stock-bar-fill ${topAlert.status}`}
              style={{ width: `${Math.max(0, Math.min(100, ((topAlert.days_remaining || 0) / 7) * 100))}%` }}
            />
          </div>
          <p className="alert-footer">Placeholder data - real forecast coming soon.</p>
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
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {ingredients.map((row) => (
              <tr key={row.ingredient_id}>
                <td>{row.name}</td>
                <td>{row.qty_on_hand === null ? 'No count uploaded' : `${row.qty_on_hand} ${row.unit}`}</td>
                <td>{row.avg_daily_consumption ? `${row.avg_daily_consumption} ${row.unit}` : '—'}</td>
                <td>{formatDays(row.days_remaining)}</td>
                <td><span className={`priority-badge ${row.status}`}>{STATUS_LABEL[row.status]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
