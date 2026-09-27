// Renders model text as plain text, turning any **bold** the model still sends into <strong>
// instead of showing asterisks. No HTML from the model is ever interpreted.
export default function PlainAnswer({ text }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : part.replace(/^#+\s*/gm, '')
  )
}
