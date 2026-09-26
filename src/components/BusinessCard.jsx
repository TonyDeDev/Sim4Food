import { swatchPalette } from '../utils/helpers.js'
import BusinessTypeIcon from './BusinessTypeIcon.jsx'

function FileTag({ label }) {
  return (
    <span className="tag">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
        <path d="M5 13l4 4L19 7" />
      </svg>
      {label}
    </span>
  )
}

export default function BusinessCard({ biz, index, highlighted, onEdit }) {
  const color = swatchPalette[index % swatchPalette.length]

  return (
    <div id={`card-${biz.id}`} className={`biz-card${highlighted ? ' highlight' : ''}`}>
      <div className="biz-card-top">
        <div className="biz-swatch" style={{ background: color + '22', color: '#245C45', borderColor: 'rgba(36, 92, 69, .2)' }}>
          <BusinessTypeIcon type={biz.type} />
        </div>
        <div className="biz-card-title">
          <h3>{biz.name}</h3>
          <p className="meta">{biz.type || 'Business'}{biz.location ? ` · ${biz.location}` : ''}</p>
        </div>
        <button className="biz-edit-btn biz-card-edit" type="button" aria-label={`Edit ${biz.name} settings`} title={`Edit ${biz.name}`} onClick={onEdit}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m15 5 4 4M4 20l4.2-.9L19 8.3a2.1 2.1 0 0 0-3-3L5.2 16.1 4 20Z" /></svg>
        </button>
      </div>
      <div className="biz-tags">
        <FileTag label="Inventory" />
        <FileTag label="Recipes" />
        <FileTag label="Sales" />
      </div>
    </div>
  )
}
