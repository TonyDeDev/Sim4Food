import { useState } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import BusinessCard from '../components/BusinessCard.jsx'
import AddBusinessModal from '../components/AddBusinessModal.jsx'

export default function Dashboard({ user, businesses, onAddBusiness, onUpdateBusiness, onSignOut }) {
  const [collapsed, setCollapsed] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [activeId, setActiveId] = useState(null)
  const [editingBusiness, setEditingBusiness] = useState(null)

  function handleSelectBusiness(id) {
    setActiveId(id)
    const card = document.getElementById(`card-${id}`)
    card?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    setTimeout(() => setActiveId((current) => (current === id ? null : current)), 1400)
  }

  function handleSubmit(newBusiness) {
    if (editingBusiness) {
      onUpdateBusiness(editingBusiness.id, newBusiness)
    } else {
      onAddBusiness({ id: `biz-${Date.now()}`, ...newBusiness })
    }
    setEditingBusiness(null)
    setModalOpen(false)
  }

  function handleEditBusiness(business) {
    setEditingBusiness(business)
    setModalOpen(true)
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
        onAddBusiness={() => setModalOpen(true)}
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
            <h1>Your businesses</h1>
            <p>{businesses.length === 0 ? 'Add a business to start estimating its food waste.' : 'Manage your businesses and their food waste estimates.'}</p>
          </div>
        </div>

        {businesses.length === 0 ? (
          <div className="empty-state">
            <p className="title">No businesses yet</p>
            <p className="desc">
              Add your first business and upload its inventory, recipes, and sales history to get a waste estimate.
            </p>
            <button className="btn-pastel" onClick={() => setModalOpen(true)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M12 5v14M5 12h14" />
              </svg>
              Add a business
            </button>
          </div>
        ) : (
          <>
            <div className="biz-grid">
              {businesses.map((biz, i) => (
                <BusinessCard key={biz.id} biz={biz} index={i} highlighted={biz.id === activeId} onEdit={() => handleEditBusiness(biz)} />
              ))}
            </div>
            <section className="business-summary" aria-label="Business summary">
              <p className="summary-count">{businesses.length}</p>
              <div>
                <h2>{businesses.length === 1 ? 'Business added' : 'Businesses added'}</h2>
                <p>Your businesses are ready for inventory, recipe, and sales data.</p>
              </div>
            </section>
          </>
        )}
      </main>

      <AddBusinessModal open={modalOpen} onClose={handleCloseModal} onSubmit={handleSubmit} business={editingBusiness} />
    </div>
  )
}
