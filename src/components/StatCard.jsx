// `delta` is {text, good} - good=true renders green, false renders red,
// null/undefined renders neutral. Callers decide what "good" means, since
// revenue up is good but waste up is not.
export default function StatCard({ label, value, sub, delta, tone, children }) {
  // A short number or one-word status (the common case) reads well at the
  // full display size; free text like an event's name needs to shrink and
  // wrap instead of overflowing the card.
  const isLongText = typeof value === 'string' && value.length > 14
  return (
    <div className={`stat-card${tone ? ` stat-card-${tone}` : ''}`}>
      <p className="stat-label">{label}</p>
      <p className={`stat-value${isLongText ? ' is-long-text' : ''}`}>{value}</p>
      {delta && (
        <p className={`stat-delta${delta.good === true ? ' up' : delta.good === false ? ' down' : ''}`}>{delta.text}</p>
      )}
      {sub && <p className="stat-sub">{sub}</p>}
      {children}
    </div>
  )
}
