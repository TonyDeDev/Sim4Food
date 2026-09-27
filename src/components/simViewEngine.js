// Scene logic for the retro simulation replay: a week of customers walking into
// the restaurant and back out again, each carrying what they ordered. Free of
// React and canvas so the timeline can be exercised on its own; simViewDraw.js
// paints whatever this reports.
//
// The scene is a sampled view, not a census. A simulated week is hundreds of
// orders, so only a handful per day get a sprite - enough to read as a busy
// street. The counters still tick through every order in the log, so what the
// HUD says stays true even though the pavement is not carrying 200 people.

// Pixel-art drawing space. The canvas buffer is exactly this size and the
// browser upscales it, so every coordinate here is one chunky pixel.
export const PW = 320
export const PH = 180

export const BUILDING = { x: 92, y: 30, w: 136, roofH: 22, bottom: 118 }
export const SIGN = { x: 100, y: 56, w: 120, h: 18 }
export const AWNING = { x: 96, y: 78, w: 128, h: 10 }
export const DOOR = { x: 148, y: 94, w: 24, h: 24 }
export const WINDOWS = [
  { x: 104, y: 94, w: 34, h: 18 },
  { x: 182, y: 94, w: 34, h: 18 },
]
export const GROUND_Y = 118
export const CURB_Y = 146
export const FOOT_Y = 140
export const SPRITE_H = 15
const DOOR_CX = DOOR.x + DOOR.w / 2

const DAY_MS = 1500
const VISITORS_PER_DAY = 7
const WALK_SPEED = 0.15 // pixels per millisecond
const STEP_MS = 260 // stepping into and out of the doorway
const DWELL_SERVED = [420, 900]
const DWELL_LEFT = [140, 260] // nothing for them, so straight back out
const TEXT_LIFE = 1300
const TEXT_RISE = 18
const TEXT_LANES = 4
const TEXT_LANE_GAP = 8
const TEXT_LIFT = 15
const OFF_LEFT = -10
const OFF_RIGHT = PW + 10

export const SERVED = 'served'
export const SUBSTITUTED = 'substituted'
export const LEFT = 'left'

const SHIRTS = ['#b3402a', '#3f6fa8', '#a8720f', '#6fae4f', '#8a4fa8', '#2f8f8f', '#c2603f']
const SKINS = ['#e8b98a', '#c98d5e', '#8d5a38', '#f0cfa8', '#6b422a']

export const clamp = (value, low, high) => Math.max(low, Math.min(high, value))
const lerp = (a, b, t) => a + (b - a) * t
export const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2)

/** Deterministic per-run generator, so a replayed week looks the same twice. */
function makeRandom(seed) {
  let state = (seed >>> 0) || 1
  return () => {
    state ^= state << 13
    state ^= state >>> 17
    state ^= state << 5
    state >>>= 0
    return state / 4294967296
  }
}

function kindOf(requested, served) {
  if (served < 0) return LEFT
  return served === requested ? SERVED : SUBSTITUTED
}

/**
 * Picks the handful of orders that get a sprite. Even spacing keeps the mix
 * representative, and a day that turned someone away always shows at least one
 * of them - that beat is the whole point of the simulation.
 */
function pickShown(dayOrders, wanted) {
  if (dayOrders.length <= wanted) return new Set(dayOrders.map((_, index) => index))
  const shown = new Set()
  const stride = dayOrders.length / wanted
  for (let slot = 0; slot < wanted; slot += 1) {
    shown.add(Math.min(dayOrders.length - 1, Math.floor(slot * stride)))
  }
  const isLeft = (index) => kindOf(dayOrders[index][1], dayOrders[index][2]) === LEFT
  const firstLeft = dayOrders.findIndex((_, index) => isLeft(index))
  if (firstLeft >= 0 && ![...shown].some(isLeft)) {
    shown.delete(Math.max(...shown))
    shown.add(firstLeft)
  }
  return shown
}

