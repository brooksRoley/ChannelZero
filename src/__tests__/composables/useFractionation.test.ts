import { describe, it, expect } from 'vitest'
import {
  step,
  initialState,
  DEFAULT_CONFIG,
  type FracState,
  type FracEvent,
  type FracEffect,
} from '@/composables/useFractionation'
import { FRACTIONATION_SCRIPT } from '@/data/fractionationScript'

interface Log { t: number; effect: FracEffect; stage: FracState['stage'] }

/**
 * Drives the reducer on a simulated clock. Every 'say' is answered with
 * VOICE_DONE `voiceMs` later; `eyes(t, state)` gives the camera reading,
 * sent as an EYES event whenever it changes (camera runs only).
 */
function simulate(opts: {
  camera: boolean
  eyes?: (t: number, s: FracState) => boolean
  voiceMs?: number
  tickMs?: number
  untilMs?: number
  stopAt?: (t: number, s: FracState) => boolean
}) {
  const voiceMs = opts.voiceMs ?? 2000
  const tickMs = opts.tickMs ?? 250
  const untilMs = opts.untilMs ?? 30 * 60_000
  const log: Log[] = []
  let state = initialState()
  let voiceDoneAt: number | null = null
  let sayOverlap = false
  let lastEyes: boolean | null = null

  const send = (ev: FracEvent) => {
    const r = step(state, ev)
    state = r.state
    for (const e of r.effects) {
      if (e.type === 'say') {
        if (voiceDoneAt !== null) sayOverlap = true
        voiceDoneAt = ev.t + voiceMs
      }
      log.push({ t: ev.t, effect: e, stage: state.stage })
    }
  }

  send({ type: 'START', t: 0, camera: opts.camera })
  for (let t = tickMs; t <= untilMs && state.stage !== 'done'; t += tickMs) {
    if (opts.stopAt?.(t, state)) { send({ type: 'STOP', t }); break }
    if (voiceDoneAt !== null && t >= voiceDoneAt) {
      voiceDoneAt = null
      send({ type: 'VOICE_DONE', t })
    }
    if (opts.camera && opts.eyes) {
      const closed = opts.eyes(t, state)
      if (closed !== lastEyes) { lastEyes = closed; send({ type: 'EYES', t, closed }) }
    }
    send({ type: 'TICK', t })
  }
  return { state, log, sayOverlap }
}

const phases = (log: Log[]) => log.flatMap((l) => (l.effect.type === 'phase' ? [l.effect.phase] : []))
const depths = (log: Log[]) => log.flatMap((l) => (l.effect.type === 'depth' ? [l.effect.value] : []))
const says = (log: Log[]) => log.flatMap((l) => (l.effect.type === 'say' ? [l.effect.text] : []))
const completes = (log: Log[]) => log.filter((l) => l.effect.type === 'complete')

// A cooperative listener: eyes closed while descending/holding/in the final
// rest, open while emerging.
const cooperative = (_t: number, s: FracState) => s.stage !== 'emerge' && s.stage !== 'induce'

