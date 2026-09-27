import { useEffect, useRef, useState } from 'react'

export default function AddBusinessModal({ open, onClose, onSubmit }) {
  const [name, setName] = useState('')
  const [type, setType] = useState('')
  const [location, setLocation] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [suggestionsOpen, setSuggestionsOpen] = useState(false)
  const [loadingLocations, setLoadingLocations] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const locationTimer = useRef(null)
  const requestRef = useRef(null)
  const locationRef = useRef(null)

  useEffect(() => {
    if (!open) return
    setName('')
    setType('')
    setLocation('')
    setSuggestions([])
    setSuggestionsOpen(false)
    setSubmitError('')
  }, [open])

  useEffect(() => () => {
    clearTimeout(locationTimer.current)
    requestRef.current?.abort()
  }, [])

  if (!open) return null

  const ready = !submitting && Boolean(name.trim() && type.trim() && location.trim())

  function reset() {
    clearTimeout(locationTimer.current)
    requestRef.current?.abort()
    setName('')
    setType('')
    setLocation('')
    setSuggestions([])
    setSuggestionsOpen(false)
    setLocationError('')
  }

  function handleClose() {
    reset()
    onClose()
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

  async function handleSubmit(e) {
    e.preventDefault()
    if (!ready) return
    setSubmitError('')
    setSubmitting(true)
    try {
      await onSubmit({ name: name.trim(), type: type.trim(), location: location.trim() })
      reset()
    } catch (error) {
      setSubmitError(error.message || 'Could not add business. Please try again.')
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay active" onClick={(e) => { if (e.target === e.currentTarget) handleClose() }}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="business-modal-title">
        <h2 id="business-modal-title">Add a business</h2>
        <p className="modal-sub">Add your business details. You can upload its records afterward.</p>

        <form onSubmit={handleSubmit}>
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

          {submitError && <p className="field-error" role="alert">{submitError}</p>}

          <div className="modal-actions">
            <button type="button" className="btn-outline-modal" onClick={handleClose} disabled={submitting}>Cancel</button>
            <button type="submit" className="btn-submit-modal" disabled={!ready}>
              {submitting ? 'Adding…' : 'Add business'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
