import { initials, swatchPalette } from '../utils/helpers.js'
import BusinessTypeIcon from './BusinessTypeIcon.jsx'

export default function Sidebar({ user, businesses, onAddBusiness, collapsed, onToggle, onSelectBusiness, onEditBusiness, activeId, onSignOut }) {
  return (
    <aside className={`sidebar${collapsed ? ' collapsed' : ''}`}>
      <div className="sidebar-top">
        <button className="hamburger-btn" aria-label="Toggle sidebar" onClick={onToggle}>
          <svg viewBox="0 0 24 24" fill="none" stroke="#26352D" strokeWidth="1.8" strokeLinecap="round">
            <path d="M3 6h18M3 12h18M3 18h18" />
          </svg>
        </button>
      </div>

      {!collapsed && (
        <>
          <div className="user-block">
            <div className="user-info">
              <div className="user-avatar">{initials(user.firstName, user.lastName)}</div>
              <div>
                <p className="user-name">
                  {user.firstName} {user.lastName}
                </p>
                <p className="user-email">{user.email}</p>
              </div>
            </div>
          </div>

          <p className="sidebar-label">Your businesses</p>
          <ul className="biz-list">
            {businesses.map((biz, i) => {
              const color = swatchPalette[i % swatchPalette.length]
              return (
                <li key={biz.id} className={`biz-item${biz.id === activeId ? ' active' : ''}`}>
                  <button className="biz-item-main" onClick={() => onSelectBusiness(biz.id)} aria-label={`Show ${biz.name}`}>
                    <div className="biz-swatch" style={{ width: 32, height: 32, fontSize: 12, background: color + '22', color: '#245C45', borderColor: 'rgba(36, 92, 69, .2)' }}>
                      <BusinessTypeIcon type={biz.type} />
                    </div>
                    <span className="biz-name">{biz.name}</span>
                  </button>
                  <button className="biz-edit-btn" type="button" aria-label={`Edit ${biz.name} settings`} title={`Edit ${biz.name}`} onClick={() => onEditBusiness(biz)}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m15 5 4 4M4 20l4.2-.9L19 8.3a2.1 2.1 0 0 0-3-3L5.2 16.1 4 20Z" /></svg>
                  </button>
                </li>
              )
            })}
          </ul>

          {businesses.length > 0 && (
            <button className="sidebar-add-business" onClick={onAddBusiness}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M12 5v14M5 12h14" />
              </svg>
              <span>Add business</span>
            </button>
          )}

          <div className="sidebar-bottom">
            <a
              href="#"
              className="signout-link"
              onClick={(e) => {
                e.preventDefault()
                onSignOut()
              }}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
                <path d="M16 17l5-5-5-5" />
                <path d="M21 12H9" />
              </svg>
              <span>Sign out</span>
            </a>
          </div>
        </>
      )}
    </aside>
  )
}
