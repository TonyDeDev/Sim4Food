// Playback engine for the simulation replay animation: it turns the backend's
// recorded week into a timeline of guests, shelf levels, deliveries and
// spoilage. Deliberately free of React and canvas so the week's arithmetic can
// be exercised on its own; SimView.jsx only draws what this reports.

// One logical drawing space, fitted to whatever width the panel gives us, so
// every coordinate here is layout units rather than device pixels.
export const W = 960
export const H = 400
export const ROOM = { x: 36, y: 96, w: 888, h: 236 }
export const DOOR = { x: 436, w: 88 }
export const SHELF = { y: 22, h: 60 }
export const STREET_Y = 374

// Phase lengths for one guest, in playback milliseconds.
const WALK_IN = 420
const DWELL = 780
const WALK_OUT = 360
const TURN_BACK = 340
export const CHIP_FLIGHT = 540
export const SPOIL_LIFE = 900
const NOTE_LIFE = 1400
const FLASH_LIFE = 700
const MAX_CHIPS = 96
const MAX_TILES = 6
const SEAT_ANGLES = [-2.36, -0.79, 0.79, 2.36]
const SEAT_COUNT = 8 * SEAT_ANGLES.length
const ORDER_SPACING = Math.ceil((WALK_IN + DWELL + WALK_OUT) / SEAT_COUNT) + 3

export const clamp = (value, low, high) => Math.max(low, Math.min(high, value))
export const lerp = (a, b, t) => a + (b - a) * t
export const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2)

// Ingredient names are free text from the owner's upload, so the glyph is a
// best-effort match with a neutral fallback rather than a required mapping.
const EMOJI = [
  [/chicken|poultry|wing|drumstick/i, '🍗'],
  [/beef|steak|mince|lamb|pork|bacon|ham/i, '🥩'],
  [/egg/i, '🥚'],
  [/tomato/i, '🍅'],
  [/cheese|feta|mozzarella|paneer|halloumi/i, '🧀'],
  [/lettuce|salad|spinach|cabbage|kale|herb/i, '🥬'],
  [/pasta|noodle|spaghetti|penne/i, '🍝'],
  [/rice|grain|quinoa/i, '🍚'],
  [/bread|bun|dough|flour|tortilla|pita/i, '🍞'],
  [/potato|fries|chips|wedge/i, '🥔'],
  [/onion|garlic|shallot|leek/i, '🧄'],
  [/fish|salmon|tuna|prawn|shrimp|squid/i, '🐟'],
  [/milk|cream|butter|yog|dairy/i, '🥛'],
  [/oil|olive/i, '🫒'],
  [/pepper|chilli|chili|capsicum/i, '🌶'],
  [/mushroom/i, '🍄'],
  [/carrot/i, '🥕'],
  [/avocado|guac/i, '🥑'],
  [/lemon|lime|citrus/i, '🍋'],
  [/apple|fruit|berry/i, '🍎'],
  [/coffee|bean|espresso/i, '☕'],
  [/sugar|honey|syrup|choc/i, '🍫'],
]
export const emojiFor = (name) => (EMOJI.find(([pattern]) => pattern.test(name || '')) || [null, '🥫'])[1]

// Eight tables, four seats each. At 1x a busy week offers roughly 29 guests at
// once (about 19 orders a second, each guest on screen for 1.56s), so 32 seats
// keep nearly every order visible; a full room still counts and still eats.
export const TABLES = Array.from({ length: 8 }, (_, index) => ({
  x: ROOM.x + 150 + (index % 4) * 208,
  y: ROOM.y + 54 + Math.floor(index / 4) * 116,
}))
const SEATS = TABLES.flatMap((table) => SEAT_ANGLES.map((angle) => ({
  x: table.x + Math.cos(angle) * 36,
  y: table.y + Math.sin(angle) * 31,
})))
const doorPoint = (spread = 1) => ({
  x: DOOR.x + DOOR.w / 2 + (Math.random() - 0.5) * DOOR.w * 0.6 * spread,
  y: STREET_Y - 6,
})