/** Flattens a replay log into a schedule of arrivals across the week. */
export function buildScene(replay) {
  const orders = replay?.orders || []
  if (!orders.length) return null
  const days = replay.days || 7
  const dishes = (replay.dishes || []).map((dish) => dish.name)

  const perDay = Array.from({ length: days }, () => [])
  for (const order of orders) perDay[clamp(order[0], 0, days - 1)].push(order)

  const schedule = []
  perDay.forEach((dayOrders, day) => {
    if (!dayOrders.length) return
    const shown = pickShown(dayOrders, VISITORS_PER_DAY)
    const start = day * DAY_MS
    dayOrders.forEach((order, position) => {
      const [, requested, served] = order
      schedule.push({
        time: start + ((position + 0.5) / dayOrders.length) * DAY_MS,
        day,
        requested,
        served,
        kind: kindOf(requested, served),
        show: shown.has(position),
      })
    })
  })
  schedule.sort((a, b) => a.time - b.time)

  return {
    days,
    dishes,
    schedule,
    dayMs: DAY_MS,
    total: days * DAY_MS,
    totals: replay.totals || null,
  }
}

export function createEngine(spec, seed = 1) {
  const random = makeRandom(seed)
  const engine = {
    clock: 0,
    cursor: 0,
    day: 0,
    served: 0,
    substituted: 0,
    walkedOut: 0,
    inside: 0,
    shown: 0,
    labelLane: 0,
    finished: false,
    visitors: [],
    texts: [],
  }

  function label(entry) {
    const requested = spec.dishes[entry.requested] || 'a dish'
    const served = spec.dishes[entry.served] || 'a dish'
    if (entry.kind === LEFT) return { text: `NO ${requested}`, tone: LEFT }
    if (entry.kind === SUBSTITUTED) return { text: `${served} INSTEAD`, tone: SUBSTITUTED }
    return { text: served, tone: SERVED }
  }

  function spawn(entry) {
    const fromLeft = random() < 0.5
    const startX = fromLeft ? OFF_LEFT : OFF_RIGHT
    const dwell = entry.kind === LEFT ? DWELL_LEFT : DWELL_SERVED
    engine.visitors.push({
      entry,
      phase: 'walk',
      t: 0,
      x: startX,
      startX,
      // A little depth so a queue at the door does not stack into one sprite.
      footY: FOOT_Y - Math.floor(random() * 5),
      exitX: fromLeft ? OFF_RIGHT : OFF_LEFT,
      facing: fromLeft ? 1 : -1,
      walkMs: Math.abs(DOOR_CX - startX) / WALK_SPEED,
      dwellMs: lerp(dwell[0], dwell[1], random()),
      leaveMs: 0,
      doorDepth: 0,
      shirt: SHIRTS[Math.floor(random() * SHIRTS.length)],
      skin: SKINS[Math.floor(random() * SKINS.length)],
      bob: Math.floor(random() * 2),
    })
    engine.shown += 1
  }

  function advance(visitor, dt) {
    visitor.t += dt
    if (visitor.phase === 'walk') {
      const progress = clamp(visitor.t / visitor.walkMs, 0, 1)
      visitor.x = lerp(visitor.startX, DOOR_CX, progress)
      if (progress >= 1) { visitor.phase = 'enter'; visitor.t = 0 }
      return
    }
    if (visitor.phase === 'enter') {
      // Step up into the doorway and fade, as if going indoors.
      const progress = clamp(visitor.t / STEP_MS, 0, 1)
      visitor.x = DOOR_CX
      visitor.doorDepth = ease(progress)
      if (progress >= 1) {
        visitor.phase = 'inside'
        visitor.t = 0
        engine.inside += 1
      }
      return
    }
    if (visitor.phase === 'inside') {
      if (visitor.t >= visitor.dwellMs) {
        visitor.phase = 'exit'
        visitor.t = 0
        engine.inside -= 1
        visitor.facing = visitor.exitX > DOOR_CX ? 1 : -1
        visitor.leaveMs = Math.abs(visitor.exitX - DOOR_CX) / WALK_SPEED
        // What they ordered, announced on the way out. The label rides with
        // them, so a rush of departures fans out across the pavement instead of
        // stacking into an unreadable pile over the door. Lanes keep the ones
        // that leave in the same instant off each other until they separate.
        const { text, tone } = label(visitor.entry)
        engine.texts.push({
          text,
          tone,
          visitor,
          x: DOOR_CX,
          y: visitor.footY - SPRITE_H - TEXT_LIFT - (engine.labelLane % TEXT_LANES) * TEXT_LANE_GAP,
          t: 0,
        })
        engine.labelLane += 1
      }
      return
    }
    if (visitor.phase === 'exit') {
      const progress = clamp(visitor.t / STEP_MS, 0, 1)
      visitor.x = DOOR_CX
      visitor.doorDepth = 1 - ease(progress)
      if (progress >= 1) { visitor.phase = 'leave'; visitor.t = 0; visitor.doorDepth = 0 }
      return
    }
    const progress = clamp(visitor.t / visitor.leaveMs, 0, 1)
    visitor.x = lerp(DOOR_CX, visitor.exitX, progress)
    if (progress >= 1) visitor.phase = 'gone'
  }

  engine.step = (dt) => {
    engine.clock += dt
    engine.day = clamp(Math.floor(engine.clock / spec.dayMs), 0, spec.days - 1)

    while (engine.cursor < spec.schedule.length && engine.clock >= spec.schedule[engine.cursor].time) {
      const entry = spec.schedule[engine.cursor]
      // Every order moves the counters; only the sampled ones get a sprite.
      if (entry.kind === SERVED) engine.served += 1
      else if (entry.kind === SUBSTITUTED) engine.substituted += 1
      else engine.walkedOut += 1
      if (entry.show) spawn(entry)
      engine.cursor += 1
    }

    for (const visitor of engine.visitors) advance(visitor, dt)
    engine.visitors = engine.visitors.filter((visitor) => visitor.phase !== 'gone')
    for (const text of engine.texts) {
      text.t += dt
      // Follow the customer until they walk off the edge, then hold position.
      if (text.visitor) {
        if (text.visitor.phase === 'gone') text.visitor = null
        else text.x = text.visitor.x
      }
    }
    engine.texts = engine.texts.filter((text) => text.t < TEXT_LIFE)

    engine.finished = engine.cursor >= spec.schedule.length
      && !engine.visitors.length
      && !engine.texts.length
      && engine.clock >= spec.total
  }

  /** Runs the week out without drawing, for reduced motion and for Skip. */
  engine.runToEnd = () => {
    let guard = 0
    while (!engine.finished && guard < 20000) { engine.step(32); guard += 1 }
    for (const text of engine.texts) text.visitor = null
    engine.visitors = []
    engine.texts = []
    engine.inside = 0
  }

  engine.hud = () => ({
    day: engine.day,
    served: engine.served,
    substituted: engine.substituted,
    walkedOut: engine.walkedOut,
    finished: engine.finished,
    progress: clamp(engine.clock / spec.total, 0, 1),
  })

  return engine
}

/** Where a visitor's sprite sits this frame, and how far into the door it is. */
export function visitorPose(visitor) {
  const depth = visitor.doorDepth || 0
  return {
    x: Math.round(visitor.x),
    footY: Math.round(visitor.footY - depth * 20),
    // Fades as they cross the threshold, so the doorway swallows them.
    alpha: 1 - depth,
    // Two frame walk cycle driven by distance covered rather than by time, so
    // the feet still match the stride at 4x speed.
    step: Math.abs(Math.floor(visitor.x / 5) + visitor.bob) % 2,
    moving: visitor.phase === 'walk' || visitor.phase === 'leave',
    facing: visitor.facing,
  }
}

export function textPose(text) {
  const progress = clamp(text.t / TEXT_LIFE, 0, 1)
  return {
    // Follows its customer right off the edge rather than being pinned to the
     // frame, which would stack every departed label in the same spot.
    x: Math.round(text.x),
    y: Math.round(text.y - TEXT_RISE * ease(progress)),
    // Pops in fast, holds, then fades into the scene.
    alpha: progress < 0.12 ? progress / 0.12 : progress > 0.6 ? 1 - (progress - 0.6) / 0.4 : 1,
  }
}
