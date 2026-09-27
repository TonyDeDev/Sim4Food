import { useEffect, useState } from 'react'
import Sidebar from '../components/Sidebar.jsx'
import AddBusinessModal from '../components/AddBusinessModal.jsx'
import BusinessDetailsPanel from '../components/BusinessDetailsPanel.jsx'
import RecordUploadCard from '../components/RecordUploadCard.jsx'
import InventoryOverview from '../components/InventoryOverview.jsx'
import ForecastOverview from '../components/ForecastOverview.jsx'
import WhatIfSimulation from '../components/WhatIfSimulation.jsx'
import { createRestaurant, fetchUploadStatus, RECORD_FIELDS } from '../utils/api.js'

const TABS = [
  { key: 'home', label: 'Home' },
  { key: 'records', label: 'Records' },
  { key: 'forecast', label: 'Forecast' },
  { key: 'whatif', label: 'What If' },
]

export default function Dashboard({ user, businesses, onAddBusiness, onUpdateBusiness, onUploadRecord, onSignOut }) {
  const [collapsed, setCollapsed] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [activeId, setActiveId] = useState(businesses[0]?.id ?? null)
  const [detailsBusiness, setDetailsBusiness] = useState(null)
  const [activeTab, setActiveTab] = useState('home')
  const selectedBusiness = businesses.find((business) => business.id === activeId) || businesses[0] || null
  const selectedBusinessId = selectedBusiness?.id

  // The upload cards' "which file is this" display is client-only state
  // (files: {}), reset to empty on every fresh login. Re-hydrate it here
  // from upload_batches (the real source of truth) whenever the selected
  // business changes, so a page reload or a fresh login shows what's
  // actually been uploaded instead of "No file uploaded" for everything.
  useEffect(() => {
    if (!selectedBusinessId) return
    let cancelled = false
    fetchUploadStatus(selectedBusinessId)
      .then((statusMap) => {
        if (cancelled) return
        onUpdateBusiness(selectedBusinessId, { files: statusMap })
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [selectedBusinessId, onUpdateBusiness])

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
            <p>{selectedBusiness ? "Here's what's in stock, plus your records and forecast." : 'Add a business to start estimating its food waste.'}</p>
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

            {activeTab === 'home' && <InventoryOverview restaurantId={selectedBusiness.id} />}

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

            {activeTab === 'forecast' && <ForecastOverview restaurantId={selectedBusiness.id} />}

            {activeTab === 'whatif' && <WhatIfSimulation restaurantId={selectedBusiness.id} />}
          </>
        )}
      </main>

      <AddBusinessModal open={modalOpen} onClose={() => setModalOpen(false)} onSubmit={handleSubmit} />
      {detailsBusiness && <BusinessDetailsPanel business={detailsBusiness} onClose={() => setDetailsBusiness(null)} onSave={onUpdateBusiness} />}
    </div>
  )
}
