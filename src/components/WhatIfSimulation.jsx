'use client'

import { useEffect, useState } from 'react'
import { API_URL, fetchInsightsStatus } from '../utils/api'
import AiOverview from './AiOverview.jsx'
import SimView from './SimView.jsx'

const money = (value) => `$${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const qty = (value) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
const pct = (value) => (value == null ? '-' : `${(Number(value) * 100).toFixed(0)}%`)

export default function WhatIfSimulation({ restaurantId, restaurantName }) {
  const [dealPct, setDealPct] = useState(0)
  const [holiday, setHoliday] = useState(false)
  const [socialInfluence, setSocialInfluence] = useState(false)
  const [menu, setMenu] = useState([])
  const [ingredients, setIngredients] = useState([])
  const [itemId, setItemId] = useState('')
  const [stockIngredientId, setStockIngredientId] = useState('')
  const [stockQty, setStockQty] = useState('')
  const [deliveryIngredientId, setDeliveryIngredientId] = useState('')
  const [deliveryQty, setDeliveryQty] = useState('')
  const [deliveryDelayDays, setDeliveryDelayDays] = useState(0)
  const [result, setResult] = useState(null)
  // Bumped per completed run so the replay animation remounts and plays again.
  const [runSeq, setRunSeq] = useState(0)
  // The week plays out before the numbers land, so the animation is watched
  // rather than skipped past. A run without a replay reveals immediately.
  const [revealed, setRevealed] = useState(false)
  const [error, setError] = useState('')
  const [configError, setConfigError] = useState('')
  const [loading, setLoading] = useState(false)
  const [assistant, setAssistant] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetchInsightsStatus()
      .then((data) => { if (!cancelled) setAssistant(data) })
      .catch(() => { if (!cancelled) setAssistant({ configured: false }) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!restaurantId) return
    let active = true
    fetch(`${API_URL}/api/menu?restaurant_id=${encodeURIComponent(restaurantId)}`, { credentials: 'include' }).then(async (response) => {
      if (!response.ok) throw new Error('Could not load inventory controls')
      const data = await response.json()
      if (!active) return
      const loadedIngredients = data.ingredients || []
      setMenu(data.menu || [])
      setIngredients(loadedIngredients)
      setItemId(data.menu?.[0]?.id || '')
      setStockIngredientId(loadedIngredients[0]?.id || '')
      setDeliveryIngredientId(loadedIngredients[0]?.id || '')
      setStockQty(loadedIngredients[0] ? String(loadedIngredients[0].qty_on_hand) : '')
    }).catch(() => { if (active) setConfigError('Inventory controls could not load. Check that the backend is running, then refresh.') })
    return () => { active = false }
  }, [restaurantId])

  function selectStockIngredient(id) {
    setStockIngredientId(id)
    const ingredient = ingredients.find((entry) => entry.id === id)
    setStockQty(ingredient ? String(ingredient.qty_on_hand) : '')
  }

  async function handleRun(event) {
    event.preventDefault()
    setLoading(true); setError(''); setResult(null)
    const stockOverrides = stockIngredientId && stockQty !== '' ? { [stockIngredientId]: Number(stockQty) } : {}
    try {
      const response = await fetch(`${API_URL}/api/simulate?restaurant_id=${encodeURIComponent(restaurantId)}`, {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          item_id: itemId, discount_pct: dealPct, holiday, social_influence: socialInfluence,
          stock_overrides: stockOverrides, delivery_ingredient_id: deliveryIngredientId,
          delivery_qty: deliveryQty === '' ? 0 : Number(deliveryQty),
          delivery_delay_days: deliveryDelayDays, runs: 300,
        }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || 'Could not run the simulation')
      setMenu(data.menu || menu); setResult(data); setRunSeq((value) => value + 1)
      setRevealed(!data.replay)
    } catch (e) { setError(e.message) } finally { setLoading(false) }
  }

  const delta = result?.comparison
  const stockIngredient = ingredients.find((entry) => entry.id === stockIngredientId)
  const verdict = result?.plan_comparison
  const recommended = result?.plans?.recommended
  const planRows = recommended?.ingredients || []
  const highestWaste = [...planRows].filter((row) => row.waste.p50 > 0)
    .sort((a, b) => b.waste_cost - a.waste_cost).slice(0, 3)
  const stockRisks = [...planRows].filter((row) => row.stockout_probability > 0)
    .sort((a, b) => b.stockout_probability - a.stockout_probability).slice(0, 5)
  const splitCount = planRows.filter((row) => (row.delivery_days || []).length > 1).length
  const financeRows = result ? [
    ['Revenue', result.baseline.revenue.p50, result.scenario.revenue.p50],
    ['Ingredient cost', result.baseline.food_cost.p50, result.scenario.food_cost.p50],
    ['Expired food cost', result.baseline.waste_cost.p50, result.scenario.waste_cost.p50],
    ['Lost-sales cost', result.baseline.lost_sales_cost.p50, result.scenario.lost_sales_cost.p50],
    ['Profit after waste and lost sales', result.baseline.profit.p50, result.scenario.profit.p50],
  ] : []

  return <>
    <p className="hint">Test a promotion against shared inventory. Each order checks recipe availability; guests may accept an available alternative or leave if stock is short.</p>
    <form className="whatif-controls" onSubmit={handleRun}>
      <div className="whatif-slider">
        <label htmlFor="whatif-item">Promoted item</label>
        <select id="whatif-item" value={itemId} onChange={(e) => setItemId(e.target.value)} disabled={!menu.length}>
          {menu.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
        </select>
      </div>
      <div className="whatif-slider">
        <label htmlFor="whatif-deal">Deal discount</label>
        <input id="whatif-deal" type="range" min="0" max="50" step="5" value={dealPct} onChange={(e) => setDealPct(Number(e.target.value))} />
        <p className="hint">{dealPct === 0 ? 'No deal' : `${dealPct}% off`}</p>
      </div>
      <section className="whatif-panel" aria-labelledby="whatif-stock-title">
        <div className="whatif-panel-head"><h3 id="whatif-stock-title">Starting inventory</h3><p>Replace one recorded opening balance for this scenario. Opening stock is assumed fresh because lot ages are not recorded.</p></div>
        <div className="whatif-field-grid">
          <div><label htmlFor="whatif-stock-ingredient">Ingredient</label><select id="whatif-stock-ingredient" value={stockIngredientId} onChange={(e) => selectStockIngredient(e.target.value)} disabled={!ingredients.length}>{ingredients.map((ingredient) => <option value={ingredient.id} key={ingredient.id}>{ingredient.name}</option>)}</select></div>
          <div><label htmlFor="whatif-stock-qty">Opening quantity{stockIngredient ? ` (${stockIngredient.unit})` : ''}</label><input id="whatif-stock-qty" type="number" min="0" step="any" value={stockQty} onChange={(e) => setStockQty(e.target.value)} disabled={!stockIngredientId} /></div>
        </div>
        {configError && <p className="whatif-panel-error" role="status">{configError}</p>}
      </section>
      <section className="whatif-panel" aria-labelledby="whatif-delivery-title">
        <div className="whatif-panel-head"><h3 id="whatif-delivery-title">Supplier delivery</h3><p>Add an expected delivery, then test the effect of a delay.</p></div>
        <div className="whatif-field-grid">
          <div><label htmlFor="whatif-delivery-ingredient">Ingredient</label><select id="whatif-delivery-ingredient" value={deliveryIngredientId} onChange={(e) => setDeliveryIngredientId(e.target.value)} disabled={!ingredients.length}>{ingredients.map((ingredient) => <option value={ingredient.id} key={ingredient.id}>{ingredient.name}</option>)}</select></div>
          <div><label htmlFor="whatif-delivery-qty">Delivery quantity</label><input id="whatif-delivery-qty" type="number" min="0" step="any" value={deliveryQty} placeholder="0" onChange={(e) => setDeliveryQty(e.target.value)} disabled={!deliveryIngredientId} /></div>
        </div>
        <div className="whatif-delay-row"><label htmlFor="whatif-delivery-delay">Delay: <strong>{deliveryDelayDays} day{deliveryDelayDays === 1 ? '' : 's'}</strong></label><input id="whatif-delivery-delay" type="range" min="0" max="6" step="1" value={deliveryDelayDays} onChange={(e) => setDeliveryDelayDays(Number(e.target.value))} disabled={deliveryQty === '' || Number(deliveryQty) <= 0} /></div>
      </section>
      <div className="whatif-toggles" aria-label="Demand conditions">
        <div className="remember-row"><input type="checkbox" id="whatif-holiday" checked={holiday} onChange={(e) => setHoliday(e.target.checked)} /><label htmlFor="whatif-holiday">Holiday demand uplift (20%)</label></div>
        <div className="remember-row"><input type="checkbox" id="whatif-social" checked={socialInfluence} onChange={(e) => setSocialInfluence(e.target.checked)} /><label htmlFor="whatif-social">Word-of-mouth demand uplift (10%)</label></div>
      </div>
      <button type="submit" className="btn-pastel" disabled={loading || !restaurantId}>{loading ? 'Simulating…' : 'Run comparison'}</button>
    </form>
    {error && <section className="alert-card" role="alert"><h2>Simulation could not run</h2><p>{error}</p></section>}
    {result && <section className="whatif-results" aria-label="Simulation results">
      <h2>What to do next week</h2>
      <p className="hint">We ran next week {result.runs} times. Your usual ordering rule and the recommendation face the identical {result.runs} versions of it, so the only difference is what you buy and when it arrives.</p>

      {result.replay && <SimView
        key={runSeq}
        replay={result.replay}
        runs={result.runs}
        restaurantName={restaurantName}
        onFinish={() => setRevealed(true)}
      />}

      {revealed && <>

      <div className="whatif-stat-row">
        <div className="whatif-stat">
          <span className="whatif-stat-label">Food thrown away</span>
          <strong className="whatif-stat-value">{money(recommended.waste_cost.p50)}</strong>
          <span className={`whatif-stat-delta${verdict.waste_cost_saving > 0 ? ' is-good' : ''}`}>
            {verdict.waste_cost_saving > 0 ? `${money(verdict.waste_cost_saving)} less than your usual rule` : 'Same as your usual rule'}
          </span>
        </div>
        <div className="whatif-stat">
          <span className="whatif-stat-label">Demand you can serve</span>
          <strong className="whatif-stat-value">{pct(verdict.service_level_recommended)}</strong>
          <span className={`whatif-stat-delta${verdict.service_level_recommended >= verdict.service_level_habit ? ' is-good' : ' is-bad'}`}>
            Usual rule serves {pct(verdict.service_level_habit)}
          </span>
        </div>
        <div className="whatif-stat">
          <span className="whatif-stat-label">Spend on ingredients</span>
          <strong className="whatif-stat-value">{money(recommended.order_cost)}</strong>
          <span className={`whatif-stat-delta${verdict.purchase_cost_saving > 0 ? ' is-good' : ''}`}>
            {verdict.purchase_cost_saving > 0 ? `${money(verdict.purchase_cost_saving)} less to buy` : `${money(-verdict.purchase_cost_saving)} more to buy`}
          </span>
        </div>
        <div className="whatif-stat">
          <span className="whatif-stat-label">Profit for the week</span>
          <strong className="whatif-stat-value">{money(recommended.profit.p50)}</strong>
          <span className={`whatif-stat-delta${verdict.profit_gain > 0 ? ' is-good' : ' is-bad'}`}>
            {verdict.profit_gain > 0 ? '+' : ''}{money(verdict.profit_gain)} vs your usual rule
          </span>
        </div>
      </div>

      {assistant?.configured ? (
        <AiOverview kind="whatif" restaurantId={restaurantId} simulateResult={result} model={assistant.model} />
      ) : assistant && (
        <p className="hint ai-off">The AI assistant (Snowflake Cortex) is not set up on this server yet.</p>
      )}

      {splitCount > 0 && <p className="whatif-decision">
        {splitCount} ingredient{splitCount === 1 ? '' : 's'} keep{splitCount === 1 ? 's' : ''} for less than a week, so a single weekly delivery is certain to spoil before it can be cooked.
        Splitting {splitCount === 1 ? 'it' : 'those'} into smaller drops buys the same weekly volume with less waste and fewer shortages.
      </p>}

      <div className="whatif-result-grid">
        <section className="whatif-result-panel"><h3>Where the waste is</h3>
          <p className="hint">Only stock that expires inside the week counts as waste. Anything still good is listed as usable.</p>
          {highestWaste.length
            ? <ul>{highestWaste.map((row) => <li key={row.ingredient_id}><strong>{row.name}:</strong> {qty(row.waste.p50)} {row.unit} · {money(row.waste_cost)}</li>)}</ul>
            : <p>Nothing is expected to expire on this plan.</p>}
        </section>
        <section className="whatif-result-panel"><h3>What might run short</h3>
          <p className="hint">Chance an ingredient runs out at some point in the week.</p>
          {stockRisks.length
            ? <ul>{stockRisks.map((row) => <li key={row.ingredient_id}><strong>{row.name}:</strong> {pct(row.stockout_probability)} chance of running short</li>)}</ul>
            : <p>No ingredient is expected to run short.</p>}
          <p><strong>Lost-sales cost:</strong> {money(recommended.lost_sales_cost.p50)}</p>
        </section>
      </div>

      <h3>Effect of the scenario itself</h3>
      <p className="hint">Holding ordering unchanged, this is what the deal and demand settings alone do.</p>
      <p className="whatif-decision">The scenario changes profit by <strong>{money(delta.profit_delta)}</strong>, expired-food cost by <strong>{money(delta.waste_cost_delta)}</strong>, and lost-sales cost by <strong>{money(delta.lost_sales_cost_delta)}</strong>.</p>
      <div className="whatif-table-wrap"><table className="whatif-table"><thead><tr><th>Measure</th><th>Baseline</th><th>What-if</th><th>Change</th></tr></thead><tbody>
        {financeRows.map(([label, baseline, scenario]) => <tr key={label}><td>{label}</td><td>{money(baseline)}</td><td>{money(scenario)}</td><td>{money(scenario - baseline)}</td></tr>)}
      </tbody></table></div>
      </>}
    </section>}
  </>
}
