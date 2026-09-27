// `delta` is {text, good} - good=true renders green, false renders red,
// null/undefined renders neutral. Callers decide what "good" means, since
// revenue up is good but waste up is not.
export default function StatCard({ label, value, sub, delta, tone, children }) {
  return (
    <div className={`stat-card${tone ? ` stat-card-${tone}` : ''}`}>
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
      {delta && (
        <p className={`stat-delta${delta.good === true ? ' up' : delta.good === false ? ' down' : ''}`}>{delta.text}</p>
      )}
      {sub && <p className="stat-sub">{sub}</p>}
      {children}
    </div>
  )
}
