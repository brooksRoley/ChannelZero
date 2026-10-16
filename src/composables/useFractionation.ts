// Pure fractionation state machine. No Vue, no timers, no side effects:
// `step(state, event)` returns the next state plus the effects the caller
// should perform (speak a line, switch the engine phase, set depth, finish).
//
// The Vue runner `useFractionationSession()` at the bottom drives it.
//
// Fractionation: take the listener down, bring them briefly up ("open your
// eyes"), then back down deeper — repeated for `rounds` rounds.

import { shallowRef, computed, watch, getCurrentScope, onScopeDispose } from 'vue'
import { FRACTIONATION_SCRIPT, lineForRound } from '@/data/fractionationScript'
// Used only by the Vue runner at the bottom; the reducer never touches them.
import { useEyeState } from './useEyeState'
import { useVoice } from './useVoice'
import { useTranceEngine } from './useTranceEngine'

export type FracStage = 'idle' | 'induce' | 'descend' | 'hold' | 'emerge' | 'reinduce' | 'final' | 'done'

export type FracEvent =
  | { type: 'START'; t: number; camera: boolean }
  | { type: 'TICK'; t: number }
  | { type: 'EYES'; t: number; closed: boolean }
  | { type: 'VOICE_DONE'; t: number }
  | { type: 'STOP'; t: number }

export type EnginePhase = 'induction' | 'coherence' | 'deepen' | 'joy' | 'wake'

export type FracEffect =
  | { type: 'say'; text: string }
  | { type: 'phase'; phase: EnginePhase }
  | { type: 'depth'; value: number }
  | { type: 'complete' }

export interface FracConfig {
  rounds: number
  descendClosedMs: number
  descendTimeoutMs: number
  holdBaseMs: number
  holdPerRoundMs: number
  emergeOpenMs: number
  emergeTimeoutMs: number
  finalHoldMs: number
}

export const DEFAULT_CONFIG: FracConfig = {
  rounds: 3,
  descendClosedMs: 3000,
  descendTimeoutMs: 20000,
  holdBaseMs: 20000,
  holdPerRoundMs: 10000,
  emergeOpenMs: 1500,
  emergeTimeoutMs: 12000,
  finalHoldMs: 45000,
}

export interface FracState {
  stage: FracStage
  round: number           // 1-based
  stageStartedAt: number
  camera: boolean
  eyesClosed: boolean
  eyesChangedAt: number
  speaking: boolean       // a 'say' is pending its VOICE_DONE
  lineIndex: number       // index within a multi-line block (induction / wake)
  holdsReached: number
  waking: boolean         // in 'final': true once the wake count has begun
}

export function initialState(): FracState {
  return {
    stage: 'idle',
    round: 1,
    stageStartedAt: 0,
    camera: false,
    eyesClosed: false,
    eyesChangedAt: 0,
    speaking: false,
    lineIndex: 0,
    holdsReached: 0,
    waking: false,
  }
}

type Result = { state: FracState; effects: FracEffect[] }

const S = FRACTIONATION_SCRIPT

function say(s: FracState, text: string, effects: FracEffect[]): FracState {
  effects.push({ type: 'say', text })
  return { ...s, speaking: true }
}

function enter(s: FracState, stage: FracStage, t: number): FracState {
  return { ...s, stage, stageStartedAt: t, lineIndex: 0 }
}

function holdMs(s: FracState, c: FracConfig): number {
  return c.holdBaseMs + c.holdPerRoundMs * (s.round - 1)
}

/** How long the eyes have been in their current state, counted within this stage. */
function eyesHeldFor(s: FracState, t: number): number {
  return t - Math.max(s.eyesChangedAt, s.stageStartedAt)
}

function enterDescend(s: FracState, t: number, effects: FracEffect[], speakLine: boolean): FracState {
  const next = enter(s, 'descend', t)
  return speakLine ? say(next, S.descend, effects) : next
}

function enterHold(s: FracState, t: number, c: FracConfig, effects: FracEffect[]): FracState {
  const next = { ...enter(s, 'hold', t), holdsReached: s.holdsReached + 1 }
  effects.push({ type: 'phase', phase: 'deepen' })
  effects.push({ type: 'depth', value: Math.min(1, s.round / c.rounds) })
  return say(next, lineForRound(S.deepen, s.round), effects)
}

