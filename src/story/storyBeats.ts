// Story → beat timeline. PURE: no Vue, no DOM, no audio.
//
// A story is plain text split into beats (blank-line paragraphs). Optional
// marker lines steer the trance arc using the fractionation stages:
//
//   [induce] [deepen] [emerge] [reinduce] [final] [wake]   — stage for what follows
//   [pause 6]                                               — silent hold, seconds
//   [subliminal calm, safe, deeper]                         — subliminal pool from here on ([subliminal off] clears)
//
// Inside a beat, *key phrase* puts that phrase on screen as it is spoken, with
// an attention effect rotated per stage; *flash:let go* picks the effect.
//
// `buildTimeline` lays the beats on one clock. The SAME timeline drives the
// offline soundtrack (voice placement + binaural glides) and the text overlay
// (phrase in/out), which is what keeps picture, voice and beat in sync.

import type { Band, MotionType } from '@/composables/studioTypes'
import { BANDS } from '@/composables/useStudioBinaural'
import { chunkPhrases, splitWords, SENTENCE_HOLD, type Phrase } from './phrases'
import { EFFECTS, STAGE_EFFECTS, GENTLE_EFFECT, keyWindow, guardFlashes, settleKeys, scheduleSubliminals, type Effect, type Look, type SubliminalFlash } from './effects'

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
  // Theta, not delta: a 2 Hz throb reads as pressure, not rest.
  final:    { band: 'theta', pace: 1.5,  breathMs: 6000, motion: 'pulse', opacity: 0.65 },
  wake:     { band: 'alpha', pace: 1.0,  breathMs: 1500, motion: 'none',  opacity: 1 },
}

const STAGE_NAMES = Object.keys(STAGES) as StoryStage[]

// ── Parsing ──────────────────────────────────────────────────────

export interface KeyMark {
  text: string
  /** Explicit effect; otherwise rotated from the stage's set at build time. */
  effect?: Effect
  /** Offsets into the beat's spoken text. */
  charStart: number
  charEnd: number
}

export interface StoryBeat {
  stage: StoryStage
  /** Spoken text, markup removed. Empty for a [pause] beat. */
  text: string
  /** Stable id from the spoken text — names the beat's voice file in a pack. */
  id: string
  keys: KeyMark[]
  /** Subliminal pool in effect for this beat. */
  subliminal: string[]
  /** Set only on [pause] beats. */
  pauseMs?: number
}

const STAGE_RE = new RegExp(`^\\[(${STAGE_NAMES.join('|')})\\]$`, 'i')
const PAUSE_RE = /^\[pause\s+(\d+(?:\.\d+)?)\s*s?\]$/i
const SUBLIMINAL_RE = /^\[subliminal\b\s*(.*)\]$/i
const KEY_RE = new RegExp(`\\*(?:(${Object.keys(EFFECTS).join('|')}):)?([^*]+)\\*`, 'gi')

/** FNV-1a — a short stable id for a line of text. */
export function textId(text: string): string {
  let h = 0x811c9dc5
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return 'b' + (h >>> 0).toString(16).padStart(8, '0')
}

/** Strip *key* markup from a paragraph, recording each key's place in the clean text. */
export function extractKeys(marked: string): { text: string; keys: KeyMark[] } {
  const keys: KeyMark[] = []
  let text = ''
  let last = 0
  for (const m of marked.matchAll(KEY_RE)) {
    text += marked.slice(last, m.index)
    const phrase = m[2].trim()
    if (phrase) {
      keys.push({
        text: phrase,
        effect: m[1] ? (m[1].toLowerCase() as Effect) : undefined,
        charStart: text.length,
        charEnd: text.length + phrase.length,
      })
    }
    text += phrase
    last = m.index! + m[0].length
  }
  text += marked.slice(last)
  return { text, keys }
}

/**
 * Split a story into beats. Without any stage markers the arc is assigned
 * automatically: the first quarter induces, the last beat wakes, the rest deepen.
 */
