// Per-beat visual styling. PURE: no Vue, no DOM.
//
// The story text stays the source of truth for words, stages and keys; the
// beat editor layers a style over each beat. Backdrop and text placement are
// "sticky" like stage markers — unset carries the previous beat's choice on —
// and only affect drawing, so they preview without a rebuild. Key effect and
// hold change timing, so they go into buildTimeline.

import type { Effect } from './effects'
import type { StoryBeat, Timeline } from './storyBeats'
import { beatIndexAt } from './storyBeats'

export type Backdrop =
  | { kind: 'field' }
  | { kind: 'solid'; color: string }
  | { kind: 'gradient'; from: string; to: string }
  | { kind: 'media'; mediaId: string }

export type TextPlace = 'low' | 'middle' | 'high'

export interface BeatStyle {
  /** Unset: carry the previous beat's backdrop on. */
  backdrop?: Backdrop
  /** Reading-line placement. Unset: carry on. */
  place?: TextPlace
  /** Effect for key phrases without an explicit *effect:* (unset: stage rotation). */
  effect?: Effect
  /** Extra silence after the beat, ms. */
  holdMs?: number
}

export interface BeatScene {
  backdrop: Backdrop
  place: TextPlace
}

/** Backdrop changes crossfade this long from the beat's start — never a hard cut. */
export const BACKDROP_XFADE_MS = 1500

/** Longest extra hold the editor offers, ms. */
export const MAX_HOLD_MS = 20000

/** Resolve sticky styles into one scene per beat. */
export function resolveScenes(styles: (BeatStyle | undefined)[], count: number, base: Backdrop): BeatScene[] {
  let backdrop = base
  let place: TextPlace = 'low'
  const out: BeatScene[] = []
  for (let i = 0; i < count; i++) {
    backdrop = styles[i]?.backdrop ?? backdrop
    place = styles[i]?.place ?? place
    out.push({ backdrop, place })
  }
  return out
}

export function sameBackdrop(a: Backdrop, b: Backdrop): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

/** The backdrop(s) on screen at tMs: `to` fades in over `from` by `k` (0..1). */
export function backdropAt(tl: Timeline, scenes: BeatScene[], tMs: number): { from: Backdrop; to: Backdrop; k: number } | null {
  const i = beatIndexAt(tl, tMs)
  const cur = scenes[i]
  if (!cur) return null
  const prev = scenes[i - 1]
  const startMs = tl.beats[i].startMs
  if (!prev || tMs < startMs || sameBackdrop(prev.backdrop, cur.backdrop)) {
    return { from: cur.backdrop, to: cur.backdrop, k: 1 }
  }
  return { from: prev.backdrop, to: cur.backdrop, k: Math.min(1, (tMs - startMs) / BACKDROP_XFADE_MS) }
}

/**
 * Carry styles across a story edit. A beat keeps its style when its text is
 * unchanged (found by id, wherever it moved); a beat whose text was edited in
 * place inherits the style of the beat that was at its index, if that beat
 * is gone.
 */
export function remapStyles(
  prev: Pick<StoryBeat, 'id'>[],
  next: Pick<StoryBeat, 'id'>[],
  styles: (BeatStyle | undefined)[],
): (BeatStyle | undefined)[] {
  const byId = new Map<string, BeatStyle>()
  prev.forEach((b, i) => { if (b.id && styles[i]) byId.set(b.id, styles[i]!) })
  const nextIds = new Set(next.map((b) => b.id))
  return next.map((b, i) => {
    if (b.id && byId.has(b.id)) return byId.get(b.id)
    const was = prev[i]
    if (was && styles[i] && !nextIds.has(was.id)) return styles[i]
    return undefined
  })
}

/** Drop empty fields so "no style" is `undefined` and stays sticky-transparent. */
export function cleanStyle(s: BeatStyle): BeatStyle | undefined {
  const out: BeatStyle = {}
  if (s.backdrop) out.backdrop = s.backdrop
  if (s.place) out.place = s.place
  if (s.effect) out.effect = s.effect
  if (s.holdMs) out.holdMs = s.holdMs
  return Object.keys(out).length ? out : undefined
}
