// Trance sound design. PURE: no Vue, no DOM, no audio.
//
// The soundtrack is rendered as stems (renderSoundtrack) and mixed live
// (mixer). This module owns the decisions that make it a trance rather than
// a playlist, each from one of three chairs:
//
//   director  — sound follows the same beat timeline as the picture; the mix
//               moves per stage and per beat, and is drawn on the timeline.
//   musician  — one key, consonant chords, smooth envelopes, headroom; the
//               beds dip under the voice; nothing sharp or fatiguing.
//   hypnotist — pacing and leading: a heartbeat that starts near resting
//               rate and slows with the listener; the same bowl on every
//               deepening, so it becomes an anchor; a rising shimmer on
//               emerge and wake; the voice moves closer (drier) as trance
//               deepens; comfort before effect.

import { GLIDE_MS, type StoryStage, type Timeline } from './storyBeats'

// ── Stems ────────────────────────────────────────────────────────

export type StemId = 'voice' | 'music' | 'waves' | 'binaural' | 'heart' | 'cues'

export const STEMS: { id: StemId; label: string; hint: string }[] = [
  { id: 'voice', label: 'Voice', hint: 'The narrator' },
  { id: 'music', label: 'Music', hint: 'Warm pad that changes chord with the stages' },
  { id: 'waves', label: 'Waves', hint: 'Slow ocean of soft noise' },
  { id: 'binaural', label: 'Entrainment', hint: 'Binaural / isochronic beat — barely heard works best' },
  { id: 'heart', label: 'Heartbeat', hint: 'Starts near resting pace and slows with the listener' },
  { id: 'cues', label: 'Bowls & rises', hint: 'A bowl on each deepening (an anchor), a shimmer rising into emerge and wake' },
]

export const STEM_IDS = STEMS.map((s) => s.id)

/** The beds a beat can re-balance (the voice stays where the director put it). */
export type BedStem = Exclude<StemId, 'voice'>
export const BED_STEMS: BedStem[] = ['music', 'waves', 'binaural', 'heart', 'cues']

export type Levels = Record<StemId, number>

export interface MixState {
  /** 0–1 per stem. */
  faders: Levels
  muted: Record<StemId, boolean>
  solo: StemId | null
}

export const DEFAULT_FADERS: Levels = { voice: 1, music: 0.55, waves: 0.4, binaural: 0.3, heart: 0.25, cues: 0.5 }

export function defaultMix(): MixState {
  return {
    faders: { ...DEFAULT_FADERS },
    muted: Object.fromEntries(STEM_IDS.map((id) => [id, false])) as Record<StemId, boolean>,
    solo: null,
  }
}

// ── Sound design (baked into the stems: changing it needs a rebuild) ──

export type Entrainment = 'binaural' | 'isochronic' | 'both'

export interface SoundDesign {
  /** Semitones from D major. */
  key: number
  /** Pad brightness 0–1 (low-pass from dark to open). */
  warmth: number
  /** Binaural needs headphones; isochronic is a soft pulse heard on speakers. */
  entrainment: Entrainment
  /** Voice room 0–1. The voice still moves closer as the stages deepen. */
  room: number
  /** Comfort: caps entrainment level and pulse depth, softens everything sharp. */
  comfort: boolean
}

export const DEFAULT_DESIGN: SoundDesign = { key: 0, warmth: 0.45, entrainment: 'binaural', room: 0.5, comfort: true }

export const KEYS: { semis: number; label: string }[] = [
  { semis: -5, label: 'A' }, { semis: -4, label: 'B♭' }, { semis: -3, label: 'B' }, { semis: -2, label: 'C' },
  { semis: -1, label: 'D♭' }, { semis: 0, label: 'D' }, { semis: 1, label: 'E♭' }, { semis: 2, label: 'E' },
  { semis: 3, label: 'F' }, { semis: 4, label: 'G♭' }, { semis: 5, label: 'G' },
]

/** Pad low-pass cutoff for a warmth setting, Hz. */
export function padCutoffHz(warmth: number): number {
  return 700 * Math.pow(2400 / 700, Math.max(0, Math.min(1, warmth)))
}

// ── Comfort ──────────────────────────────────────────────────────

