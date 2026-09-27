import { useState } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import AddBusinessModal from '../components/AddBusinessModal.jsx'
import BusinessDetailsPanel from '../components/BusinessDetailsPanel.jsx'
import RecordUploadCard from '../components/RecordUploadCard.jsx'
import InventoryOverview from '../components/InventoryOverview.jsx'
import { createRestaurant, RECORD_FIELDS } from '../utils/api.js'

const TABS = [
  { key: 'records', label: 'Records' },
  { key: 'inventory', label: 'Inventory' },
]

export default function Dashboard({ user, businesses, onAddBusiness, onUpdateBusiness, onUploadRecord, onSignOut }) {
  const [collapsed, setCollapsed] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [activeId, setActiveId] = useState(businesses[0]?.id ?? null)
  const [detailsBusiness, setDetailsBusiness] = useState(null)
  const [activeTab, setActiveTab] = useState('records')
  const selectedBusiness = businesses.find((business) => business.id === activeId) || businesses[0] || null

  function handleSelectBusiness(id) {
    setActiveId(id)
  }

  function handleAddBusinessClick() {
    setModalOpen(true)
  }

  // Throws on failure - AddBusinessModal awaits this and keeps itself open
  // to show the error, only calling reset()/closing on success.
  async function handleSubmit(newBusiness) {
    const restaurant = await createRestaurant(newBusiness)
    const addedBusiness = {
      id: restaurant.id, name: restaurant.name, type: newBusiness.type, location: newBusiness.location, files: {},
    }
    onAddBusiness(addedBusiness)
    setActiveId(addedBusiness.id)
    setModalOpen(false)
  }

  function handleRecordUploaded(key, filename) {
    onUploadRecord(selectedBusiness.id, key, filename)
  }

  function handleEditBusiness(business) {
    setDetailsBusiness(business)
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
            <p>{selectedBusiness ? 'Upload records and see how long your stock will last.' : 'Add a business to start estimating its food waste.'}</p>
          </div>
        </div>

        {businesses.length === 0 ? (
          <div className="empty-state">
            <p className="title">No businesses yet</p>
            <p className="desc">
              Add your first business, then upload its records to get a waste estimate.
            </p>
            <button className="btn-pastel" onClick={handleAddBusinessClick}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M12 5v14M5 12h14" />
              </svg>
              Add a business
            </button>
          </div>
        ) : selectedBusiness && (
          <>
            <nav className="record-tabs" aria-label="Business view">
              {TABS.map(({ key, label }) => (
                <button
                  key={key}
                  type="button"
                  className={`record-tab${activeTab === key ? ' active' : ''}`}
                  onClick={() => setActiveTab(key)}
                >
                  {label}
                </button>
              ))}
            </nav>

            {activeTab === 'records' && (
              <section className="business-record-grid" aria-label={`${selectedBusiness.name} records`}>
                {RECORD_FIELDS.map(({ key, label }) => (
                  <RecordUploadCard
                    key={key}
                    fieldKey={key}
                    label={label}
                    restaurantId={selectedBusiness.id}
                    currentFile={selectedBusiness.files?.[key]}
                    onUploaded={handleRecordUploaded}
                  />
                ))}
              </section>
            )}

            {activeTab === 'inventory' && <InventoryOverview restaurantId={selectedBusiness.id} />}
          </>
        )}
      </main>

      <AddBusinessModal open={modalOpen} onClose={() => setModalOpen(false)} onSubmit={handleSubmit} />
      {detailsBusiness && <BusinessDetailsPanel business={detailsBusiness} onClose={() => setDetailsBusiness(null)} onSave={onUpdateBusiness} />}
    </div>
  )
}