function enterEmerge(s: FracState, t: number, effects: FracEffect[]): FracState {
  effects.push({ type: 'phase', phase: 'coherence' })
  return say(enter(s, 'emerge', t), lineForRound(S.emerge, s.round), effects)
}

function enterReinduce(s: FracState, t: number, effects: FracEffect[]): FracState {
  return say(enter(s, 'reinduce', t), lineForRound(S.reinduce, s.round), effects)
}

function enterFinal(s: FracState, t: number, effects: FracEffect[]): FracState {
  effects.push({ type: 'phase', phase: 'joy' })
  effects.push({ type: 'depth', value: 1 })
  return say({ ...enter(s, 'final', t), waking: false }, S.final, effects)
}

/** Time/eye-driven transitions. Only called when no line is pending. */
function advance(s: FracState, t: number, c: FracConfig, effects: FracEffect[]): FracState {
  const elapsed = t - s.stageStartedAt
  switch (s.stage) {
    case 'descend': {
      const settled = s.camera && s.eyesClosed && eyesHeldFor(s, t) >= c.descendClosedMs
      if (settled || elapsed >= c.descendTimeoutMs) return enterHold(s, t, c, effects)
      return s
    }
    case 'hold':
      if (elapsed < holdMs(s, c)) return s
      return s.round < c.rounds ? enterEmerge(s, t, effects) : enterFinal(s, t, effects)
    case 'emerge': {
      // Never wait on the eyes forever: they may simply be asleep.
      const opened = s.camera && !s.eyesClosed && eyesHeldFor(s, t) >= c.emergeOpenMs
      if (opened || elapsed >= c.emergeTimeoutMs) return enterReinduce(s, t, effects)
      return s
    }
    case 'final':
      if (!s.waking && elapsed >= c.finalHoldMs) {
        effects.push({ type: 'phase', phase: 'wake' })
        return say({ ...s, waking: true, lineIndex: 0 }, S.wake[0], effects)
      }
      return s
    default:
      return s
  }
}

/** Handle the end of the current line for stages that chain lines. */
function onVoiceDone(s: FracState, t: number, c: FracConfig, effects: FracEffect[]): FracState {
  const quiet = { ...s, speaking: false }
  switch (s.stage) {
    case 'induce': {
      const i = s.lineIndex + 1
      if (i < S.induction.length) return say({ ...quiet, lineIndex: i }, S.induction[i], effects)
      return enterDescend(quiet, t, effects, true)
    }
    case 'reinduce':
      // The reinduce line already asked for the eyes to close — no extra line.
      return enterDescend({ ...quiet, round: s.round + 1 }, t, effects, false)
    case 'final':
      if (s.waking) {
        const i = s.lineIndex + 1
        if (i < S.wake.length) return say({ ...quiet, lineIndex: i }, S.wake[i], effects)
        effects.push({ type: 'complete' })
        return { ...enter(quiet, 'done', t), waking: false }
      }
      return advance(quiet, t, c, effects)
    default:
      return advance(quiet, t, c, effects)
  }
}

export function step(state: FracState, event: FracEvent, config: Partial<FracConfig> = {}): Result {
  const c: FracConfig = { ...DEFAULT_CONFIG, ...config }
  const effects: FracEffect[] = []

  if (event.type === 'STOP') {
    if (state.stage === 'idle' || state.stage === 'done') return { state, effects }
    if (state.holdsReached > 0) effects.push({ type: 'complete' })
    return { state: { ...enter(state, 'done', event.t), speaking: false }, effects }
  }

  if (state.stage === 'done') return { state, effects }

  if (event.type === 'START') {
    if (state.stage !== 'idle') return { state, effects }
    let s: FracState = { ...initialState(), camera: event.camera, eyesChangedAt: event.t }
    s = enter(s, 'induce', event.t)
    effects.push({ type: 'phase', phase: 'induction' })
    effects.push({ type: 'depth', value: 0 })
    s = say(s, S.induction[0], effects)
    return { state: s, effects }
  }

  if (state.stage === 'idle') return { state, effects }

  let s = state
  if (event.type === 'EYES') {
    if (event.closed !== s.eyesClosed) s = { ...s, eyesClosed: event.closed, eyesChangedAt: event.t }
  }

  if (event.type === 'VOICE_DONE') {
    if (!s.speaking) return { state: s, effects }
    return { state: onVoiceDone(s, event.t, c, effects), effects }
  }

  // TICK or EYES: time-based transitions wait for the current line to finish.
  if (!s.speaking) s = advance(s, event.t, c, effects)
  return { state: s, effects }
}

