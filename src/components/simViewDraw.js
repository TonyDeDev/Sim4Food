// Pixel-art renderer for the simulation replay. Everything is drawn as flat
// blocks on a 320x180 buffer with no gradients, curves or antialiasing, which
// is what makes it read as retro once the browser upscales it. Pure: given a
// context and an engine it paints one frame and returns nothing.
import { drawText, toFontSafe } from './pixelFont.js'
import {
  AWNING, BUILDING, CURB_Y, DOOR, GROUND_Y, LEFT, PH, PW, SIGN, SPRITE_H, SUBSTITUTED, WINDOWS,
  textPose, visitorPose,
} from './simViewEngine.js'

const DAY_NAMES = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']

// A deliberately small palette, the way an 8-bit tileset would have.
const SKY = '#bfe0d2'
const SKY_BAND = '#d3e9dd'
const SKY_HAZE = '#e3f1e8'
const CLOUD = '#f6fbf7'
const WALL = '#f2e9d3'
const WALL_SHADE = '#ded2b6'
const WALL_LINE = '#cfc2a4'
const ROOF = '#245c45'
const ROOF_SHADE = '#1c4a37'
const SIGN_BG = '#1c4a37'
const SIGN_EDGE = '#8cbf65'
const CREAM = '#fff8ea'
const AWNING_A = '#b3402a'
const AWNING_B = '#fff8ea'
const DOORWAY = '#2b3a33'
const GLASS = '#f5c95b'
const GLASS_DIM = '#d9a93f'
const SILHOUETTE = '#4a3a22'
const PAVEMENT = '#e6e0d0'
const PAVEMENT_LINE = '#d3cbb5'
const STREET = '#5b6360'
const STREET_DASH = '#e6e0d0'
const INK = '#26352d'
const PANTS = '#3b4a56'
const SHOES = '#2b2b2b'
const TONE_SERVED = '#fff8ea'
const TONE_SUB = '#f5c95b'
const TONE_LEFT = '#ff9c85'
const OUTLINE = '#1c2a22'

const CLOUDS = [
  { x: 24, y: 18, w: 26 },
  { x: 150, y: 10, w: 34 },
  { x: 250, y: 24, w: 20 },
]

function drawSky(ctx, clock) {
  ctx.fillStyle = SKY
  ctx.fillRect(0, 0, PW, 40)
  ctx.fillStyle = SKY_BAND
  ctx.fillRect(0, 40, PW, 44)
  ctx.fillStyle = SKY_HAZE
  ctx.fillRect(0, 84, PW, GROUND_Y - 84)

  // Clouds drift slowly and wrap, which is the only thing telling the eye that
  // the scene is alive between customers.
  ctx.fillStyle = CLOUD
  for (const cloud of CLOUDS) {
    const x = Math.round(((cloud.x + clock * 0.006) % (PW + 60)) - 30)
    ctx.fillRect(x, cloud.y, cloud.w, 4)
    ctx.fillRect(x + 4, cloud.y - 3, cloud.w - 10, 3)
    ctx.fillRect(x + 3, cloud.y + 4, cloud.w - 6, 2)
  }
}

function drawStreet(ctx) {
  ctx.fillStyle = PAVEMENT
  ctx.fillRect(0, GROUND_Y, PW, CURB_Y - GROUND_Y)
  ctx.fillStyle = PAVEMENT_LINE
  for (let x = 0; x < PW; x += 24) ctx.fillRect(x, GROUND_Y + 8, 1, CURB_Y - GROUND_Y - 8)
  ctx.fillRect(0, GROUND_Y, PW, 1)

  ctx.fillStyle = STREET
  ctx.fillRect(0, CURB_Y, PW, PH - CURB_Y)
  ctx.fillStyle = PAVEMENT_LINE
  ctx.fillRect(0, CURB_Y, PW, 2)
  ctx.fillStyle = STREET_DASH
  for (let x = 6; x < PW; x += 22) ctx.fillRect(x, CURB_Y + 14, 12, 2)
}

