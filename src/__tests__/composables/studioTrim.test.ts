import { describe, it, expect } from 'vitest'
import {
  clampTrim, setTrimIn, setTrimOut, isTrimmed, trimProgress, loopCorrection, sessionEnvelope, MIN_TRIM_S,
} from '@/composables/studioTrim'

describe('studioTrim', () => {
  it('treats endS 0 as "to the end"', () => {
    expect(clampTrim({ startS: 0, endS: 0 }, 60)).toEqual({ startS: 0, endS: 60 })
  })

  it('never lets In and Out collapse', () => {
    const r = setTrimIn({ startS: 0, endS: 10 }, 10, 60)
    expect(r.endS - r.startS).toBeGreaterThanOrEqual(MIN_TRIM_S)
    const o = setTrimOut({ startS: 20, endS: 60 }, 5, 60)
    expect(o).toEqual({ startS: 5 - MIN_TRIM_S, endS: 5 })
  })

  it('clamps to the media duration', () => {
    expect(setTrimOut({ startS: 0, endS: 60 }, 90, 60).endS).toBe(60)
    expect(setTrimIn({ startS: 0, endS: 60 }, -3, 60).startS).toBe(0)
  })

  it('reports whether a range is trimmed', () => {
    expect(isTrimmed({ startS: 0, endS: 60 }, 60)).toBe(false)
    expect(isTrimmed({ startS: 5, endS: 60 }, 60)).toBe(true)
    expect(isTrimmed({ startS: 0, endS: 30 }, 60)).toBe(true)
  })

  it('measures progress through the range', () => {
    expect(trimProgress({ startS: 10, endS: 20 }, 15)).toBe(0.5)
    expect(trimProgress({ startS: 10, endS: 20 }, 25)).toBe(1)
  })

  it('wraps the preview playhead at Out and before In', () => {
    const r = { startS: 10, endS: 20 }
    expect(loopCorrection(r, 15)).toBeNull()
    expect(loopCorrection(r, 20)).toBe(10)
    expect(loopCorrection(r, 0)).toBe(10)
  })
})

describe('sessionEnvelope', () => {
  const r = { startS: 10, endS: 40 }

  it('ramps up after In, holds, and ramps down before Out', () => {
    expect(sessionEnvelope(r, 10, 4)).toBe(0)
    expect(sessionEnvelope(r, 12, 4)).toBe(0.5)
    expect(sessionEnvelope(r, 25, 4)).toBe(1)
    expect(sessionEnvelope(r, 38, 4)).toBe(0.5)
    expect(sessionEnvelope(r, 40, 4)).toBe(0)
  })

  it('is flat when fading is off', () => {
    expect(sessionEnvelope(r, 10, 0)).toBe(1)
  })

  it('shortens fades so they never overlap on a short range', () => {
    const short = { startS: 0, endS: 4 }
    expect(sessionEnvelope(short, 2, 10)).toBe(1)
  })
})
