import { useEffect, useRef, useState } from 'react'
import { streamForecastChat } from '../utils/api.js'
import PlainAnswer from './PlainAnswer.jsx'

const SUGGESTIONS = [
  'What should I order first on Monday?',
  'Which ingredient am I most likely to run out of?',
  'How sure are you about these numbers?',
  'Why is this different from my usual order?',
]

// Chat about the latest forecast run, answered by Snowflake Cortex and streamed in.
export default function ForecastChat({ restaurantId, runAt }) {
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const controllerRef = useRef(null)
  const logRef = useRef(null)

  // A new forecast run (or another restaurant) starts a new conversation.
  const conversationKey = `${restaurantId}:${runAt}`
  const [syncedFor, setSyncedFor] = useState(conversationKey)
  if (syncedFor !== conversationKey) {
    setSyncedFor(conversationKey)
    setMessages([])
    setError('')
  }

  useEffect(() => () => controllerRef.current?.abort(), [conversationKey])

  useEffect(() => {
    const log = logRef.current
    if (log) log.scrollTop = log.scrollHeight
  }, [messages])

  async function ask(text) {
    const question = text.trim()
    if (!question || busy) return
    const history = [...messages, { role: 'user', content: question }]
    setMessages([...history, { role: 'assistant', content: '' }])
    setDraft('')
    setError('')
    setBusy(true)
    const controller = new AbortController()
    controllerRef.current = controller
    try {
      await streamForecastChat(restaurantId, history, (chunk) => {
        setMessages((prev) => {
          const next = [...prev]
          const last = next[next.length - 1]
          next[next.length - 1] = { ...last, content: last.content + chunk }
          return next
        })
      }, controller.signal)
    } catch (err) {
      if (err.name === 'AbortError') return
      setError(err.message)
      setMessages(history.slice(0, -1))
      setDraft(question)
    } finally {
      setBusy(false)
    }
  }

  function handleSubmit(e) {
    e.preventDefault()
    ask(draft)
  }

  return (
    <section className="ai-card chat-card" aria-label="Ask about this order">
      <div className="ai-card-head">
        <h2>Ask about this order</h2>
        {messages.length > 0 && (
          <button type="button" className="btn-link" onClick={() => setMessages([])} disabled={busy}>
            Clear
          </button>
        )}
      </div>

      <div className="chat-log" ref={logRef} aria-live="polite">
        {messages.length === 0 ? (
          <div className="chat-suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" className="chat-suggestion" onClick={() => ask(s)} disabled={busy}>
                {s}
              </button>
            ))}
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={`chat-bubble ${m.role}`}>
              {m.content ? <PlainAnswer text={m.content} /> : (busy && i === messages.length - 1 ? <span className="typing" aria-label="Thinking" /> : null)}
            </div>
          ))
        )}
      </div>

      {error && <p className="field-error" role="alert">{error}</p>}

      <form className="chat-form" onSubmit={handleSubmit}>
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about quantities, risks, or the deal..."
          maxLength={2000}
          aria-label="Your question"
          disabled={busy}
        />
        <button type="submit" className="btn-pastel" disabled={busy || !draft.trim()}>
          {busy ? 'Thinking…' : 'Ask'}
        </button>
      </form>
    </section>
  )
}