function drawBuilding(ctx, engine, restaurantName, clock) {
  const { x, y, w, roofH, bottom } = BUILDING

  // Walls
  ctx.fillStyle = WALL
  ctx.fillRect(x, y + roofH, w, bottom - y - roofH)
  ctx.fillStyle = WALL_SHADE
  ctx.fillRect(x, y + roofH, 4, bottom - y - roofH)
  ctx.fillRect(x + w - 4, y + roofH, 4, bottom - y - roofH)
  ctx.fillStyle = WALL_LINE
  ctx.fillRect(x, bottom - 2, w, 2)

  // Pitched roof, stepped one pixel at a time so the slope stays on the grid.
  ctx.fillStyle = ROOF
  const inset = 10
  for (let row = 0; row < roofH; row += 1) {
    const shrink = Math.round((inset * (roofH - row)) / roofH)
    ctx.fillRect(x + shrink, y + row, w - shrink * 2, 1)
  }
  ctx.fillStyle = ROOF_SHADE
  ctx.fillRect(x, y + roofH - 3, w, 3)

  // Name board
  ctx.fillStyle = SIGN_BG
  ctx.fillRect(SIGN.x, SIGN.y, SIGN.w, SIGN.h)
  ctx.fillStyle = SIGN_EDGE
  ctx.fillRect(SIGN.x, SIGN.y, SIGN.w, 1)
  ctx.fillRect(SIGN.x, SIGN.y + SIGN.h - 1, SIGN.w, 1)
  const name = toFontSafe(restaurantName || 'THE DINER', 28)
  // Two sizes: the big one when the name fits, otherwise step down rather than
  // let it run off the board.
  const scale = name.length <= 14 ? 2 : 1
  drawText(ctx, name, SIGN.x + SIGN.w / 2, SIGN.y + (SIGN.h - 5 * scale) / 2, {
    color: CREAM, scale, align: 'center',
  })

  // Striped awning
  for (let i = 0; i < AWNING.w; i += 8) {
    ctx.fillStyle = (i / 8) % 2 === 0 ? AWNING_A : AWNING_B
    ctx.fillRect(AWNING.x + i, AWNING.y, Math.min(8, AWNING.w - i), AWNING.h)
  }
  ctx.fillStyle = ROOF_SHADE
  ctx.fillRect(AWNING.x, AWNING.y + AWNING.h, AWNING.w, 1)

  // Windows, with a silhouette for each customer currently inside
  WINDOWS.forEach((window, windowIndex) => {
    ctx.fillStyle = GLASS
    ctx.fillRect(window.x, window.y, window.w, window.h)
    ctx.fillStyle = GLASS_DIM
    ctx.fillRect(window.x, window.y, window.w, 2)
    ctx.fillStyle = ROOF
    ctx.fillRect(window.x - 2, window.y - 2, window.w + 4, 2)
    ctx.fillRect(window.x - 2, window.y + window.h, window.w + 4, 2)
    ctx.fillRect(window.x - 2, window.y - 2, 2, window.h + 4)
    ctx.fillRect(window.x + window.w, window.y - 2, 2, window.h + 4)

    ctx.fillStyle = SILHOUETTE
    const heads = Math.min(3, Math.max(0, engine.inside - windowIndex * 3))
    for (let head = 0; head < heads; head += 1) {
      const hx = window.x + 5 + head * 10
      ctx.fillRect(hx, window.y + 7, 5, 5)
      ctx.fillRect(hx + 1, window.y + 4, 3, 3)
    }
  })

  // Doorway
  ctx.fillStyle = DOORWAY
  ctx.fillRect(DOOR.x, DOOR.y, DOOR.w, DOOR.h)
  ctx.fillStyle = ROOF
  ctx.fillRect(DOOR.x - 2, DOOR.y - 2, DOOR.w + 4, 2)
  ctx.fillRect(DOOR.x - 2, DOOR.y - 2, 2, DOOR.h + 2)
  ctx.fillRect(DOOR.x + DOOR.w, DOOR.y - 2, 2, DOOR.h + 2)
  ctx.fillStyle = GLASS_DIM
  ctx.fillRect(DOOR.x + 3, DOOR.y + 3, DOOR.w - 6, 7)

  // Door slab standing ajar, so the opening reads as a way in rather than an
  // alcove, plus the blinking OPEN transom that says the place is trading.
  ctx.fillStyle = ROOF_SHADE
  ctx.fillRect(DOOR.x + DOOR.w - 7, DOOR.y + 4, 6, DOOR.h - 4)
  ctx.fillStyle = SIGN_EDGE
  ctx.fillRect(DOOR.x + DOOR.w - 6, DOOR.y + 13, 1, 2)

  const lit = Math.floor(clock / 700) % 2 === 0
  ctx.fillStyle = '#12211a'
  ctx.fillRect(DOOR.x + 2, DOOR.y + 2, DOOR.w - 10, 9)
  drawText(ctx, 'OPEN', DOOR.x + 2 + (DOOR.w - 10) / 2, DOOR.y + 5, {
    color: lit ? GLASS : '#6b5a2a', scale: 1, align: 'center',
  })
}

