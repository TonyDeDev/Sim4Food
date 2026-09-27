'use client'

// Plays back one recorded simulated week as a retro street scene: customers
// arrive, go inside, and come out again with what they ordered floating off
// above them. The canvas buffer is a fixed 320x180 and CSS upscales it with
// nearest-neighbour, which is what keeps the pixels chunky at any size.
//
// The scene is driven entirely by the backend replay log, and calls onFinish
// once the week has played out - the caller uses that to reveal the numbers.
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { PH, PW, buildScene, createEngine } from './simViewEngine.js'
import { drawScene } from './simViewDraw.js'

const MOTION_QUERY = '(prefers-reduced-motion: reduce)'

function subscribeToMotionPreference(onChange) {
  const query = window.matchMedia(MOTION_QUERY)
  query.addEventListener('change', onChange)
  return () => query.removeEventListener('change', onChange)
}

function usePrefersReducedMotion() {
  // Read through the browser rather than mirroring it into state, so the first
  // paint already honours the preference. There are no media queries on the
  // server, so rendering there assumes motion is fine and the client settles it
  // on hydration.
  return useSyncExternalStore(
    subscribeToMotionPreference,
    () => window.matchMedia(MOTION_QUERY).matches,
    () => false,
  )
}

const EMPTY_HUD = { day: 0, served: 0, substituted: 0, walkedOut: 0, finished: false, progress: 0 }

/**
 * Mount this with a `key` that changes per simulation run: a new result should
 * play from the top, which a remount gives for free.
 */
export default function SimView({ replay, runs, restaurantName, onFinish }) {
  const canvasRef = useRef(null)
  const speedRef = useRef(2)
  const skipRef = useRef(false)
  const finishRef = useRef(onFinish)
  const [speed, setSpeed] = useState(2)
  const [hud, setHud] = useState(EMPTY_HUD)
  const reduceMotion = usePrefersReducedMotion()
  const spec = useMemo(() => buildScene(replay), [replay])

  useEffect(() => { speedRef.current = speed }, [speed])
  // Kept in a ref so a new callback identity never restarts the playback.
  useEffect(() => { finishRef.current = onFinish }, [onFinish])

  const meta = spec ? `WEEK ${(replay.run_index ?? 0) + 1} OF ${runs || 0}` : ''
  const name = restaurantName || 'THE DINER'

  useEffect(() => {
    const canvas = canvasRef.current
    if (!spec || !canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const engine = createEngine(spec, (replay.run_index ?? 0) + 1)
    const options = { restaurantName: name, meta }
    let frame = 0
    let done = false

    const settle = () => {
      if (done) return
      done = true
      setHud(engine.hud())
      finishRef.current?.()
    }

    if (reduceMotion) {
      engine.runToEnd()
      drawScene(ctx, engine, spec, options)
      settle()
      return undefined
    }

    let last = performance.now()
    let hudAt = 0
    const tick = (now) => {
      // A backgrounded tab resumes where it left off instead of skipping ahead.
      const dt = Math.min(now - last, 64)
      last = now
      if (skipRef.current && !engine.finished) engine.runToEnd()
      else if (!engine.finished) engine.step(dt * speedRef.current)
      drawScene(ctx, engine, spec, options)
      // The canvas redraws every frame, but the React side only carries a
      // progress bar, so re-rendering it at 60Hz would be waste for no gain.
      if (now - hudAt > 100) { hudAt = now; setHud(engine.hud()) }
      if (engine.finished) settle()
      else frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [spec, reduceMotion, meta, name, replay])

  if (!spec) return null

  return <section className="simview" aria-labelledby="simview-title">
    <div className="simview-head">
      <h3 id="simview-title">Simulating next week at {name}</h3>
      <p className="hint">
        One of the {runs || 'simulated'} weeks, played back at speed. Each customer who leaves shows what they
        ordered. Your numbers appear once the week finishes.
      </p>
    </div>
    <canvas
      ref={canvasRef}
      className="simview-canvas"
      width={PW}
      height={PH}
      role="img"
      aria-label={`Animation of one simulated week at ${name}: ${replay?.totals?.orders || 0} orders, of which ${replay?.totals?.walked_out || 0} customers left because stock had run out.`}
    />
    <div className="simview-controls">
      {!hud.finished && <button
        type="button"
        className="simview-btn"
        onClick={() => { skipRef.current = true }}
      >Skip to results</button>}
      <div className="simview-speeds" role="group" aria-label="Playback speed">
        {[1, 2, 4].map((option) => <button
          key={option}
          type="button"
          className={`simview-speed${speed === option ? ' is-active' : ''}`}
          aria-pressed={speed === option}
          onClick={() => setSpeed(option)}
        >{option}x</button>)}
      </div>
      <div className="simview-progress" aria-hidden="true"><span style={{ width: `${hud.progress * 100}%` }} /></div>
    </div>
  </section>
}
