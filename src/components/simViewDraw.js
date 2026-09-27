// Pure drawing layer for the simulation replay: given a canvas context, an
// engine and its spec, it paints one frame and returns nothing. No React and no
// timers, so a mock context can assert every coordinate it would ever draw.
import {
  CHIP_FLIGHT, DOOR, H, ROOM, SHELF, SPOIL_LIFE, STREET_Y, TABLES, W,
  clamp, ease, guestPosition, lerp,
} from './simViewEngine.js'

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const CREAM = '#fff8ea'
const CREAM_DEEP = '#f2e9d3'
const FLOOR = '#fffdf7'
const INK = '#26352d'
const INK_SOFT = 'rgba(38, 53, 45, 0.62)'
const INK_FAINT = 'rgba(38, 53, 45, 0.32)'
const GREEN = '#245c45'
const FRESH = '#8cbf65'
const HAIRLINE = 'rgba(36, 92, 69, 0.22)'
const ERROR = '#b3402a'
const AMBER = '#a8720f'
const FONT = 'Inter, system-ui, -apple-system, sans-serif'

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.roundRect(x, y, w, h, r)
}

function drawRoom(ctx) {
  ctx.fillStyle = CREAM
  ctx.fillRect(0, 0, W, H)

  // Street outside the door
  ctx.fillStyle = CREAM_DEEP
  ctx.fillRect(0, STREET_Y - 30, W, H - STREET_Y + 30)
  ctx.strokeStyle = HAIRLINE
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(0, STREET_Y - 30)
  ctx.lineTo(W, STREET_Y - 30)
  ctx.stroke()

  ctx.fillStyle = FLOOR
  roundRect(ctx, ROOM.x, ROOM.y, ROOM.w, ROOM.h, 14)
  ctx.fill()
  ctx.strokeStyle = HAIRLINE
  ctx.lineWidth = 1.5
  ctx.stroke()

  // The door is a gap in the front wall, painted back over the room's own edge.
  ctx.strokeStyle = FLOOR
  ctx.lineWidth = 4
  ctx.beginPath()
  ctx.moveTo(DOOR.x, ROOM.y + ROOM.h)
  ctx.lineTo(DOOR.x + DOOR.w, ROOM.y + ROOM.h)
  ctx.stroke()
  ctx.strokeStyle = GREEN
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(DOOR.x, ROOM.y + ROOM.h + 7)
  ctx.lineTo(DOOR.x, ROOM.y + ROOM.h)
  ctx.moveTo(DOOR.x + DOOR.w, ROOM.y + ROOM.h + 7)
  ctx.lineTo(DOOR.x + DOOR.w, ROOM.y + ROOM.h)
  ctx.stroke()
  ctx.fillStyle = INK_FAINT
  ctx.font = `500 10px ${FONT}`
  ctx.textAlign = 'center'
  ctx.fillText('DOOR', DOOR.x + DOOR.w / 2, ROOM.y + ROOM.h + 20)

  // Kitchen pass along the back wall
  ctx.fillStyle = 'rgba(36, 92, 69, 0.06)'
  roundRect(ctx, ROOM.x + 12, ROOM.y + 10, ROOM.w - 24, 17, 8)
  ctx.fill()
  ctx.fillStyle = INK_FAINT
  ctx.font = `600 9px ${FONT}`
  ctx.fillText('KITCHEN PASS', ROOM.x + ROOM.w / 2, ROOM.y + 23)

  for (const table of TABLES) {
    ctx.fillStyle = 'rgba(38, 53, 45, 0.07)'
    ctx.beginPath()
    ctx.ellipse(table.x, table.y + 3, 23, 17, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = CREAM_DEEP
    ctx.beginPath()
    ctx.ellipse(table.x, table.y, 22, 16, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.strokeStyle = HAIRLINE
    ctx.lineWidth = 1
    ctx.stroke()
  }
}

function drawGuests(ctx, engine) {
  for (const guest of engine.guests) {
    const at = guestPosition(guest)
    const eating = guest.phase === 'sit'
    ctx.fillStyle = 'rgba(38, 53, 45, 0.12)'
    ctx.beginPath()
    ctx.ellipse(at.x, at.y + 8, 7, 3, 0, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = guest.walkout ? ERROR : GREEN
    ctx.beginPath()
    ctx.arc(at.x, at.y, eating ? 7.5 : 6.5, 0, Math.PI * 2)
    ctx.fill()
    if (!guest.walkout && guest.actual !== guest.requested) {
      // Took an available alternative rather than what they came in for.
      ctx.strokeStyle = AMBER
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc(at.x, at.y, 10, 0, Math.PI * 2)
      ctx.stroke()
    }
    if (guest.walkout) {
      ctx.strokeStyle = ERROR
      ctx.lineWidth = 1.6
      ctx.beginPath()
      ctx.moveTo(at.x + 8, at.y - 13)
      ctx.lineTo(at.x + 15, at.y - 6)
      ctx.moveTo(at.x + 15, at.y - 13)
      ctx.lineTo(at.x + 8, at.y - 6)
      ctx.stroke()
    }
  }
}

function drawShelf(ctx, engine, spec) {
  ctx.fillStyle = INK_SOFT
  ctx.font = `600 10px ${FONT}`
  ctx.textAlign = 'left'
  ctx.fillText('YOUR SHELF', 36, SHELF.y - 7)
  for (const tile of spec.tiles) {
    const remaining = engine.stock.get(tile.id) || 0
    const fill = clamp(remaining / tile.capacity, 0, 1)
    const flashing = engine.flash.has(tile.id)
    ctx.fillStyle = flashing ? 'rgba(140, 191, 101, 0.28)' : 'rgba(255, 255, 255, 0.72)'
    roundRect(ctx, tile.x, SHELF.y, tile.w, SHELF.h, 10)
    ctx.fill()
    ctx.strokeStyle = flashing ? FRESH : HAIRLINE
    ctx.lineWidth = flashing ? 2 : 1
    ctx.stroke()

    ctx.textAlign = 'left'
    ctx.font = '17px sans-serif'
    ctx.fillStyle = INK
    ctx.fillText(tile.emoji, tile.x + 10, SHELF.y + 26)
    ctx.font = `600 11px ${FONT}`
    ctx.fillStyle = INK
    ctx.fillText(tile.name.length > 13 ? `${tile.name.slice(0, 12)}…` : tile.name, tile.x + 34, SHELF.y + 20)
    ctx.font = `500 10px ${FONT}`
    ctx.fillStyle = remaining <= 1e-6 ? ERROR : INK_SOFT
    ctx.fillText(remaining <= 1e-6 ? 'out of stock' : `${remaining.toFixed(2)} ${tile.unit}`, tile.x + 34, SHELF.y + 33)

    ctx.fillStyle = 'rgba(38, 53, 45, 0.1)'
    roundRect(ctx, tile.x + 10, SHELF.y + 42, tile.w - 20, 7, 3.5)
    ctx.fill()
    if (fill > 0) {
      ctx.fillStyle = fill < 0.15 ? ERROR : fill < 0.35 ? AMBER : FRESH
      roundRect(ctx, tile.x + 10, SHELF.y + 42, Math.max((tile.w - 20) * fill, 3), 7, 3.5)
      ctx.fill()
    }
  }
}

function drawFlyingFood(ctx, engine) {
  // Spoilage drifts up off the shelf and fades out.
  for (const spoil of engine.spoils) {
    const p = spoil.t / SPOIL_LIFE
    const cx = spoil.tile.x + spoil.tile.w / 2 + spoil.drift * p
    const cy = SHELF.y + 26 - 34 * p
    ctx.globalAlpha = 1 - p
    ctx.font = '15px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillStyle = INK
    ctx.fillText(spoil.tile.emoji, cx, cy)
    ctx.strokeStyle = ERROR
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(cx - 8, cy - 13)
    ctx.lineTo(cx + 8, cy + 3)
    ctx.stroke()
    ctx.globalAlpha = 1
  }

  // Ingredients flying from the shelf to the table that ordered them.
  for (const chip of engine.chips) {
    const p = chip.t / CHIP_FLIGHT
    const eased = ease(p)
    ctx.globalAlpha = p < 0.65 ? 1 : 1 - (p - 0.65) / 0.35
    ctx.font = `${13 - 5 * eased}px sans-serif`
    ctx.textAlign = 'center'
    ctx.fillStyle = INK
    ctx.fillText(
      chip.tile.emoji,
      lerp(chip.tile.x + chip.tile.w / 2, chip.to.x, eased),
      lerp(SHELF.y + SHELF.h - 8, chip.to.y - 12, eased),
    )
    ctx.globalAlpha = 1
  }
}

export function draw(ctx, engine, spec, meta) {
  ctx.clearRect(0, 0, W, H)
  drawRoom(ctx)
  drawGuests(ctx, engine)
  drawShelf(ctx, engine, spec)
  drawFlyingFood(ctx, engine)

  ctx.textAlign = 'left'
  ctx.font = `600 13px ${FONT}`
  ctx.fillStyle = GREEN
  const dayName = DAY_NAMES[engine.day] || `Day ${engine.day + 1}`
  ctx.fillText(`${dayName} · day ${engine.day + 1} of ${spec.days}`, 36, SHELF.y + SHELF.h + 24)
  ctx.textAlign = 'right'
  ctx.font = `500 11px ${FONT}`
  ctx.fillStyle = INK_SOFT
  ctx.fillText(meta, W - 36, SHELF.y + SHELF.h + 24)
}