describe('useFractionation reducer', () => {
  it('runs a full camera-path session through 3 rounds to complete', () => {
    const { state, log, sayOverlap } = simulate({ camera: true, eyes: cooperative })
    expect(state.stage).toBe('done')
    expect(state.holdsReached).toBe(3)
    expect(completes(log)).toHaveLength(1)
    expect(sayOverlap).toBe(false)

    expect(phases(log)).toEqual([
      'induction',
      'deepen', 'coherence',
      'deepen', 'coherence',
      'deepen',
      'joy', 'wake',
    ])

    const d = depths(log)
    expect(d[0]).toBe(0)
    for (let i = 1; i < d.length; i++) expect(d[i]).toBeGreaterThanOrEqual(d[i - 1])
    expect(d.at(-1)).toBe(1)
    expect(d).toEqual([0, 1 / 3, 2 / 3, 1, 1])

    const s = says(log)
    expect(s.slice(0, FRACTIONATION_SCRIPT.induction.length)).toEqual([...FRACTIONATION_SCRIPT.induction])
    expect(s).toContain(FRACTIONATION_SCRIPT.emerge[0])
    expect(s).toContain(FRACTIONATION_SCRIPT.reinduce[1])
    expect(s.slice(-FRACTIONATION_SCRIPT.wake.length)).toEqual([...FRACTIONATION_SCRIPT.wake])
    // complete is the very last effect
    expect(log.at(-1)!.effect.type).toBe('complete')
  })

  it('camera path descends faster than the timer once eyes stay closed', () => {
    const { log } = simulate({ camera: true, eyes: cooperative })
    const firstHold = log.find((l) => l.effect.type === 'phase' && l.effect.phase === 'deepen')!
    const descendStart = log.find((l) => l.effect.type === 'say' && l.effect.text === FRACTIONATION_SCRIPT.descend)!
    expect(firstHold.t - descendStart.t).toBeLessThan(DEFAULT_CONFIG.descendTimeoutMs)
  })

  it('timer path (no camera) completes', () => {
    const { state, log, sayOverlap } = simulate({ camera: false })
    expect(state.stage).toBe('done')
    expect(state.holdsReached).toBe(3)
    expect(completes(log)).toHaveLength(1)
    expect(sayOverlap).toBe(false)
    // descend waits the full timeout in timer mode
    const descendStart = log.find((l) => l.effect.type === 'say' && l.effect.text === FRACTIONATION_SCRIPT.descend)!
    const firstHold = log.find((l) => l.effect.type === 'phase' && l.effect.phase === 'deepen')!
    expect(firstHold.t - descendStart.t).toBeGreaterThanOrEqual(DEFAULT_CONFIG.descendTimeoutMs)
  })

  it('a blink-like closed/open flicker in descend does not advance', () => {
    let s = initialState()
    const feed = (ev: FracEvent) => { const r = step(s, ev); s = r.state; return r.effects }
    feed({ type: 'START', t: 0, camera: true })
    // finish induction lines
    let t = 0
    while (s.stage === 'induce') { t += 1000; feed({ type: 'VOICE_DONE', t }) }
    expect(s.stage).toBe('descend')
    t += 1000
    feed({ type: 'VOICE_DONE', t }) // descend line done
    const start = t
    // Flicker: closed for 2s, open briefly, repeat — never 3s continuous.
    for (let k = 0; k < 6; k++) {
      t += 100; feed({ type: 'EYES', t, closed: true })
      t += 2000; feed({ type: 'TICK', t })
      t += 100; feed({ type: 'EYES', t, closed: false })
      feed({ type: 'TICK', t })
      expect(s.stage).toBe('descend')
    }
    expect(t - start).toBeLessThan(DEFAULT_CONFIG.descendTimeoutMs)
    // Holding them closed for 3s does advance
    t += 100; feed({ type: 'EYES', t, closed: true })
    t += DEFAULT_CONFIG.descendClosedMs
    const fx = feed({ type: 'TICK', t })
    expect(s.stage).toBe('hold')
    expect(fx).toContainEqual({ type: 'phase', phase: 'deepen' })
  })

  it('emerge proceeds at timeout even with eyes still closed', () => {
    const asleep = () => true
    const { state, log } = simulate({ camera: true, eyes: asleep })
    expect(state.stage).toBe('done')
    const emergeSay = log.find((l) => l.effect.type === 'say' && l.effect.text === FRACTIONATION_SCRIPT.emerge[0])!
    const reinduceSay = log.find((l) => l.effect.type === 'say' && l.effect.text === FRACTIONATION_SCRIPT.reinduce[0])!
    expect(reinduceSay.t - emergeSay.t).toBeGreaterThanOrEqual(DEFAULT_CONFIG.emergeTimeoutMs)
    expect(reinduceSay.t - emergeSay.t).toBeLessThan(DEFAULT_CONFIG.emergeTimeoutMs + 1000)
  })

  it('never emits a say while one is pending', () => {
    let s = initialState()
    let r = step(s, { type: 'START', t: 0, camera: false })
    s = r.state
    expect(r.effects.filter((e) => e.type === 'say')).toHaveLength(1)
    // Lots of time passes with no VOICE_DONE: nothing new is said.
    for (let t = 1000; t < 120_000; t += 1000) {
      r = step(s, { type: 'TICK', t })
      s = r.state
      expect(r.effects).toEqual([])
    }
    expect(s.stage).toBe('induce')
    expect(s.speaking).toBe(true)
  })

  it('STOP before any hold emits no complete', () => {
    const { state, log } = simulate({ camera: false, stopAt: (t) => t >= 5000 })
    expect(state.stage).toBe('done')
    expect(state.holdsReached).toBe(0)
    expect(completes(log)).toHaveLength(0)
    const r = step(state, { type: 'STOP', t: 6000 })
    expect(r.effects).toEqual([])
  })

  it('STOP after a hold emits complete', () => {
    const { state, log } = simulate({ camera: false, stopAt: (_t, s) => s.holdsReached === 1 && s.stage === 'hold' })
    expect(state.stage).toBe('done')
    expect(completes(log)).toHaveLength(1)
    expect(log.at(-1)!.effect).toEqual({ type: 'complete' })
  })

  it('respects a config override for rounds', () => {
    let state = initialState()
    let t = 0
    let pending = false
    const effects: FracEffect[] = []
    const send = (ev: FracEvent) => {
      const r = step(state, ev, { rounds: 1 })
      state = r.state
      for (const e of r.effects) { effects.push(e); if (e.type === 'say') pending = true }
    }
    send({ type: 'START', t, camera: false })
    while (state.stage !== 'done' && t < 600_000) {
      t += 500
      if (pending) { pending = false; send({ type: 'VOICE_DONE', t }) }
      send({ type: 'TICK', t })
    }
    expect(state.stage).toBe('done')
    expect(effects.filter((e) => e.type === 'phase').map((e) => (e as { phase: string }).phase))
      .toEqual(['induction', 'deepen', 'joy', 'wake'])
  })

  it('ignores events before START', () => {
    const s = initialState()
    expect(step(s, { type: 'TICK', t: 10 })).toEqual({ state: s, effects: [] })
    expect(step(s, { type: 'STOP', t: 10 }).effects).toEqual([])
  })
})