// ── Vue runner ─────────────────────────────────────────────────────
// Everything below wires the pure reducer above to the real world: a 250 ms
// clock, the (opt-in) eye sensor, the voice and the trance engine. The
// reducer itself stays free of Vue and side effects.

export const TICK_MS = 250

export function useFractionationSession(config: Partial<FracConfig> = {}) {
  const eye = useEyeState()
  const voice = useVoice()
  const engine = useTranceEngine()
  const cfg: FracConfig = { ...DEFAULT_CONFIG, ...config }

  const state = shallowRef<FracState>(initialState())
  let timer: ReturnType<typeof setInterval> | null = null
  let unsubscribeEyes: (() => void) | null = null
  /** Bumped per spoken line and on stop, so a stale say() can't advance the machine. */
  let lineToken = 0

  const running = computed(() => state.value.stage !== 'idle' && state.value.stage !== 'done')

  const now = () => Date.now()

  function dispatch(event: FracEvent) {
    const r = step(state.value, event, cfg)
    state.value = r.state
    for (const effect of r.effects) execute(effect)
    if (state.value.stage === 'done') teardown()
  }

  function execute(effect: FracEffect) {
    switch (effect.type) {
      case 'say': {
        const token = ++lineToken
        void voice.say(effect.text).then(() => {
          if (token === lineToken && running.value) dispatch({ type: 'VOICE_DONE', t: now() })
        })
        break
      }
      case 'phase':
        engine.enterPhase(effect.phase)
        break
      case 'depth':
        engine.setDepth(effect.value)
        break
      case 'complete':
        lineToken++
        void engine.finishSession()
        eye.stop()
        voice.cancel()
        break
    }
  }

  function teardown() {
    if (timer !== null) clearInterval(timer)
    timer = null
    unsubscribeEyes?.()
    unsubscribeEyes = null
  }

  function sendEyes(closed: boolean) {
    // 'no-face' keeps the last reading, so only a live track counts.
    if (!running.value || eye.status.value !== 'tracking') return
    dispatch({ type: 'EYES', t: now(), closed })
  }

  async function start(opts: { camera: boolean }) {
    if (running.value) return
    teardown()
    state.value = initialState()
    await engine.startSession({ autoAdvance: false, phrases: false })
    if (opts.camera) unsubscribeEyes = eye.onChange(sendEyes)
    dispatch({ type: 'START', t: now(), camera: opts.camera })
    timer = setInterval(() => dispatch({ type: 'TICK', t: now() }), TICK_MS)
  }

  function stop() {
    const wasRunning = running.value
    dispatch({ type: 'STOP', t: now() })
    lineToken++
    teardown()
    if (wasRunning && engine.sessionActive.value) engine.stopSession()
    eye.stop()
    voice.cancel()
  }

  // Tracking resumed (e.g. the face came back): resync the current reading.
  watch(eye.status, (s) => {
    if (s === 'tracking' && unsubscribeEyes) sendEyes(eye.eyesClosed.value)
  })

  // Something else ended the engine (e.g. the nav panel's End): end with it.
  watch(engine.sessionActive, (active) => {
    if (!active && running.value) stop()
  })

  // Leaving the page always releases the camera and the voice.
  if (getCurrentScope()) onScopeDispose(stop)

  return {
    start,
    stop,
    stage: computed(() => state.value.stage),
    round: computed(() => state.value.round),
    rounds: computed(() => cfg.rounds),
    running,
    camera: computed(() => state.value.camera),
  }
}
