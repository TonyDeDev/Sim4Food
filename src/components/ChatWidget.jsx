import { useEffect, useRef, useState } from 'react'
import { fetchInsightsStatus, streamChat } from '../utils/api.js'
import PlainAnswer from './PlainAnswer.jsx'

const NO_MESSAGES = []
const PAGE_LABELS = { home: 'Home', records: 'Records', forecast: 'Forecast', whatif: 'What If' }

const SUGGESTIONS = {
  home: ["What's running low?", 'Why did waste change last week?', 'How is revenue trending?'],
  records: ['Show me the sales file layout for Excel', 'Did any upload fail, and why?', 'Which order should I upload files in?'],
  forecast: ['What should I order first on Monday?', 'Which ingredient am I most likely to run out of?', 'How sure are you about these numbers?'],
  whatif: ['How do I plan a deal?', 'What events are coming up?'],
}

function ChatIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />
    </svg>
  )
}

// The assistant in the corner of every dashboard tab. It answers from the data of
// the tab the owner is on; the server builds that context, the browser only names the tab.
export default function ChatWidget({ restaurantId, page, businessName }) {
  const [status, setStatus] = useState(null)
  const [open, setOpen] = useState(false)
  const [threads, setThreads] = useState({})
  const [draft, setDraft] = useState('')
  const [busyKey, setBusyKey] = useState(null)
  const [errors, setErrors] = useState({})
  const controllerRef = useRef(null)
  const logRef = useRef(null)
  const inputRef = useRef(null)

  const key = `${restaurantId}:${page}`
  const messages = threads[key] ?? NO_MESSAGES
  const busy = busyKey !== null
  const error = errors[key] || ''

  useEffect(() => {
    let cancelled = false
    fetchInsightsStatus()
      .then((data) => { if (!cancelled) setStatus(data) })
      .catch(() => { if (!cancelled) setStatus({ configured: false }) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => () => controllerRef.current?.abort(), [])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open, key])

  useEffect(() => {
    const log = logRef.current
    if (log) log.scrollTop = log.scrollHeight
  }, [messages, open])

  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  if (!status?.configured || !restaurantId) return null

  function setThread(threadKey, update) {
    setThreads((prev) => ({ ...prev, [threadKey]: update(prev[threadKey] || []) }))
  }

  async function ask(text) {
    const question = text.trim()
    if (!question || busy) return
    const threadKey = key
    const history = [...messages, { role: 'user', content: question }]
    setThread(threadKey, () => [...history, { role: 'assistant', content: '' }])
    setErrors((prev) => ({ ...prev, [threadKey]: '' }))
    setDraft('')
    setBusyKey(threadKey)
    const controller = new AbortController()
    controllerRef.current = controller
    try {
      await streamChat(restaurantId, page, history, (chunk) => {
        setThread(threadKey, (prev) => {
          const next = [...prev]
          const lastMessage = next[next.length - 1]
          next[next.length - 1] = { ...lastMessage, content: lastMessage.content + chunk }
          return next
        })
      }, controller.signal)
    } catch (err) {
      if (err.name === 'AbortError') return
      setErrors((prev) => ({ ...prev, [threadKey]: err.message }))
      setThread(threadKey, () => history.slice(0, -1))
      setDraft(question)
    } finally {
      setBusyKey(null)
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    ask(draft)
  }

  return (
    <>
      {open && (
        <section className="chat-widget" role="dialog" aria-label="Ask Sim4Food">
          <header className="chat-widget-head">
            <div>
              <h2>Ask Sim4Food</h2>
              <p>Looking at {PAGE_LABELS[page] ?? page}{businessName ? ` for ${businessName}` : ''}</p>
            </div>
            <div className="chat-widget-actions">
              {messages.length > 0 && (
                <button type="button" className="btn-link" onClick={() => setThread(key, () => [])} disabled={busy}>
                  Clear
                </button>
              )}
              <button type="button" className="chat-close" onClick={() => setOpen(false)} aria-label="Close assistant">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
              </button>
            </div>
          </header>

          <div className="chat-log" ref={logRef} aria-live="polite">
            {messages.length === 0 ? (
              <div className="chat-empty">
                <p className="hint">Ask about what&apos;s on this tab. Answers use only your data here.</p>
                <div className="chat-suggestions">
                  {(SUGGESTIONS[page] || []).map((s) => (
                    <button key={s} type="button" className="chat-suggestion" onClick={() => ask(s)} disabled={busy}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m, i) => (
                <div key={i} className={`chat-bubble ${m.role}`}>
                  {m.content
                    ? (m.role === 'assistant' ? <PlainAnswer text={m.content} /> : m.content)
                    : (busyKey === key && i === messages.length - 1 ? <span className="typing" aria-label="Thinking" /> : null)}
                </div>
              ))
            )}
          </div>

          {error && <p className="field-error chat-error" role="alert">{error}</p>}

          <form className="chat-form" onSubmit={handleSubmit}>
            <input
              ref={inputRef}
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={`Ask about ${(PAGE_LABELS[page] ?? page).toLowerCase()}...`}
              maxLength={2000}
              aria-label="Your question"
              disabled={busy}
            />
            <button type="submit" className="btn-pastel" disabled={busy || !draft.trim()}>
              {busy ? '…' : 'Ask'}
            </button>
          </form>
          <p className="chat-widget-foot">Powered by Snowflake Cortex. It can explain your data but can&apos;t change anything.</p>
        </section>
      )}

      <button
        type="button"
        className={`chat-launcher${open ? ' open' : ''}`}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={open ? 'Close assistant' : 'Ask Sim4Food'}
      >
        <ChatIcon />
        <span>{open ? 'Close' : 'Ask'}</span>
      </button>
    </>
  )
}
