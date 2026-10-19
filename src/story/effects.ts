// Attention effects for key phrases + the subliminal schedule. PURE: windows,
// rotation, the photosensitivity guard and deterministic scheduling. The
// canvas side lives in drawEffects.ts.
//
// Photosensitivity: WCAG 2.3.1 fails more than 3 flashes in any one second.
// A `flash` strobe runs at 2 Hz (3 onsets span 1 s, so at most 2 fall in any
// second), two strobes never overlap (the later key is downgraded to `slam`),
// and subliminals keep clear of strobes — so the worst case stays well under 3. `maxFlashesPerSecond` checks a built timeline.

import { mulberry32 } from '@/composables/useGlassComposer'
import type { StoryStage } from './storyBeats'

export type Effect = 'flash' | 'slam' | 'whisper' | 'type' | 'echo' | 'scatter' | 'hand'

export interface EffectSpec {
  label: string
  /** On screen this long before the phrase is spoken. */
  leadMs: number
  /** Held this long after it is spoken. */
  tailMs: number
  /** Shortest time on screen. */
  minMs: number
}

export const EFFECTS: Record<Effect, EffectSpec> = {
  flash:   { label: 'Flash',   leadMs: 60,  tailMs: 700,  minMs: 1800 },
  slam:    { label: 'Slam',    leadMs: 40,  tailMs: 900,  minMs: 1400 },
  whisper: { label: 'Whisper', leadMs: 300, tailMs: 1400, minMs: 2200 },
  type:    { label: 'Type',    leadMs: 0,   tailMs: 1200, minMs: 1600 },
  echo:    { label: 'Echo',    leadMs: 100, tailMs: 1800, minMs: 2400 },
  scatter: { label: 'Scatter', leadMs: 0,   tailMs: 1200, minMs: 2000 },
  hand:    { label: 'Hand',    leadMs: 150, tailMs: 1500, minMs: 2200 },
}

/** Default rotation per stage: gentle while inducing, louder on re-induction. */
export const STAGE_EFFECTS: Record<StoryStage, Effect[]> = {
  induce:   ['whisper', 'type', 'hand'],
  deepen:   ['echo', 'whisper', 'slam'],
  emerge:   ['type', 'hand'],
  reinduce: ['slam', 'echo', 'flash'],
  final:    ['whisper', 'echo'],
  wake:     ['slam', 'type'],
}

/** Strobe: on/off halves of this period, STROBE_CYCLES times. 500 ms → 2 Hz. */
export const STROBE_PERIOD_MS = 500
export const STROBE_CYCLES = 3
const STROBE_MS = STROBE_PERIOD_MS * STROBE_CYCLES

/** A subliminal is on screen this long (≥ FLASH_FLOOR_MS so 30 fps export keeps it). */
export const SUBLIMINAL_MS = 50
/** Mean gap between subliminals, with ± half-jitter. */
export const SUBLIMINAL_GAP_MS = 2400
/** Keep subliminals this far clear of either side of a strobe. */
// ≥ one strobe period, so a subliminal + two strobe onsets never share a second.
const STROBE_GUARD_MS = 600

export function keyWindow(effect: Effect, spokenStartMs: number, spokenEndMs: number) {
  const spec = EFFECTS[effect]
  const startMs = spokenStartMs - spec.leadMs
  let endMs = Math.max(spokenEndMs + spec.tailMs, startMs + spec.minMs)
  const strobeEndMs = effect === 'flash' ? startMs + STROBE_MS : startMs
  if (effect === 'flash') endMs = Math.max(endMs, strobeEndMs + 600)
  return { startMs, endMs, strobeEndMs }
}

interface KeyLike {
  effect: Effect
  spokenStartMs: number
  spokenEndMs: number
  startMs: number
  strobeEndMs: number
}

/** Downgrade any flash whose strobe would overlap an earlier one to `slam`. */
export function guardFlashes<K extends KeyLike>(keys: K[]): K[] {
  let lastStrobeEnd = -Infinity
  return keys.map((k) => {
    if (k.effect !== 'flash') return k
    if (k.startMs < lastStrobeEnd + STROBE_GUARD_MS) {
      return { ...k, effect: 'slam' as Effect, ...keyWindow('slam', k.spokenStartMs, k.spokenEndMs) }
    }
    lastStrobeEnd = k.strobeEndMs
    return k
  })
}

export interface SubliminalFlash {
  text: string
  atMs: number
  seed: number
}

interface BeatLike {
  index: number
  startMs: number
  endMs: number
  subliminal: string[]
}

/** Deterministic subliminal times for every beat with a pool, clear of strobes. */
export function scheduleSubliminals(beats: BeatLike[], keys: KeyLike[]): SubliminalFlash[] {
  const strobes = keys
    .filter((k) => k.effect === 'flash')
    .map((k) => [k.startMs - STROBE_GUARD_MS, k.strobeEndMs + STROBE_GUARD_MS] as const)
  const out: SubliminalFlash[] = []
  for (const b of beats) {
    if (!b.subliminal.length) continue
    const rand = mulberry32(b.index * 7919 + 17)
    let t = b.startMs + 800
    while (t < b.endMs - SUBLIMINAL_MS) {
      if (!strobes.some(([s, e]) => t >= s && t <= e)) {
        out.push({ text: b.subliminal[Math.floor(rand() * b.subliminal.length)], atMs: t, seed: out.length + 1 })
      }
      t += SUBLIMINAL_GAP_MS + (rand() - 0.5) * SUBLIMINAL_GAP_MS * 0.5
    }
  }
  return out
}

/** Onset times of every flash (each strobe "on" + each subliminal). */
export function flashOnsets(keys: KeyLike[], subs: SubliminalFlash[]): number[] {
  const t: number[] = []
  for (const k of keys) {
    if (k.effect !== 'flash') continue
    for (let c = 0; c < STROBE_CYCLES; c++) t.push(k.startMs + c * STROBE_PERIOD_MS)
  }
  for (const s of subs) t.push(s.atMs)
  return t.sort((a, b) => a - b)
}

/** Most flash onsets in any 1-second window. Must stay ≤ 3 (WCAG 2.3.1). */
export function maxFlashesPerSecond(keys: KeyLike[], subs: SubliminalFlash[]): number {
  const t = flashOnsets(keys, subs)
  let best = 0
  let lo = 0
  for (let hi = 0; hi < t.length; hi++) {
    while (t[hi] - t[lo] >= 1000) lo++
    best = Math.max(best, hi - lo + 1)
  }
  return best
}
