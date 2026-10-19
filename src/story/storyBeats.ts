// Story → beat timeline. PURE: no Vue, no DOM, no audio.
//
// A story is plain text split into beats (blank-line paragraphs). Optional
// marker lines steer the trance arc using the fractionation stages:
//
//   [induce] [deepen] [emerge] [reinduce] [final] [wake]   — stage for what follows
//   [pause 6]                                               — silent hold, seconds
//
// `buildTimeline` lays the beats on one clock. The SAME timeline drives the
// offline soundtrack (voice placement + binaural glides) and the text overlay
// (phrase in/out), which is what keeps picture, voice and beat in sync.

import type { Band, MotionType } from '@/composables/studioTypes'
import { BANDS } from '@/composables/useStudioBinaural'
import { chunkPhrases, splitWords, SENTENCE_HOLD, type Phrase } from './phrases'

// ── Stages ───────────────────────────────────────────────────────

export type StoryStage = 'induce' | 'deepen' | 'emerge' | 'reinduce' | 'final' | 'wake'

export interface StageSpec {
  band: Band
  /** Multiplies reading time — deeper stages are paced slower. */
  pace: number
  /** Silence after the beat's words, before the next beat. */
  breathMs: number
  /** Overlay motion; beat-synced motion is clamped by safeVisualHz. */
  motion: MotionType
  /** Overlay opacity — the text recedes as the listener goes down. */
  opacity: number
}

export const STAGES: Record<StoryStage, StageSpec> = {
  induce:   { band: 'alpha', pace: 1.0,  breathMs: 1500, motion: 'drift', opacity: 0.95 },
  deepen:   { band: 'theta', pace: 1.25, breathMs: 3000, motion: 'waver', opacity: 0.8 },
  emerge:   { band: 'alpha', pace: 1.0,  breathMs: 1500, motion: 'drift', opacity: 0.95 },
  reinduce: { band: 'theta', pace: 1.35, breathMs: 3500, motion: 'waver', opacity: 0.75 },
  final:    { band: 'delta', pace: 1.5,  breathMs: 6000, motion: 'pulse', opacity: 0.65 },
  wake:     { band: 'alpha', pace: 1.0,  breathMs: 1500, motion: 'none',  opacity: 1 },
}

const STAGE_NAMES = Object.keys(STAGES) as StoryStage[]

// ── Parsing ──────────────────────────────────────────────────────

export interface StoryBeat {
  stage: StoryStage
  /** Empty for a [pause] beat. */
  text: string
  /** Set only on [pause] beats. */
  pauseMs?: number
}

const STAGE_RE = new RegExp(`^\\[(${STAGE_NAMES.join('|')})\\]$`, 'i')
const PAUSE_RE = /^\[pause\s+(\d+(?:\.\d+)?)\s*s?\]$/i

/**
 * Split a story into beats. Without any stage markers the arc is assigned
 * automatically: the first quarter induces, the last beat wakes, the rest deepen.
 */
export function parseStory(source: string): StoryBeat[] {
  const beats: StoryBeat[] = []
  let stage: StoryStage = 'induce'
  let sawMarker = false
  let para: string[] = []

  const flush = () => {
    const text = para.join(' ').replace(/\s+/g, ' ').trim()
    if (text) beats.push({ stage, text })
    para = []
  }

  for (const raw of source.split(/\r?\n/)) {
    const line = raw.trim()
    const stageHit = STAGE_RE.exec(line)
    const pauseHit = PAUSE_RE.exec(line)
    if (stageHit) {
      flush()
      stage = stageHit[1].toLowerCase() as StoryStage
      sawMarker = true
    } else if (pauseHit) {
      flush()
      beats.push({ stage, text: '', pauseMs: Math.round(parseFloat(pauseHit[1]) * 1000) })
    } else if (!line) {
      flush()
    } else {
      para.push(line)
    }
  }
  flush()

  if (!sawMarker) autoArc(beats)
  return beats
}

function autoArc(beats: StoryBeat[]) {
  const n = beats.length
  const induceCount = Math.max(1, Math.ceil(n * 0.25))
  beats.forEach((b, i) => {
    if (n >= 3 && i === n - 1) b.stage = 'wake'
    else if (i < induceCount) b.stage = 'induce'
    else b.stage = 'deepen'
  })
}

// ── Timeline ─────────────────────────────────────────────────────

export interface TimedPhrase {
  text: string
  startMs: number
  endMs: number
}

export interface TimedBeat extends StoryBeat {
  index: number
  startMs: number
  /** End of words (voice or reading), before the breath. */
  bodyEndMs: number
  endMs: number
  beatHz: number
  carrierHz: number
  /** Voice starts at startMs when the beat has a rendered line. */
  voiced: boolean
  phrases: TimedPhrase[]
}

export interface Timeline {
  durationMs: number
  leadInMs: number
  tailMs: number
  beats: TimedBeat[]
}

export interface TimelineOptions {
  /** Rendered voice length per beat (ms), null where a beat is unvoiced. */
  voiceMs?: (number | null | undefined)[]
  wpm?: number
  /** Binaural-only settle before the first beat. */
  leadInMs?: number
  /** Binaural-only rest after the last beat. */
  tailMs?: number
}

/** Last phrase of a beat lingers this far into the breath. */
const LINGER_MS = 1200
/** Binaural glide between beats; audio ramps and overlay motion share it. */
export const GLIDE_MS = 4000
/** Phrase fade in / out. */
export const PHRASE_FADE_MS = 220