/** One customer: 7 wide, 15 tall, four flat colours and a two frame stride. */
function drawVisitor(ctx, visitor) {
  const pose = visitorPose(visitor)
  if (pose.alpha <= 0.01) return
  ctx.globalAlpha = Math.max(0, Math.min(1, pose.alpha))

  const left = pose.x - 3
  const top = pose.footY - SPRITE_H
  const stride = pose.moving && pose.step === 1

  // Head, nudged toward the direction of travel so they read as facing it.
  ctx.fillStyle = visitor.skin
  ctx.fillRect(left + 2 + (pose.facing > 0 ? 1 : 0), top, 3, 3)

  // Torso and arms
  ctx.fillStyle = visitor.shirt
  ctx.fillRect(left + 1, top + 3, 5, 6)
  ctx.fillRect(left, top + 4, 1, stride ? 5 : 4)
  ctx.fillRect(left + 6, top + 4, 1, stride ? 4 : 5)

  // Legs: the two frames swap which one is forward.
  ctx.fillStyle = PANTS
  if (stride) {
    ctx.fillRect(left + 1, top + 9, 2, 4)
    ctx.fillRect(left + 4, top + 9, 2, 5)
  } else {
    ctx.fillRect(left + 1, top + 9, 2, 5)
    ctx.fillRect(left + 4, top + 9, 2, 4)
  }
  ctx.fillStyle = SHOES
  ctx.fillRect(left + 1, top + (stride ? 13 : 14), 2, 1)
  ctx.fillRect(left + 4, top + (stride ? 14 : 13), 2, 1)

  ctx.globalAlpha = 1
}

const toneColor = (tone) => (tone === LEFT ? TONE_LEFT : tone === SUBSTITUTED ? TONE_SUB : TONE_SERVED)

function drawOrderTexts(ctx, engine) {
  for (const text of engine.texts) {
    const pose = textPose(text)
    // Gone with its customer; nothing left to paint.
    if (pose.x < -60 || pose.x > PW + 60) continue
    ctx.globalAlpha = Math.max(0, Math.min(1, pose.alpha))
    drawText(ctx, toFontSafe(text.text, 20), pose.x, pose.y, {
      color: toneColor(text.tone), scale: 1, align: 'center', outline: OUTLINE,
    })
    ctx.globalAlpha = 1
  }
}

function drawHud(ctx, engine, spec, meta) {
  drawText(ctx, DAY_NAMES[engine.day] || `DAY ${engine.day + 1}`, 8, 8, { color: ROOF, scale: 2 })
  drawText(ctx, `SERVED ${engine.served}`, 8, 24, { color: INK, scale: 1 })
  if (engine.walkedOut) {
    drawText(ctx, `TURNED AWAY ${engine.walkedOut}`, 8, 32, { color: AWNING_A, scale: 1 })
  }
  drawText(ctx, meta, PW - 8, 8, { color: INK, scale: 1, align: 'right' })
  drawText(ctx, `DAY ${engine.day + 1} OF ${spec.days}`, PW - 8, 16, { color: INK, scale: 1, align: 'right' })
}

export function drawScene(ctx, engine, spec, { restaurantName, meta }) {
  ctx.clearRect(0, 0, PW, PH)
  drawSky(ctx, engine.clock)
  drawStreet(ctx)
  drawBuilding(ctx, engine, restaurantName, engine.clock)
  // Anyone still on the pavement is in front of the building, and their order
  // label sits above everything so it never disappears behind the awning.
  for (const visitor of engine.visitors) drawVisitor(ctx, visitor)
  drawOrderTexts(ctx, engine)
  drawHud(ctx, engine, spec, meta)
}
