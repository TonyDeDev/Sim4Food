'use client'

// Draws the replay of one recorded simulated week: guests arrive, take a table,
// eat their dish, and leave, while the ingredients that dish uses pop off the
// shelf and fade. Every guest, walkout, delivery and spoilage drawn here comes
// from the backend replay log, so the animation shows the run - it never
// influences it. The week's arithmetic lives in simViewEngine.js.
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { H, W, buildSpec, createEngine } from './simViewEngine.js'
import { draw } from './simViewDraw.js'

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

const EMPTY_HUD = { day: 0, served: 0, substituted: 0, walkedOut: 0, note: '', finished: false, progress: 0 }

/**
 * Mount this with a `key` that changes per simulation run: a new result should
 * start its own playback from the top, which a remount gives for free.
 */
export default function SimView({ replay, runs }) {
  const canvasRef = useRef(null)
  const playingRef = useRef(true)
  const speedRef = useRef(2)
  const [playing, setPlaying] = useState(true)
  // 2x is the default: a week is a demo beat, not a wait.
  const [speed, setSpeed] = useState(2)
  const [attempt, setAttempt] = useState(0)
  const [hud, setHud] = useState(EMPTY_HUD)
  const reduceMotion = usePrefersReducedMotion()
  const spec = useMemo(() => buildSpec(replay), [replay])

  useEffect(() => { playingRef.current = playing }, [playing])
  useEffect(() => { speedRef.current = speed }, [speed])

  const totals = replay?.totals
  const meta = spec ? `week ${(replay.run_index ?? 0) + 1} of ${runs || '?'} · recommended plan` : ''

  useEffect(() => {
    const canvas = canvasRef.current
    if (!spec || !canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const engine = createEngine(spec)

    // Fit the backing store to the element box and the device pixel ratio, so
    // the drawing stays sharp on a laptop screen and on a projector.
    const fit = () => {
      const dpr = window.devicePixelRatio || 1
      const width = canvas.clientWidth || W
      const scale = width / W
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(H * scale * dpr)
      ctx.setTransform(dpr * scale, 0, 0, dpr * scale, 0, 0)
      draw(ctx, engine, spec, meta)
    }
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(canvas)

    if (reduceMotion) {
      engine.runToEnd()
      draw(ctx, engine, spec, meta)
      setHud(engine.hud())
      return () => observer.disconnect()
    }

    let frame = 0
    let last = performance.now()
    let hudAt = 0
    const tick = (now) => {
      // A backgrounded tab resumes where it left off instead of skipping ahead.
      const dt = Math.min(now - last, 64)
      last = now
      if (playingRef.current && !engine.finished) engine.step(dt * speedRef.current)
      draw(ctx, engine, spec, meta)
      if (now - hudAt > 120 || engine.finished) { hudAt = now; setHud(engine.hud()) }
      if (!engine.finished) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(frame); observer.disconnect() }
  }, [spec, reduceMotion, attempt, meta])

  if (!spec) return null

  return <section className="simview" aria-labelledby="simview-title">
    <div className="simview-head">
      <h3 id="simview-title">Watch the week run</h3>
      <p className="hint">
        One of the {runs || 'simulated'} weeks, played back at speed. Guests arrive, order and eat, and each dish
        takes its recipe off your shelf. A red guest is one who left because an ingredient had run out.
      </p>
    </div>
    <canvas
      ref={canvasRef}
      className="simview-canvas"
      role="img"
      aria-label={`Animated replay of one simulated week: ${totals?.orders || 0} orders, ${totals?.served_as_ordered || 0} served as ordered, ${totals?.substituted || 0} given an alternative, ${totals?.walked_out || 0} left because stock ran out.`}
    />
    <div className="simview-stats" role="status">
      <span className="simview-stat"><i className="simview-key is-served" />Served <strong>{hud.served}</strong></span>
      <span className="simview-stat"><i className="simview-key is-sub" />Took an alternative <strong>{hud.substituted}</strong></span>
      <span className="simview-stat"><i className="simview-key is-lost" />Left unserved <strong>{hud.walkedOut}</strong></span>
      <span className="simview-note">{hud.note}</span>
    </div>
    <div className="simview-controls">
      <button
        type="button"
        className="simview-btn"
        onClick={() => (hud.finished ? setAttempt((value) => value + 1) : setPlaying(!playing))}
      >{hud.finished ? 'Replay' : playing ? 'Pause' : 'Play'}</button>
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