/** Flattens a replay log into a playable timeline plus the shelf tiles. */
export function buildSpec(replay) {
  const orders = replay?.orders || []
  if (!orders.length) return null
  const days = replay.days || 7
  const dishes = replay.dishes || []
  const recipes = replay.recipes || {}

  // What the week actually eats decides which ingredients earn a tile, busiest
  // first, so the shelf never shows something that cannot move.
  const consumed = new Map()
  for (const [, , served] of orders) {
    const dish = dishes[served]
    if (served < 0 || !dish) continue
    for (const [id, quantity] of Object.entries(recipes[dish.id] || {})) {
      consumed.set(id, (consumed.get(id) || 0) + quantity)
    }
  }
  // The most any ingredient can hold is its opening stock plus everything that
  // arrives, which keeps each tile's fill bar inside its own frame all week.
  const capacity = new Map((replay.ingredients || []).map((row) => [row.id, row.opening_stock || 0]))
  for (const arrival of replay.arrivals || []) {
    capacity.set(arrival.ingredient_id, (capacity.get(arrival.ingredient_id) || 0) + arrival.qty)
  }
  const shortlist = (replay.ingredients || [])
    .filter((row) => consumed.has(row.id))
    .sort((a, b) => (consumed.get(b.id) || 0) - (consumed.get(a.id) || 0))
    .slice(0, MAX_TILES)
  const gap = 14
  const tileWidth = (W - 72 - gap * Math.max(shortlist.length - 1, 0)) / Math.max(shortlist.length, 1)
  const tiles = shortlist.map((row, index) => ({
    id: row.id,
    name: row.name,
    unit: row.unit,
    opening: row.opening_stock || 0,
    emoji: emojiFor(row.name),
    capacity: Math.max(capacity.get(row.id) || 0, 1e-6),
    x: 36 + index * (tileWidth + gap),
    w: tileWidth,
  }))

  const perDay = Array.from({ length: days }, () => [])
  for (const order of orders) perDay[clamp(order[0], 0, days - 1)].push(order)
  const schedule = []
  const dayStarts = []
  let cursor = 0
  perDay.forEach((dayOrders, day) => {
    // A busy day plays longer than a quiet one, but the whole week still lands
    // in a demo-sized window rather than dragging. ORDER_SPACING is what keeps
    // the room legible: a guest is on screen for WALK_IN + DWELL + WALK_OUT, so
    // spacing arrivals by that over the seat count means a typical week fills
    // the room without overflowing it. A restaurant busy enough to hit the
    // ceiling saturates the seats, and the extra orders still count and still
    // draw down the shelf - they just have nowhere to sit.
    const duration = clamp(dayOrders.length * ORDER_SPACING, 1600, 4000)
    dayStarts.push(cursor)
    dayOrders.forEach((order, position) => {
      schedule.push({ time: cursor + ((position + 0.5) / dayOrders.length) * duration, day, order })
    })
    cursor += duration
  })
  dayStarts.push(cursor)

  // Deliveries and spoilage land at the start of a day, exactly as the
  // simulation applies them. Day `days` is the end-of-week sweep.
  const dayEvents = Array.from({ length: days + 1 }, () => ({ arrivals: [], expiries: [] }))
  for (const arrival of replay.arrivals || []) dayEvents[clamp(arrival.day, 0, days)].arrivals.push(arrival)
  for (const expiry of replay.expiries || []) dayEvents[clamp(expiry.day, 0, days)].expiries.push(expiry)

  return { days, dishes, recipes, tiles, schedule, dayStarts, dayEvents, total: Math.max(cursor, 1) }
}