function phraseWeight(p: Phrase): number {
  return Math.max(1, p.text.length) * (p.isPausePoint ? SENTENCE_HOLD : 1)
}

export function buildTimeline(beats: StoryBeat[], opts: TimelineOptions = {}): Timeline {
  const wpm = opts.wpm ?? 150
  const leadInMs = opts.leadInMs ?? 3000
  const tailMs = opts.tailMs ?? 5000
  const msPerWord = 60000 / wpm

  let t = leadInMs
  const timed: TimedBeat[] = beats.map((beat, index) => {
    const spec = STAGES[beat.stage]
    const band = BANDS[spec.band]
    const startMs = t

    if (beat.pauseMs != null) {
      t += beat.pauseMs
      return {
        ...beat, index, startMs, bodyEndMs: t, endMs: t,
        beatHz: band.beatHz, carrierHz: band.carrierHz, voiced: false, phrases: [],
      }
    }

    const phrases = chunkPhrases(splitWords(beat.text))
    const readMs = phrases.reduce((sum, p) => {
      const words = p.endIdx - p.startIdx + 1
      return sum + words * msPerWord * spec.pace * (p.isPausePoint ? SENTENCE_HOLD : 1)
    }, 0)
    const voiceMs = opts.voiceMs?.[index] ?? null
    const voiced = voiceMs != null && voiceMs > 0
    const bodyMs = Math.max(readMs, voiced ? voiceMs! : 0)

    // Spread phrases across the spoken (or read) span, weighted by length, so
    // each phrase is on screen roughly while it is being said.
    const totalWeight = phrases.reduce((s, p) => s + phraseWeight(p), 0)
    let cursor = startMs
    const timedPhrases: TimedPhrase[] = phrases.map((p, i) => {
      const len = (phraseWeight(p) / totalWeight) * bodyMs
      const ph = { text: p.text, startMs: cursor, endMs: cursor + len }
      cursor += len
      if (i === phrases.length - 1) ph.endMs = startMs + bodyMs + Math.min(LINGER_MS, spec.breathMs)
      return ph
    })

    const bodyEndMs = startMs + bodyMs
    t = bodyEndMs + spec.breathMs
    return {
      ...beat, index, startMs, bodyEndMs, endMs: t,
      beatHz: band.beatHz, carrierHz: band.carrierHz, voiced, phrases: timedPhrases,
    }
  })

  return { durationMs: t + tailMs, leadInMs, tailMs, beats: timed }
}

// ── Sampling ─────────────────────────────────────────────────────

export interface TimelineFrame {
  beat: TimedBeat | null
  text: string | null
  /** Phrase envelope × stage opacity. */
  alpha: number
  beatHz: number
  carrierHz: number
}

/** Index of the beat active at tMs (lead-in → first beat, tail → last beat). */
export function beatIndexAt(tl: Timeline, tMs: number): number {
  const bs = tl.beats
  if (!bs.length) return -1
  for (let i = bs.length - 1; i >= 0; i--) if (tMs >= bs[i].startMs) return i
  return 0
}

/**
 * PURE: what the binaural pair is playing at tMs — a linear glide over
 * GLIDE_MS from the previous beat's frequencies. renderSoundtrack schedules
 * exactly these ramps, so overlay motion locks to what is heard.
 */
export function entrainmentAt(tl: Timeline, tMs: number): { beatHz: number; carrierHz: number } {
  if (!tl.beats.length) return { beatHz: BANDS.alpha.beatHz, carrierHz: BANDS.alpha.carrierHz }
  return {
    beatHz: glideAt(tl, tMs, (b) => b.beatHz),
    carrierHz: glideAt(tl, tMs, (b) => b.carrierHz),
  }
}

/**
 * PURE: how far the background dims at tMs (0 = untouched) — the world
 * darkens as the stages deepen, gliding with the binaural beat.
 */
export function depthDimAt(tl: Timeline, tMs: number): number {
  if (!tl.beats.length) return 0
  return glideAt(tl, tMs, (b) => (1 - STAGES[b.stage].opacity) * 0.6)
}

/** Linear glide of `pick` over GLIDE_MS from the previous beat into the current one. */
function glideAt(tl: Timeline, tMs: number, pick: (b: TimedBeat) => number): number {
  const i = beatIndexAt(tl, tMs)
  const cur = tl.beats[i]
  const prev = tl.beats[i - 1]
  if (!prev || tMs < cur.startMs) return pick(cur)
  const k = Math.min(1, (tMs - cur.startMs) / GLIDE_MS)
  return pick(prev) + (pick(cur) - pick(prev)) * k
}

export function frameAt(tl: Timeline, tMs: number): TimelineFrame {
  const { beatHz, carrierHz } = entrainmentAt(tl, tMs)
  const i = beatIndexAt(tl, tMs)
  const beat = i >= 0 && tMs >= tl.beats[i].startMs ? tl.beats[i] : null
  const empty = { beat, text: null, alpha: 0, beatHz, carrierHz }
  if (!beat) return empty

  const ph = beat.phrases.find((p) => tMs >= p.startMs && tMs < p.endMs)
  if (!ph) return empty
  const fade = Math.min(PHRASE_FADE_MS, (ph.endMs - ph.startMs) / 2)
  const env = Math.min(1, (tMs - ph.startMs) / fade, (ph.endMs - tMs) / fade)
  return { beat, text: ph.text, alpha: Math.max(0, env) * STAGES[beat.stage].opacity, beatHz, carrierHz }
}

/** "m:ss" for beat lists. */
export function formatClock(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