/** Entrainment fader ceiling in comfort mode. */
export const COMFORT_ENTRAINMENT_MAX = 0.5
/** Isochronic AM depth: a gentle sine swell, never a hard pulse. */
export const PULSE_DEPTH = { comfort: 0.3, full: 0.6 }

/** Gain a stem actually gets from the mixer (mute, solo, comfort cap). */
export function stemGain(mix: MixState, id: StemId, comfort: boolean): number {
  if (mix.muted[id]) return 0
  if (mix.solo && mix.solo !== id) return 0
  const f = Math.max(0, Math.min(1, mix.faders[id]))
  return id === 'binaural' && comfort ? Math.min(f, COMFORT_ENTRAINMENT_MAX) : f
}

// ── Stage mix (the arc) ──────────────────────────────────────────

/**
 * Multipliers on each bed per stage. Going down, the room fills with waves and
 * heartbeat and the music softens; on emerge and wake the music brightens and
 * the body sounds recede.
 */
export const STAGE_MIX: Record<StoryStage, Record<BedStem, number>> = {
  induce:   { music: 1,    waves: 0.9, binaural: 0.9, heart: 0.8, cues: 1 },
  deepen:   { music: 0.9,  waves: 1.1, binaural: 1,   heart: 1,   cues: 1 },
  emerge:   { music: 1.1,  waves: 0.8, binaural: 0.7, heart: 0.6, cues: 1 },
  reinduce: { music: 0.85, waves: 1.15, binaural: 1.05, heart: 1.1, cues: 1 },
  final:    { music: 0.75, waves: 1.25, binaural: 1.1, heart: 1.2, cues: 1 },
  wake:     { music: 1.15, waves: 0.7, binaural: 0.4, heart: 0.4, cues: 1 },
}

/** Voice reverb send per stage — closer and drier as trance deepens. */
export const STAGE_ROOM: Record<StoryStage, number> = {
  induce: 1, deepen: 0.75, emerge: 1, reinduce: 0.65, final: 0.5, wake: 1,
}

/** A beat's own re-balance, 0–1.5 per bed; unset carries the previous beat's on. */
export type BeatSound = Partial<Record<BedStem, number>>

/** Sticky per-beat sound, resolved to a full multiplier set per beat. */
export function resolveBeatSound(sounds: (BeatSound | undefined)[], count: number): Record<BedStem, number>[] {
  let cur: Record<BedStem, number> = { music: 1, waves: 1, binaural: 1, heart: 1, cues: 1 }
  const out: Record<BedStem, number>[] = []
  for (let i = 0; i < count; i++) {
    cur = { ...cur, ...sounds[i] }
    out.push(cur)
  }
  return out
}

// ── Automation ───────────────────────────────────────────────────

export interface AutoPoint { tMs: number; v: number }
export type Automation = Record<StemId, AutoPoint[]>

/**
 * Piecewise-linear level curve per stem: at each beat start the level glides
 * (over GLIDE_MS, or until the next beat if sooner) from the previous beat's
 * stage × beat multiplier to this one's. Voice stays at 1.
 */
export function buildAutomation(tl: Timeline, beatSound: Record<BedStem, number>[]): Automation {
  const auto = Object.fromEntries(STEM_IDS.map((id) => [id, [] as AutoPoint[]])) as Automation
  auto.voice.push({ tMs: 0, v: 1 })
  const level = (i: number, id: BedStem) => STAGE_MIX[tl.beats[i].stage][id] * (beatSound[i]?.[id] ?? 1)
  for (const id of BED_STEMS) {
    const pts = auto[id]
    if (!tl.beats.length) { pts.push({ tMs: 0, v: 1 }); continue }
    pts.push({ tMs: 0, v: level(0, id) })
    for (let i = 1; i < tl.beats.length; i++) {
      const start = tl.beats[i].startMs
      const end = Math.min(start + GLIDE_MS, tl.beats[i + 1]?.startMs ?? Infinity)
      pts.push({ tMs: start, v: pts[pts.length - 1].v }, { tMs: end, v: level(i, id) })
    }
  }
  return auto
}

/** Value of a level curve at tMs (held flat outside its points). */
export function autoValueAt(pts: AutoPoint[], tMs: number): number {
  if (!pts.length) return 1
  if (tMs <= pts[0].tMs) return pts[0].v
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i]
    if (tMs <= b.tMs) return b.tMs === a.tMs ? b.v : a.v + (b.v - a.v) * ((tMs - a.tMs) / (b.tMs - a.tMs))
  }
  return pts[pts.length - 1].v
}

