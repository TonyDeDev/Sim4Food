import { useState } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import AddBusinessModal from '../components/AddBusinessModal.jsx'
import BusinessDetailsPanel from '../components/BusinessDetailsPanel.jsx'

export default function Dashboard({ user, businesses, onAddBusiness, onUpdateBusiness, onSignOut }) {
  const [collapsed, setCollapsed] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [modalMode, setModalMode] = useState('add')
  const [activeId, setActiveId] = useState(businesses[0]?.id ?? null)
  const [editingBusiness, setEditingBusiness] = useState(null)
  const [detailsBusiness, setDetailsBusiness] = useState(null)
  const selectedBusiness = businesses.find((business) => business.id === activeId) || businesses[0] || null

  function handleSelectBusiness(id) {
    setActiveId(id)
  }

  function handleAddBusinessClick() {
    setEditingBusiness(null)
    setModalMode('add')
    setModalOpen(true)
  }

  function handleEditRecords() {
    setEditingBusiness(selectedBusiness)
    setModalMode('records')
    setModalOpen(true)
  }

  function handleSubmit(newBusiness) {
    if (editingBusiness) {
      onUpdateBusiness(editingBusiness.id, newBusiness)
    } else {
      const addedBusiness = { id: `biz-${Date.now()}`, ...newBusiness }
      onAddBusiness(addedBusiness)
      setActiveId(addedBusiness.id)
    }
    setEditingBusiness(null)
    setModalOpen(false)
  }

  function handleEditBusiness(business) {
    setDetailsBusiness(business)
  }

  function handleCloseModal() {
    setModalOpen(false)
    setEditingBusiness(null)
  }

  return (
    <div className="app-shell">
      <Sidebar
        user={user}
        businesses={businesses}
        onAddBusiness={handleAddBusinessClick}
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
        onSelectBusiness={handleSelectBusiness}
        onEditBusiness={handleEditBusiness}
        activeId={activeId}
        onSignOut={onSignOut}
      />

      <main className="main">
        <div className="main-head">
          <div>
            <h1>{selectedBusiness?.name || 'Your businesses'}</h1>
            <p>{selectedBusiness ? 'Inventory, recipes, and POS records' : 'Add a business to start estimating its food waste.'}</p>
          </div>
          {selectedBusiness && (
            <button className="main-business-edit" type="button" onClick={handleEditRecords} aria-label={`Edit ${selectedBusiness.name} records`} title={`Edit ${selectedBusiness.name} records`}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m15 5 4 4M4 20l4.2-.9L19 8.3a2.1 2.1 0 0 0-3-3L5.2 16.1 4 20Z" /></svg>
              <span>Edit records</span>
            </button>
          )}
        </div>

        {businesses.length === 0 ? (
          <div className="empty-state">
            <p className="title">No businesses yet</p>
            <p className="desc">
              Add your first business and upload its inventory, recipes, and sales history to get a waste estimate.
            </p>
            <button className="btn-pastel" onClick={handleAddBusinessClick}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M12 5v14M5 12h14" />
              </svg>
              Add a business
            </button>
          </div>
        ) : selectedBusiness && (
          <section className="business-record-grid" aria-label={`${selectedBusiness.name} records`}>
            <article className="business-record-card">
              <div className="record-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="m3 7 9-4 9 4-9 4-9-4Z"/><path d="M3 7v10l9 4 9-4V7M12 11v10"/><path d="m7.5 5 9 4"/></svg></div>
              <div><h2>Inventory</h2><p>{selectedBusiness.inventoryFile || 'No inventory file attached'}</p></div>
            </article>
            <article className="business-record-card">
              <div className="record-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M6 3h9l4 4v14H6z"/><path d="M15 3v5h5M9 12h7m-7 4h7"/><path d="M3 6v15h12"/></svg></div>
              <div><h2>Recipes</h2><p>{selectedBusiness.recipeFile || 'No recipe file attached'}</p></div>
            </article>
            <article className="business-record-card">
              <div className="record-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16v16H4zM4 9h16M8 15h3m3 0h2m-8 3h8"/><path d="M8 2v4m8-4v4"/></svg></div>
              <div><h2>POS</h2><p>{selectedBusiness.salesFile || 'No POS / sales file attached'}</p></div>
            </article>
          </section>
        )}
      </main>

      <AddBusinessModal open={modalOpen} onClose={handleCloseModal} onSubmit={handleSubmit} business={editingBusiness} mode={modalMode} />
      {detailsBusiness && <BusinessDetailsPanel business={detailsBusiness} onClose={() => setDetailsBusiness(null)} onSave={onUpdateBusiness} />}
    </div>
  )
}
