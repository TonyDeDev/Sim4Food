import { useState } from 'react'

export default function BusinessDetailsPanel({ business, onClose, onSave }) {
  const [name, setName] = useState(business?.name || '')
  const [type, setType] = useState(business?.type || '')

  // Reset the fields synchronously during render when a different business
  // is opened, rather than inside an effect (see "resetting state when a
  // prop changes": https://react.dev/learn/you-might-not-need-an-effect).
  const [syncedBusiness, setSyncedBusiness] = useState(business)
  if (business !== syncedBusiness) {
    setSyncedBusiness(business)
    setName(business?.name || '')
    setType(business?.type || '')
  }

  if (!business) return null

  function handleSubmit(event) {
    event.preventDefault()
    if (!name.trim() || !type.trim()) return
    onSave(business.id, { name: name.trim(), type: type.trim() })
    onClose()
  }

  return (
    <div className="details-drawer-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <aside className="details-drawer" role="dialog" aria-modal="true" aria-labelledby="details-panel-title">
        <div className="details-drawer-top">
          <div>
            <p className="details-eyebrow">BUSINESS DETAILS</p>
            <h2 id="details-panel-title">A quick refresh</h2>
          </div>
          <button className="details-close" type="button" onClick={onClose} aria-label="Close business details">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
          </button>
        </div>
        <p className="details-intro">Keep the basics up to date. Your location and uploaded records stay as they are.</p>
        <form className="details-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Business name</span>
            <input autoFocus required value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Millbrook Cafe" />
          </label>
          <label className="field">
            <span>Business type</span>
            <input required value={type} onChange={(event) => setType(event.target.value)} placeholder="e.g. Cafe, bakery, restaurant" />
          </label>
          <div className="details-panel-note"><span className="details-note-mark">✳</span><span>Upload inventory, recipes, and POS files from the record cards on the main panel.</span></div>
          <div className="details-actions">
            <button className="btn-outline-modal" type="button" onClick={onClose}>Cancel</button>
            <button className="btn-submit-modal" type="submit" disabled={!name.trim() || !type.trim()}>Save details</button>
          </div>
        </form>
      </aside>
    </div>
  )
}