// ── Heartbeat: pacing and leading ────────────────────────────────

/** Beats per minute per stage — near resting at the start, slower going down. */
export const HEART_BPM: Record<StoryStage, number> = {
  induce: 64, deepen: 58, emerge: 62, reinduce: 55, final: 50, wake: 66,
}

/** Delay of the softer second sound ("dub") after the first. */
export const HEART_DUB_MS = 300

/**
 * When each heartbeat lands, ms. Tempo glides between stages like the
 * binaural beat; the pulse starts once the first beat begins and stops
 * before the tail, so the opening and closing are heart-free.
 */
export function heartbeatTimes(tl: Timeline): number[] {
  if (!tl.beats.length) return []
  const end = tl.durationMs - tl.tailMs
  const out: number[] = []
  let t = tl.beats[0].startMs
  while (t < end) {
    out.push(t)
    t += 60000 / bpmAt(tl, t)
  }
  return out
}

function bpmAt(tl: Timeline, tMs: number): number {
  let i = tl.beats.length - 1
  while (i > 0 && tl.beats[i].startMs > tMs) i--
  const cur = HEART_BPM[tl.beats[i].stage]
  const prev = i > 0 ? HEART_BPM[tl.beats[i - 1].stage] : cur
  const k = Math.min(1, Math.max(0, (tMs - tl.beats[i].startMs) / GLIDE_MS))
  return prev + (cur - prev) * k
}

// ── Cues: the anchor and the lift ────────────────────────────────

export interface Cue {
  kind: 'bowl' | 'rise'
  /** Bowl: the strike. Rise: where it peaks (the stage change). */
  atMs: number
}

/** A rise starts this long before the stage it lifts into. */
export const RISE_MS = 3500

/**
 * A bowl on the first beat and on every stage change that goes down (the
 * same strike each time, so it becomes an anchor); a rise into every stage
 * change that comes up.
 */
export function cueEvents(tl: Timeline): Cue[] {
  const out: Cue[] = []
  const down = new Set<StoryStage>(['induce', 'deepen', 'reinduce', 'final'])
  tl.beats.forEach((b, i) => {
    const prev = tl.beats[i - 1]
    if (prev && prev.stage === b.stage) return
    if (down.has(b.stage)) out.push({ kind: 'bowl', atMs: b.startMs })
    else if (prev) out.push({ kind: 'rise', atMs: b.startMs })
  })
  return out
}

/** Singing-bowl partial ratios (inharmonic) and their decay times, s. */
export const BOWL_PARTIALS: [number, number, number][] = [
  // ratio, level, decay
  [1, 1, 9], [2.71, 0.45, 6], [5.15, 0.2, 4], [8.43, 0.08, 2.5],
]

// ── Presets ──────────────────────────────────────────────────────

export interface MixPreset {
  name: string
  faders: Levels
  design: SoundDesign
}

export const MIX_PRESETS: MixPreset[] = [
  { name: 'Balanced', faders: { ...DEFAULT_FADERS }, design: { ...DEFAULT_DESIGN } },
  { name: 'Ocean drift', faders: { voice: 1, music: 0.35, waves: 0.7, binaural: 0.3, heart: 0.15, cues: 0.4 }, design: { ...DEFAULT_DESIGN, warmth: 0.3, room: 0.6 } },
  { name: 'Deep rest', faders: { voice: 0.9, music: 0.45, waves: 0.5, binaural: 0.4, heart: 0.45, cues: 0.55 }, design: { ...DEFAULT_DESIGN, key: -3, warmth: 0.25, room: 0.4 } },
  { name: 'Clear voice', faders: { voice: 1, music: 0.3, waves: 0.2, binaural: 0.2, heart: 0.1, cues: 0.35 }, design: { ...DEFAULT_DESIGN, room: 0.3 } },
  { name: 'Speakers', faders: { voice: 1, music: 0.5, waves: 0.35, binaural: 0.35, heart: 0.2, cues: 0.5 }, design: { ...DEFAULT_DESIGN, entrainment: 'isochronic' } },
]