export function parseStory(source: string): StoryBeat[] {
  const beats: StoryBeat[] = []
  let stage: StoryStage = 'induce'
  let subliminal: string[] = []
  let sawMarker = false
  let para: string[] = []

  const flush = () => {
    const marked = para.join(' ').replace(/\s+/g, ' ').trim()
    para = []
    if (!marked) return
    const { text, keys } = extractKeys(marked)
    beats.push({ stage, text, id: textId(text), keys, subliminal })
  }

  for (const raw of source.split(/\r?\n/)) {
    const line = raw.trim()
    const stageHit = STAGE_RE.exec(line)
    const pauseHit = PAUSE_RE.exec(line)
    const subHit = SUBLIMINAL_RE.exec(line)
    if (stageHit) {
      flush()
      stage = stageHit[1].toLowerCase() as StoryStage
      sawMarker = true
    } else if (pauseHit) {
      flush()
      beats.push({
        stage, text: '', id: '', keys: [], subliminal,
        pauseMs: Math.round(parseFloat(pauseHit[1]) * 1000),
      })
    } else if (subHit) {
      flush()
      const words = subHit[1].split(',').map((w) => w.trim()).filter(Boolean)
      subliminal = words.length === 1 && words[0].toLowerCase() === 'off' ? [] : words
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

/** A reading line: one sentence (long ones split), with per-word timing. */
export interface TimedLine {
  text: string
  startMs: number
  endMs: number
  words: { text: string; startMs: number }[]
  /** Key-phrase character ranges within `text`, for highlighting. */
  keySpans: [number, number][]
  /** Index of the beat it belongs to. */
  beat: number
}

export interface TimedKey {
  text: string
  effect: Effect
  /** When the phrase is spoken. */
  spokenStartMs: number
  spokenEndMs: number
  /** When it is on screen (effect lead-in / hold included). */
  startMs: number
  endMs: number
  /** End of a flash strobe (== startMs for other effects). */
  strobeEndMs: number
  /** Per-key seed for deterministic placement / jitter. */
  seed: number
  /** Index of the beat it belongs to. */
  beat: number
}

/** ElevenLabs `/with-timestamps` alignment for one beat. */
export interface Alignment {
  characters: string[]
  character_start_times_seconds: number[]
  character_end_times_seconds: number[]
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
  /** True when key/caption timing comes from real character timestamps. */
  aligned: boolean
  phrases: TimedPhrase[]
  lines: TimedLine[]
}

export interface Timeline {
  durationMs: number
  leadInMs: number
  tailMs: number
  beats: TimedBeat[]
  keys: TimedKey[]
  subliminals: SubliminalFlash[]
  look: Look
}

export interface TimelineOptions {
  /** Rendered voice length per beat (ms), null where a beat is unvoiced. */
  voiceMs?: (number | null | undefined)[]
  /** Character timestamps per beat (ElevenLabs packs), null where unknown. */
  alignments?: (Alignment | null | undefined)[]
  wpm?: number
  /** Binaural-only settle before the first beat. */
  leadInMs?: number
  /** Binaural-only rest after the last beat. */
  tailMs?: number
  /** 'gentle' (default): reading line + soft key phrases, one at a time. 'bold': the full effect set. */
  look?: Look
  /** Per-beat effect for keys without an explicit one (beat editor). */
  effects?: (Effect | undefined)[]
  /** Per-beat extra silence after the beat, ms (beat editor). */
  holdMs?: (number | undefined)[]
}

/** Split a long sentence into lines at a phrase boundary past this many words. */
const LINE_MAX_WORDS = 12

/** Last phrase of a beat lingers this far into the breath. */
const LINGER_MS = 1200
/** Binaural glide between beats; audio ramps and overlay motion share it. */
export const GLIDE_MS = 4000
/** Phrase fade in / out. */
export const PHRASE_FADE_MS = 220

function phraseWeight(p: Phrase): number {
  return Math.max(1, p.text.length) * (p.isPausePoint ? SENTENCE_HOLD : 1)
}

/** Alignment usable only if it spells exactly the beat's spoken text. */
function matchesText(al: Alignment | null | undefined, text: string): al is Alignment {
  return !!al && al.characters.length === text.length && al.characters.join('') === text
}

/**
 * Per-beat clock: ms offset (from beat start) at which character `i` is spoken.
 * Exact with an alignment; otherwise interpolated through the phrase spans.
 */
function charClock(
  text: string,
  phrases: Phrase[],
  spans: { startMs: number; endMs: number }[],
  al: Alignment | null,
): (i: number, edge?: 'start' | 'end') => number {
  if (al) {
    return (i, edge = 'start') => {
      const k = Math.max(0, Math.min(text.length - 1, i))
      return (edge === 'end' ? al.character_end_times_seconds[k] : al.character_start_times_seconds[k]) * 1000
    }
  }
  // Char offset of each phrase in the text (phrases are word runs joined by one space).
  const starts: number[] = []
  let c = 0
  for (const p of phrases) {
    starts.push(c)
    c += p.text.length + 1
  }
  return (i) => {
    let j = starts.length - 1
    while (j > 0 && starts[j] > i) j--
    const span = spans[j]
    if (!span) return 0
    const k = Math.min(1, Math.max(0, (i - starts[j]) / Math.max(1, phrases[j].text.length)))
    return span.startMs + (span.endMs - span.startMs) * k
  }
}

export function buildTimeline(beats: StoryBeat[], opts: TimelineOptions = {}): Timeline {
  const wpm = opts.wpm ?? 150
  const leadInMs = opts.leadInMs ?? 3000
  const tailMs = opts.tailMs ?? 5000
  const msPerWord = 60000 / wpm
  const look = opts.look ?? 'gentle'

  let t = leadInMs
  let keyCount = 0
  const keys: TimedKey[] = []
  const timed: TimedBeat[] = beats.map((beat, index) => {
    const spec = STAGES[beat.stage]
    const band = BANDS[spec.band]
    const startMs = t
    const holdMs = Math.max(0, opts.holdMs?.[index] ?? 0)

    if (beat.pauseMs != null) {
      t += beat.pauseMs + holdMs
      return {
        ...beat, index, startMs, bodyEndMs: t, endMs: t,
        beatHz: band.beatHz, carrierHz: band.carrierHz, voiced: false, aligned: false, phrases: [], lines: [],
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
    const rawAl = opts.alignments?.[index]
    const al = voiced && matchesText(rawAl, beat.text) ? rawAl : null

    // Without timestamps, spread phrases across the spoken (or read) span,
    // weighted by length, so each is on screen roughly while it is said.
    const totalWeight = phrases.reduce((s, p) => s + phraseWeight(p), 0)
    let cursor = 0
    const spans = phrases.map((p) => {
      const len = (phraseWeight(p) / totalWeight) * bodyMs
      const span = { startMs: cursor, endMs: cursor + len }
      cursor += len
      return span
    })
    const at = charClock(beat.text, phrases, spans, al)

    let charPos = 0
    const timedPhrases: TimedPhrase[] = phrases.map((p, i) => {
      const ph = { text: p.text, startMs: startMs + at(charPos), endMs: 0 }
      charPos += p.text.length + 1
      ph.endMs = i === phrases.length - 1
        ? startMs + bodyMs + Math.min(LINGER_MS, spec.breathMs)
        : startMs + at(charPos)
      return ph
    })

    // Reading lines: whole sentences, split at a phrase boundary when long.
    const lines: TimedLine[] = []
    let lineStart = 0
    let lineWords = 0
    charPos = 0
    phrases.forEach((p, i) => {
      lineWords += p.endIdx - p.startIdx + 1
      charPos += p.text.length + 1
      const last = i === phrases.length - 1
      if (!(p.isPausePoint || lineWords >= LINE_MAX_WORDS || last)) return
      const end = charPos - 1
      const text = beat.text.slice(lineStart, end)
      const words: TimedLine['words'] = []
      let w = lineStart
      for (const word of text.split(' ')) {
        words.push({ text: word, startMs: startMs + at(w) })
        w += word.length + 1
      }
      lines.push({
        text,
        startMs: startMs + at(lineStart),
        endMs: last ? startMs + bodyMs + Math.min(LINGER_MS, spec.breathMs) : startMs + at(end + 1),
        words,
        beat: index,
        keySpans: beat.keys
          .filter((k) => k.charStart >= lineStart && k.charEnd <= end)
          .map((k) => [k.charStart - lineStart, k.charEnd - lineStart]),
      })
      lineStart = end + 1
      lineWords = 0
    })

    for (const k of beat.keys) {
      const rotation = STAGE_EFFECTS[beat.stage]
      const picked = k.effect ?? opts.effects?.[index] ?? rotation[keyCount % rotation.length]
      const effect = look === 'gentle' ? GENTLE_EFFECT[picked] : picked
      const spokenStartMs = startMs + at(k.charStart)
      const spokenEndMs = startMs + at(k.charEnd - 1, 'end')
      keys.push({ text: k.text, effect, spokenStartMs, spokenEndMs, ...keyWindow(effect, spokenStartMs, spokenEndMs), seed: keyCount + 1, beat: index })
      keyCount++
    }

    const bodyEndMs = startMs + bodyMs
    t = bodyEndMs + spec.breathMs + holdMs
    return {
      ...beat, index, startMs, bodyEndMs, endMs: t,
      beatHz: band.beatHz, carrierHz: band.carrierHz, voiced, aligned: !!al, phrases: timedPhrases, lines,
    }
  })

  const safeKeys = look === 'gentle' ? settleKeys(keys) : guardFlashes(keys)
  return {
    durationMs: t + tailMs, leadInMs, tailMs, beats: timed,
    keys: safeKeys,
    subliminals: scheduleSubliminals(timed, safeKeys),
    look,
  }
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

/** The reading line on screen at tMs, if any. */
export function lineAt(tl: Timeline, tMs: number): TimedLine | null {
  const i = beatIndexAt(tl, tMs)
  if (i < 0) return null
  // A beat's last line lingers into the next beat's lead, so check the previous beat too.
  for (const b of [tl.beats[i], tl.beats[i - 1]]) {
    const line = b?.lines.find((l) => tMs >= l.startMs && tMs < l.endMs)
    if (line) return line
  }
  return null
}

/** "m:ss" for beat lists. */
export function formatClock(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
