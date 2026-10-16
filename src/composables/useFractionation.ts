// Pure fractionation state machine. No Vue, no timers, no side effects:
// `step(state, event)` returns the next state plus the effects the caller
// should perform (speak a line, switch the engine phase, set depth, finish).
//
// Fractionation: take the listener down, bring them briefly up ("open your
// eyes"), then back down deeper — repeated for `rounds` rounds.

import { FRACTIONATION_SCRIPT, lineForRound } from '@/data/fractionationScript'

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
