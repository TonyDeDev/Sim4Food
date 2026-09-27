// A 3x5 bitmap font for the retro simulation scene. Drawing glyphs as blocks
// keeps every letter on the pixel grid, which a real font at 5px would not: the
// browser would antialias it back into mush the moment the canvas is upscaled.
// Each glyph is 5 rows of 3 bits, row major.
const GLYPHS = {
  A: '010101111101101',
  B: '110101110101110',
  C: '011100100100011',
  D: '110101101101110',
  E: '111100110100111',
  F: '111100110100100',
  G: '011100101101011',
  H: '101101111101101',
  I: '111010010010111',
  J: '001001001101010',
  K: '101101110101101',
  L: '100100100100111',
  M: '101111111101101',
  N: '110101101101101',
  O: '010101101101010',
  P: '110101110100100',
  Q: '010101101111011',
  R: '110101110101101',
  S: '011100010001110',
  T: '111010010010010',
  U: '101101101101111',
  V: '101101101101010',
  W: '101101111111101',
  X: '101101010101101',
  Y: '101101010010010',
  Z: '111001010100111',
  0: '111101101101111',
  1: '010110010010111',
  2: '111001111100111',
  3: '111001111001111',
  4: '101101111001001',
  5: '111100111001111',
  6: '111100111101111',
  7: '111001001001001',
  8: '111101111101111',
  9: '111101111001111',
  ' ': '000000000000000',
  '.': '000000000000010',
  ',': '000000000010100',
  '-': '000000111000000',
  '!': '010010010000010',
  "'": '010010000000000',
  ':': '000010000010000',
  '?': '111001011000010',
  '/': '001001010100100',
  '%': '101001010100101',
  '+': '000010111010000',
  '(': '001010010010001',
  ')': '100010010010100',
}

const GLYPH_W = 3
const GLYPH_H = 5
const TRACKING = 1
export const CHAR_ADVANCE = GLYPH_W + TRACKING

/**
 * Folds a label into something the font can actually draw: accents stripped the
 * same way the rest of the app does it, then uppercased, with anything still
 * unknown dropped rather than drawn as a blank hole.
 */
export function toFontSafe(text, maxChars = Infinity) {
  const folded = String(text ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toUpperCase()
    .split('')
    .filter((char) => char in GLYPHS)
    .join('')
    .replace(/\s+/g, ' ')
    .trim()
  return folded.length > maxChars ? `${folded.slice(0, Math.max(maxChars - 1, 0))}.` : folded
}

export function textWidth(text, scale = 1) {
  if (!text.length) return 0
  return (text.length * CHAR_ADVANCE - TRACKING) * scale
}

/**
 * Paints `text` with its top-left at (x, y). `align` shifts it relative to x,
 * and `outline` draws a one-pixel border first so a label stays readable over
 * both the pale sky and the dark roof.
 */
export function drawText(ctx, text, x, y, { color, scale: rawScale = 1, align = 'left', outline = null } = {}) {
  const scale = Math.max(1, Math.round(rawScale))
  const safe = typeof text === 'string' ? text : toFontSafe(text)
  if (!safe.length) return
  const width = textWidth(safe, scale)
  // Snap to whole pixels. A half-pixel origin would let the canvas antialias
  // every glyph edge, which is the one thing that stops this reading as pixel
  // art, so the font enforces the grid rather than trusting each caller.
  const top = Math.round(y)
  let left = Math.round(x)
  if (align === 'center') left = Math.round(x - width / 2)
  else if (align === 'right') left = Math.round(x - width)

  if (outline) {
    for (const [dx, dy] of [[-scale, 0], [scale, 0], [0, -scale], [0, scale]]) {
      paint(ctx, safe, left + dx, top + dy, outline, scale)
    }
  }
  paint(ctx, safe, left, top, color, scale)
}

function paint(ctx, text, left, top, color, scale) {
  ctx.fillStyle = color
  for (let index = 0; index < text.length; index += 1) {
    const bits = GLYPHS[text[index]]
    if (!bits || bits === GLYPHS[' ']) continue
    const originX = left + index * CHAR_ADVANCE * scale
    for (let row = 0; row < GLYPH_H; row += 1) {
      for (let column = 0; column < GLYPH_W; column += 1) {
        if (bits[row * GLYPH_W + column] !== '1') continue
        ctx.fillRect(originX + column * scale, top + row * scale, scale, scale)
      }
    }
  }
}
