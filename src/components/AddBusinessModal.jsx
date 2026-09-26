import { useEffect, useRef, useState } from 'react'

const FIELDS = [
  { key: 'inventory', label: 'Inventory', hint: 'Current stock on hand, as a spreadsheet or document.' },
  { key: 'recipe', label: 'Recipes', hint: 'Dish names, ingredients, and quantities used.' },
  { key: 'sales', label: 'POS / sales history', hint: 'Export sales records from your point-of-sale system.' },
]

function EditIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m15 5 4 4M4 20l4.2-.9L19 8.3a2.1 2.1 0 0 0-3-3L5.2 16.1 4 20Z" /></svg>
}

export default function AddBusinessModal({ open, onClose, onSubmit, business = null, mode = 'add' }) {
  const [name, setName] = useState('')
  const [type, setType] = useState('')
  const [location, setLocation] = useState('')
  const [files, setFiles] = useState({ inventory: null, recipe: null, sales: null })
  const [suggestions, setSuggestions] = useState([])
  const [suggestionsOpen, setSuggestionsOpen] = useState(false)
  const [loadingLocations, setLoadingLocations] = useState(false)
  const [locationError, setLocationError] = useState('')
  const fileInputRefs = useRef({})
  const locationTimer = useRef(null)
  const requestRef = useRef(null)
  const locationRef = useRef(null)

  useEffect(() => {
    if (!open) return
    setName(business?.name || '')
    setType(business?.type || '')
    setLocation(business?.location || '')
    setFiles({ inventory: null, recipe: null, sales: null })
    setSuggestions([])
    setSuggestionsOpen(false)
  }, [open, business, mode])

  useEffect(() => () => {
    clearTimeout(locationTimer.current)
    requestRef.current?.abort()
  }, [])

  if (!open) return null

  const ready = mode === 'records'
    ? Boolean(files.inventory || files.recipe || files.sales)
    : Boolean(name.trim() && type.trim() && location.trim() && (business || (files.inventory && files.recipe && files.sales)))

  function reset() {
    clearTimeout(locationTimer.current)
    requestRef.current?.abort()
    setName('')
    setType('')
    setLocation('')
    setFiles({ inventory: null, recipe: null, sales: null })
    setSuggestions([])
    setSuggestionsOpen(false)
    setLocationError('')
  }

  function handleClose() {
    reset()
    onClose()
  }

  function handleFileChange(key, fileList) {
    const file = fileList[0]
    setFiles((prev) => ({ ...prev, [key]: file || null }))
  }

  function handleLocationChange(value) {
    setLocation(value)
    setSuggestions([])
    setLocationError('')
    requestRef.current?.abort()
    clearTimeout(locationTimer.current)
    if (value.trim().length < 3) {
      setSuggestionsOpen(false)
      setLoadingLocations(false)
      return
    }

    setSuggestionsOpen(true)
    setLoadingLocations(true)
    locationTimer.current = setTimeout(async () => {
      const controller = new AbortController()
      requestRef.current = controller
      try {
        const params = new URLSearchParams({ q: value.trim(), limit: '5', lang: 'en' })
        const response = await fetch(`https://photon.komoot.io/api/?${params}`, { signal: controller.signal })
        if (!response.ok) throw new Error('Address suggestions are unavailable right now.')
        const data = await response.json()
        const results = (data.features || []).map((feature) => {
          const props = feature.properties || {}
          return [props.name, props.housenumber && props.street ? `${props.housenumber} ${props.street}` : props.street, props.city || props.locality || props.district, props.state, props.postcode, props.country]
            .filter(Boolean)
            .filter((part, index, all) => all.indexOf(part) === index)
            .join(', ')
        }).filter(Boolean)
        setSuggestions([...new Set(results)])
        setLocationError(results.length ? '' : 'No matching addresses found. You can keep the address you typed.')
      } catch (error) {
        if (error.name !== 'AbortError') setLocationError('Address suggestions are unavailable. You can still enter the address manually.')
      } finally {
        if (!controller.signal.aborted) setLoadingLocations(false)
      }
    }, 500)
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (!ready) return
    if (mode === 'records') {
      onSubmit({
        inventoryFile: files.inventory?.name || business?.inventoryFile,
        recipeFile: files.recipe?.name || business?.recipeFile,
        salesFile: files.sales?.name || business?.salesFile,
      })
      reset()
      return
    }
    onSubmit({
      name: name.trim(),
      type: type.trim(),
      location: location.trim(),
      inventoryFile: files.inventory?.name || business?.inventoryFile,
      recipeFile: files.recipe?.name || business?.recipeFile,
      salesFile: files.sales?.name || business?.salesFile,
    })
    reset()
  }

  return (
    <div className="modal-overlay active" onClick={(e) => { if (e.target === e.currentTarget) handleClose() }}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="business-modal-title">
        <h2 id="business-modal-title">{mode === 'records' ? 'Update business records' : 'Add a business'}</h2>
        <p className="modal-sub">{mode === 'records' ? `Replace the inventory, recipes, or POS file for ${business?.name}. Choose at least one file to save.` : 'Add your business details, then attach its records.'}</p>

        <form onSubmit={handleSubmit}>
          {mode === 'add' && <>
            <div className="field">
              <label htmlFor="biz-name-input">Business name</label>
              <input id="biz-name-input" type="text" placeholder="e.g. Millbrook Cafe" required value={name} onChange={(e) => setName(e.target.value)} autoFocus />
            </div>

            <div className="field">
              <label htmlFor="biz-type-input">Business type</label>
              <input id="biz-type-input" type="text" placeholder="e.g. Restaurant, cafe, bakery" required value={type} onChange={(e) => setType(e.target.value)} />
            </div>

            <div className="field location-field" ref={locationRef}>
            <label htmlFor="biz-location-input">Business location</label>
            <input
              id="biz-location-input"
              type="text"
              placeholder="Start typing a street address"
              required
              value={location}
              autoComplete="off"
              role="combobox"
              aria-autocomplete="list"
              aria-expanded={suggestionsOpen && suggestions.length > 0}
              aria-controls="biz-location-suggestions"
              onFocus={() => suggestions.length && setSuggestionsOpen(true)}
              onChange={(e) => handleLocationChange(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Escape') setSuggestionsOpen(false) }}
            />
            {suggestionsOpen && (loadingLocations || suggestions.length > 0 || locationError) && (
              <div className="location-suggestions-wrap">
                <ul className="location-suggestions" id="biz-location-suggestions" role="listbox">
                  {loadingLocations && <li className="location-message">Finding matching addresses…</li>}
                  {suggestions.map((address) => (
                    <li key={address} role="option" aria-selected={address === location}>
                      <button type="button" onClick={() => { setLocation(address); setSuggestionsOpen(false); setLocationError('') }}>{address}</button>
                    </li>
                  ))}
                  {!loadingLocations && locationError && <li className="location-message">{locationError}</li>}
                </ul>
                <small>Suggestions by Photon · © OpenStreetMap contributors</small>
              </div>
            )}
            </div>
          </>}

          {FIELDS.map(({ key, label, hint }) => (
            <div className="upload-field" key={key}>
              <label htmlFor={`biz-file-${key}`}>{label}</label>
              <p className="hint">{hint}</p>
              <div className="upload-box">
                <span className={`file-name${files[key] ? ' chosen' : ''}`}>
                  {files[key] ? files[key].name : business?.[`${key}File`] || 'No file selected'}
                </span>
              <button type="button" className="btn-choose" onClick={() => fileInputRefs.current[key]?.click()}>
                  {files[key] || business?.[`${key}File`] ? 'Replace file' : 'Choose file'}
                </button>
              </div>
              <input id={`biz-file-${key}`} type="file" style={{ display: 'none' }} ref={(el) => (fileInputRefs.current[key] = el)} onChange={(e) => handleFileChange(key, e.target.files)} />
            </div>
          ))}

          <div className="modal-actions">
            <button type="button" className="btn-outline-modal" onClick={handleClose}>Cancel</button>
            <button type="submit" className="btn-submit-modal" disabled={!ready}>{mode === 'records' ? 'Save records' : 'Add business'}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