export function createEngine(spec) {
  const tileById = new Map(spec.tiles.map((tile) => [tile.id, tile]))
  const engine = {
    clock: 0,
    orderCursor: 0,
    dayCursor: 0,
    day: 0,
    served: 0,
    substituted: 0,
    walkedOut: 0,
    drawnOrders: 0,
    finished: false,
    guests: [],
    chips: [],
    spoils: [],
    note: '',
    noteAge: Infinity,
    stock: new Map(spec.tiles.map((tile) => [tile.id, tile.opening])),
    flash: new Map(),
    freeSeats: SEATS.map((_, index) => index),
  }

  const setNote = (text) => { engine.note = text; engine.noteAge = 0 }

  function applyDayStart(day) {
    const events = spec.dayEvents[day]
    if (!events) return
    for (const expiry of events.expiries) {
      const tile = tileById.get(expiry.ingredient_id)
      if (!tile) continue
      engine.stock.set(tile.id, Math.max(0, (engine.stock.get(tile.id) || 0) - expiry.qty))
      engine.spoils.push({ tile, t: 0, drift: (Math.random() - 0.5) * 16 })
      setNote(`${tile.name}: ${expiry.qty.toFixed(2)} ${tile.unit} past its shelf life, thrown away`)
    }
    for (const arrival of events.arrivals) {
      const tile = tileById.get(arrival.ingredient_id)
      if (!tile) continue
      engine.stock.set(tile.id, (engine.stock.get(tile.id) || 0) + arrival.qty)
      engine.flash.set(tile.id, 0)
      setNote(`Delivery: ${arrival.qty.toFixed(2)} ${tile.unit} of ${tile.name}`)
    }
  }

  /** Takes the dish's ingredients off the shelf and sends them to the table. */
  function consume(dishIndex, target) {
    const dish = spec.dishes[dishIndex]
    if (!dish) return
    for (const [ingredientId, quantity] of Object.entries(spec.recipes[dish.id] || {})) {
      const tile = tileById.get(ingredientId)
      if (!tile) continue
      engine.stock.set(tile.id, Math.max(0, (engine.stock.get(tile.id) || 0) - quantity))
      if (target && engine.chips.length < MAX_CHIPS) engine.chips.push({ tile, to: target, t: 0 })
    }
  }

  function spawn({ order }) {
    const [, requested, actual] = order
    const walkout = actual < 0
    if (walkout) engine.walkedOut += 1
    else if (actual === requested) engine.served += 1
    else engine.substituted += 1

    const from = doorPoint()
    if (walkout) {
      engine.guests.push({
        phase: 'turn',
        t: 0,
        from,
        to: { x: from.x + (Math.random() - 0.5) * 90, y: ROOM.y + ROOM.h - 34 },
        walkout: true,
        requested,
        actual,
      })
      engine.drawnOrders += 1
      return
    }
    const seatIndex = engine.freeSeats.length ? engine.freeSeats.pop() : null
    if (seatIndex === null) {
      // A full room still eats: the order is counted and the shelf still drops,
      // it just has no free seat to be drawn in.
      consume(actual, null)
      return
    }
    engine.guests.push({
      phase: 'in', t: 0, from, seatIndex, seat: SEATS[seatIndex], walkout: false, requested, actual, ate: false,
    })
    engine.drawnOrders += 1
  }

  engine.step = (dt) => {
    engine.clock += dt
    while (engine.dayCursor <= spec.days && engine.clock >= spec.dayStarts[engine.dayCursor]) {
      applyDayStart(engine.dayCursor)
      engine.day = Math.min(engine.dayCursor, spec.days - 1)
      engine.dayCursor += 1
    }
    while (engine.orderCursor < spec.schedule.length && engine.clock >= spec.schedule[engine.orderCursor].time) {
      spawn(spec.schedule[engine.orderCursor])
      engine.orderCursor += 1
    }

    for (const guest of engine.guests) {
      guest.t += dt
      if (guest.phase === 'in' && guest.t >= WALK_IN) {
        guest.phase = 'sit'
        guest.t -= WALK_IN
        if (!guest.ate) { guest.ate = true; consume(guest.actual, guest.seat) }
      } else if (guest.phase === 'sit' && guest.t >= DWELL) {
        guest.phase = 'out'
        guest.t -= DWELL
        guest.exit = doorPoint()
      } else if (guest.phase === 'turn' && guest.t >= TURN_BACK) {
        guest.phase = 'out'
        guest.t -= TURN_BACK
        guest.exit = doorPoint(1.4)
      } else if (guest.phase === 'out' && guest.t >= WALK_OUT) {
        guest.phase = 'gone'
        if (guest.seatIndex != null) engine.freeSeats.push(guest.seatIndex)
      }
    }
    engine.guests = engine.guests.filter((guest) => guest.phase !== 'gone')
    for (const chip of engine.chips) chip.t += dt
    engine.chips = engine.chips.filter((chip) => chip.t < CHIP_FLIGHT)
    for (const spoil of engine.spoils) spoil.t += dt
    engine.spoils = engine.spoils.filter((spoil) => spoil.t < SPOIL_LIFE)
    for (const [id, age] of engine.flash) {
      if (age > FLASH_LIFE) engine.flash.delete(id)
      else engine.flash.set(id, age + dt)
    }
    engine.noteAge += dt
    engine.finished = engine.orderCursor >= spec.schedule.length
      && engine.dayCursor > spec.days
      && !engine.guests.length
  }

  engine.runToEnd = () => {
    // Reduced motion wants the settled week rather than a blank room, so step
    // through the timeline without ever drawing it.
    let guard = 0
    while (!engine.finished && guard < 20000) { engine.step(48); guard += 1 }
    engine.chips = []
    engine.spoils = []
    engine.note = ''
  }

  engine.hud = () => ({
    day: engine.day,
    served: engine.served,
    substituted: engine.substituted,
    walkedOut: engine.walkedOut,
    note: engine.noteAge < NOTE_LIFE ? engine.note : '',
    finished: engine.finished,
    progress: clamp(engine.clock / spec.total, 0, 1),
  })

  return engine
}

export function guestPosition(guest) {
  if (guest.phase === 'in') {
    // Down the aisle first, then across to the seat, so guests read as walking
    // to a table rather than sliding through the furniture.
    const p = ease(clamp(guest.t / WALK_IN, 0, 1))
    const via = { x: guest.seat.x, y: ROOM.y + ROOM.h - 30 }
    if (p < 0.55) {
      const q = p / 0.55
      return { x: lerp(guest.from.x, via.x, q), y: lerp(guest.from.y, via.y, q) }
    }
    const q = (p - 0.55) / 0.45
    return { x: lerp(via.x, guest.seat.x, q), y: lerp(via.y, guest.seat.y, q) }
  }
  if (guest.phase === 'sit') return guest.seat
  if (guest.phase === 'turn') {
    const p = ease(clamp(guest.t / TURN_BACK, 0, 1))
    return { x: lerp(guest.from.x, guest.to.x, p), y: lerp(guest.from.y, guest.to.y, p) }
  }
  const p = ease(clamp(guest.t / WALK_OUT, 0, 1))
  const from = guest.seat || guest.to
  const exit = guest.exit || doorPoint()
  return { x: lerp(from.x, exit.x, p), y: lerp(from.y, exit.y, p) }
}
