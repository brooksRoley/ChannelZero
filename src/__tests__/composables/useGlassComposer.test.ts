import { describe, it, expect } from 'vitest'
import { layerStateAt, FLASH_FLOOR_MS, safeVisualHz, subliminalFlashRate, MAX_VISUAL_HZ, DEFAULT_MOTION_HZ } from '@/composables/useGlassComposer'
import { isochronicDepth, ISOCHRONIC_ABOVE_HZ } from '@/composables/useBinauralEngine'
import { makeDefaultTextLayer, type TextLayer } from '@/composables/studioTypes'

function layer(overrides: Partial<TextLayer> = {}): TextLayer {
  return makeDefaultTextLayer(overrides)
}

describe('layerStateAt — sequence timing', () => {
  // 3 items, hold 1000ms, fade 200ms → slot = 1400ms, cycle = 4200ms
  const seq = layer({
    content: ['one', 'two', 'three'],
    style: { color: '#fff', opacity: 1, blend: 'normal' },
    timing: { mode: 'sequence', holdMs: 1000, fadeMs: 200, intervalMs: 4000, flashMs: 200 },
    motion: { type: 'none', amount: 0, syncToBeat: false },
  })

  it('shows the first item fully during its hold window', () => {
    const s = layerStateAt(seq, 600) // inside item 0 hold (200..1200)
    expect(s.text).toBe('one')
    expect(s.alpha).toBeCloseTo(1, 5)
  })

  it('is mid-fade-in at the start of an item', () => {
    const s = layerStateAt(seq, 100) // half of the 200ms fade-in
    expect(s.text).toBe('one')
    expect(s.alpha).toBeCloseTo(0.5, 5)
  })

  it('advances to the second item in its slot', () => {
    const s = layerStateAt(seq, 1400 + 600) // item 1 hold window
    expect(s.text).toBe('two')
    expect(s.alpha).toBeCloseTo(1, 5)
  })

  it('loops back to the first item after a full cycle', () => {
    const s = layerStateAt(seq, 4200 + 600) // cycle length 4200 + item0 hold
    expect(s.text).toBe('one')
    expect(s.alpha).toBeCloseTo(1, 5)
  })
})

describe('layerStateAt — subliminal timing', () => {
  // interval 1000ms, flash 200ms
  const sub = layer({
    content: ['a', 'b', 'c'],
    style: { color: '#fff', opacity: 0.8, blend: 'normal' },
    timing: { mode: 'subliminal', holdMs: 1000, fadeMs: 200, intervalMs: 1000, flashMs: 200 },
    motion: { type: 'none', amount: 0, syncToBeat: false },
  })

  it('is visible at layer opacity during the flash window', () => {
    const s = layerStateAt(sub, 50) // within first 200ms flash
    expect(s.alpha).toBeCloseTo(0.8, 5)
    expect(s.text).not.toBeNull()
  })

  it('is hidden between flashes', () => {
    const s = layerStateAt(sub, 500) // after flash, before next interval
    expect(s.alpha).toBe(0)
  })

  it('is deterministic — same t yields same pooled text', () => {
    const a = layerStateAt(sub, 50).text
    const b = layerStateAt(sub, 50).text
    expect(a).toBe(b)
  })

  it('clamps the flash window to the 33ms export floor', () => {
    const tiny = layer({
      content: ['x'],
      timing: { mode: 'subliminal', holdMs: 0, fadeMs: 0, intervalMs: 1000, flashMs: 5 },
      motion: { type: 'none', amount: 0, syncToBeat: false },
    })
    // 5ms requested is clamped up to FLASH_FLOOR_MS, so t=20ms is still ON.
    expect(FLASH_FLOOR_MS).toBe(33)
    expect(layerStateAt(tiny, 20).alpha).toBeGreaterThan(0)
    expect(layerStateAt(tiny, 40).alpha).toBe(0)
  })
})

describe('layerStateAt — persistent timing', () => {
  it('fades in once over fadeMs then holds at opacity', () => {
    const p = layer({
      content: ['always'],
      style: { color: '#fff', opacity: 0.6, blend: 'normal' },
      timing: { mode: 'persistent', holdMs: 2000, fadeMs: 400, intervalMs: 4000, flashMs: 200 },
      motion: { type: 'none', amount: 0, syncToBeat: false },
    })
    expect(layerStateAt(p, 200).alpha).toBeCloseTo(0.3, 5) // half of 400ms fade × 0.6
    expect(layerStateAt(p, 5000).alpha).toBeCloseTo(0.6, 5)
    expect(layerStateAt(p, 5000).text).toBe('always')
  })
})

describe('safeVisualHz — beat-synced motion stays under the flash limit', () => {
  it('divides every studio band down to a phase-locked subharmonic ≤ MAX_VISUAL_HZ', () => {
    for (const beat of [2, 6, 7.83, 10, 18, 40]) {
      const hz = safeVisualHz(beat)
      expect(hz).toBeLessThanOrEqual(MAX_VISUAL_HZ)
      expect(Number.isInteger(+(beat / hz).toFixed(9))).toBe(true)
    }
    expect(safeVisualHz(10)).toBe(2.5)
    expect(safeVisualHz(40)).toBe(2.5)
    expect(safeVisualHz(2)).toBe(2)
  })

  it('falls back to the default rate with no beat', () => {
    expect(safeVisualHz(0)).toBe(DEFAULT_MOTION_HZ)
  })

  it('caps waver opacity oscillation even at a 40 Hz beat', () => {
    const l = layer({ motion: { type: 'waver', amount: 1, syncToBeat: true } })
    // At 2.5 Hz, two samples 1/80 s apart (a quarter of a 40 Hz cycle) barely differ.
    const a = layerStateAt(l, 0, 40).transform.alphaMul
    const b = layerStateAt(l, 1000 / 160, 40).transform.alphaMul
    expect(Math.abs(a - b)).toBeLessThan(0.05)
  })
})

describe('subliminalFlashRate', () => {
  const sub = (intervalMs: number, content = ['x']) =>
    layer({ content, timing: { ...layer().timing, mode: 'subliminal', intervalMs } })

  it('sums flashes/sec across subliminal layers with content', () => {
    expect(subliminalFlashRate([sub(500), sub(500)])).toBe(4)
    expect(subliminalFlashRate([sub(1000), sub(500, [''])])).toBe(1)
  })
})

describe('isochronicDepth', () => {
  it('engages only above the binaural ceiling', () => {
    expect(isochronicDepth(ISOCHRONIC_ABOVE_HZ)).toBe(0)
    expect(isochronicDepth(40)).toBeGreaterThan(0)
  })
})
