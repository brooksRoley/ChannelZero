/**
 * Glass Studio trim range — pure helpers shared by the preview loop and export.
 * A range is in media seconds; `endS` of 0 (or past the end) means "to the end".
 */

/** Shortest range the editor allows, so In and Out never collapse together. */
export const MIN_TRIM_S = 0.5

export interface TrimRange {
  startS: number
  endS: number
}

/** Clamp a proposed range into [0, durationS] with at least MIN_TRIM_S between ends. */
export function clampTrim(range: TrimRange, durationS: number): TrimRange {
  const dur = isFinite(durationS) && durationS > 0 ? durationS : 0
  if (dur === 0) return { startS: 0, endS: 0 }
  const min = Math.min(MIN_TRIM_S, dur)
  const endS = range.endS > 0 ? Math.min(dur, Math.max(min, range.endS)) : dur
  const startS = Math.max(0, Math.min(range.startS, endS - min))
  return { startS, endS }
}

/** Move the In point to `tS`, keeping Out. */
export function setTrimIn(range: TrimRange, tS: number, durationS: number): TrimRange {
  return clampTrim({ startS: tS, endS: range.endS }, durationS)
}

/** Move the Out point to `tS`, keeping In (pushing In back if needed). */
export function setTrimOut(range: TrimRange, tS: number, durationS: number): TrimRange {
  const min = Math.min(MIN_TRIM_S, durationS)
  const endS = Math.max(min, tS)
  return clampTrim({ startS: Math.min(range.startS, endS - min), endS }, durationS)
}

export function isTrimmed(range: TrimRange, durationS: number): boolean {
  return range.startS > 0 || (range.endS > 0 && range.endS < durationS)
}

/** 0–1 progress of `tS` through the range. */
export function trimProgress(range: TrimRange, tS: number): number {
  const len = range.endS - range.startS
  if (len <= 0) return 0
  return Math.max(0, Math.min(1, (tS - range.startS) / len))
}

/**
 * Where the preview playhead should be: wrap to the In point once it reaches Out,
 * or if it sits before In (e.g. the full-media loop restarted at 0). Returns null
 * when no correction is needed.
 */
export function loopCorrection(range: TrimRange, tS: number): number | null {
  if (range.endS <= range.startS) return null
  if (tS >= range.endS || tS < range.startS - 0.05) return range.startS
  return null
}

/**
 * PURE: session fade envelope (0–1) at `tS` — a linear ramp up over `fadeS`
 * after the In point and down over `fadeS` before Out. Shared by the audio bus
 * and the fade-to-black picture so sound and image move together. Fades are
 * shortened to half the range so they never overlap.
 */
export function sessionEnvelope(range: TrimRange, tS: number, fadeS: number): number {
  const len = range.endS - range.startS
  if (!(fadeS > 0) || len <= 0) return 1
  const f = Math.min(fadeS, len / 2)
  const up = (tS - range.startS) / f
  const down = (range.endS - tS) / f
  return Math.max(0, Math.min(1, up, down))
}
