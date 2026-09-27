import { useState } from 'react'

export default function WhatIfSimulation() {
  const [dealPct, setDealPct] = useState(0)
  const [holiday, setHoliday] = useState(false)
  const [showComingSoon, setShowComingSoon] = useState(false)

  function handleRun(e) {
    e.preventDefault()
    setShowComingSoon(true)
  }

  return (
    <>
      <p className="hint">
        Simulate customer demand for the week ahead against your current stock on hand, with a deal or
        holiday layered in - useful for checking whether a promotion is likely to run you out of an
        ingredient before you run it.
      </p>

      <form className="whatif-controls" onSubmit={handleRun}>
        <div className="whatif-slider">
          <label htmlFor="whatif-deal">Deal discount</label>
          <input
            id="whatif-deal"
            type="range"
            min="0"
            max="50"
            step="5"
            value={dealPct}
            onChange={(e) => setDealPct(Number(e.target.value))}
          />
          <p className="hint">{dealPct === 0 ? 'No deal' : `${dealPct}% off`}</p>
        </div>

        <div className="remember-row">
          <input
            type="checkbox"
            id="whatif-holiday"
            checked={holiday}
            onChange={(e) => setHoliday(e.target.checked)}
          />
          <label htmlFor="whatif-holiday">Treat the coming week as a holiday</label>
        </div>

        <button type="submit" className="btn-pastel">Run simulation</button>
      </form>

      {showComingSoon && (
        <section className="alert-card" aria-label="Simulation status">
          <div className="alert-card-head">
            <h2>Coming soon</h2>
          </div>
          <p className="alert-subtitle">
            The agent-based simulation isn&apos;t wired up yet. Once it&apos;s ready, this will simulate a
            week of customers under this scenario against your current stock on hand and flag
            anything likely to run out.
          </p>
        </section>
      )}
    </>
  )
}
