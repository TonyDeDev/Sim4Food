export default function Sparkline({ values, width = 90, height = 28, label = 'Usage trend over recent weeks', fallback }) {
  const nums = values.filter((v) => v !== null && v !== undefined)
  if (nums.length < 2) return fallback ?? <span className="pending-note">Not enough history</span>

  const pad = 3
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  const range = max - min || 1
  const points = nums.map((v, i) => {
    const x = pad + (i / (nums.length - 1)) * (width - pad * 2)
    const y = height - pad - ((v - min) / range) * (height - pad * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} className="sparkline" role="img" aria-label={label}>
      <polyline points={points} fill="none" stroke="var(--deep-green)" strokeWidth="1.5" />
    </svg>
  )
}
