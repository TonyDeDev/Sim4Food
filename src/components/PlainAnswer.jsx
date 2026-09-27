// Renders model text without interpreting any HTML: blank lines split paragraphs,
// lines starting with "- " become a list, and leftover **bold** becomes <strong>
// instead of showing asterisks.
function Inline({ text }) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : part.replace(/^#+\s*/, '')
  )
}

const BULLET = /^[-*•]\s+/

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

export default function PlainAnswer({ text }) {
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
