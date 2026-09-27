import { useState } from 'react'

// Renders model text without interpreting any HTML:
// - a ```csv block becomes a spreadsheet-style table with a "Copy for Excel" button,
// - blank lines split paragraphs, lines starting with "- " become a list,
// - leftover **bold** becomes <strong> instead of showing asterisks.
const BULLET = /^[-*•]\s+/
const FENCE = /```[a-zA-Z]*[ \t]*\n?([\s\S]*?)(?:```|$)/g

function Inline({ text }) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : part.replace(/^#+\s*/, '')
  )
}

function isList(lines) {
  return lines.every((line) => BULLET.test(line))
}

function Block({ lines }) {
  if (isList(lines)) {
    return (
      <ul>
        {lines.map((line, i) => <li key={i}><Inline text={line.replace(BULLET, '')} /></li>)}
      </ul>
    )
  }
  return <p><Inline text={lines.join(' ')} /></p>
}

function Prose({ text }) {
  const blocks = text
    .trim()
    .split(/\n\s*\n/)
    .map((block) => block.split('\n').map((line) => line.trim()).filter(Boolean))
    .filter((lines) => lines.length > 0)
    // Models often put a blank line between bullets: keep consecutive bullets in one list.
    .reduce((merged, lines) => {
      const last = merged[merged.length - 1]
      if (last && isList(last) && isList(lines)) last.push(...lines)
      else merged.push(lines)
      return merged
    }, [])
  return blocks.map((lines, i) => <Block key={i} lines={lines} />)
}

// Minimal CSV line parser: commas, and double-quoted fields that may contain commas.
function parseCsvLine(line) {
  const cells = []
  let cell = ''
  let quoted = false
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i]
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') { cell += '"'; i += 1 }
      else if (ch === '"') quoted = false
      else cell += ch
    } else if (ch === '"') quoted = true
    else if (ch === ',') { cells.push(cell); cell = '' }
    else cell += ch
  }
  cells.push(cell)
  return cells.map((c) => c.trim())
}

function CsvTable({ source }) {
  const [copied, setCopied] = useState(false)
  const rows = source.split('\n').map((line) => line.trim()).filter(Boolean).map(parseCsvLine)
  if (rows.length === 0) return null
  const [header, ...body] = rows

  async function copy() {
    // Tab-separated text pastes into separate Excel / Google Sheets cells.
    try {
      await navigator.clipboard.writeText(rows.map((r) => r.join('\t')).join('\n'))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="csv-block">
      <div className="csv-head">
        <span>Spreadsheet layout</span>
        <button type="button" className="btn-link" onClick={copy}>{copied ? 'Copied' : 'Copy for Excel'}</button>
      </div>
      <div className="csv-scroll">
        <table className="csv-table">
          <thead>
            <tr>
              <th className="csv-index" aria-hidden="true" />
              {header.map((h, i) => <th key={i}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {body.map((row, r) => (
              <tr key={r}>
                <td className="csv-index" aria-hidden="true">{r + 2}</td>
                {header.map((_, c) => <td key={c}>{row[c] ?? ''}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function PlainAnswer({ text }) {
  const parts = []
  let last = 0
  for (const match of text.matchAll(FENCE)) {
    if (match.index > last) parts.push({ kind: 'prose', text: text.slice(last, match.index) })
    parts.push({ kind: 'csv', text: match[1] })
    last = match.index + match[0].length
  }
  if (last < text.length) parts.push({ kind: 'prose', text: text.slice(last) })
  return parts.map((part, i) => (part.kind === 'csv'
    ? <CsvTable key={i} source={part.text} />
    : <Prose key={i} text={part.text} />))
}
