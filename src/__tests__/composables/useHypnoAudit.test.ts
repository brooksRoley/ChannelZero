import { describe, it, expect, vi } from 'vitest'

vi.mock('tone', () => ({}))
vi.mock('@/composables/useTranceEngine', () => ({
  BINAURAL_LAYERS: {
    alpha: { id: 'alpha', label: 'Alpha Wave', leftHz: 195, rightHz: 205, targetBand: 'alpha' },
  },
  useTranceEngine: () => ({}),
}))
vi.mock('@/composables/useStudioBinaural', () => ({
  BANDS: { gamma: { beatHz: 40, carrierHz: 220 } },
}))

import {
  classifyBand,
  auditBinauralPair,
  allBinauralPairs,
  findPeaks,
  relativeLuminance,
  countFlashes,
} from '@/composables/useHypnoAudit'

describe('classifyBand', () => {
  it('maps beat frequencies to EEG bands', () => {
    expect(classifyBand(2)).toBe('delta')
    expect(classifyBand(6)).toBe('theta')
    expect(classifyBand(7.83)).toBe('theta')
    expect(classifyBand(10)).toBe('alpha')
    expect(classifyBand(18)).toBe('beta')
    expect(classifyBand(40)).toBe('gamma')
  })
})

describe('auditBinauralPair', () => {
  it('passes a well-formed alpha pair', () => {
    const a = auditBinauralPair({ source: 't', label: 'Alpha', leftHz: 195, rightHz: 205, targetBand: 'alpha' })
    expect(a.beatHz).toBe(10)
    expect(a.carrierHz).toBe(200)
    expect(a.worst).toBe('pass')
  })

  it('fails when the beat is outside the labelled band', () => {
    const a = auditBinauralPair({ source: 't', label: 'Bad', leftHz: 195, rightHz: 205, targetBand: 'theta' })
    expect(a.worst).toBe('fail')
  })

  it('warns on beats above 30 Hz', () => {
    const a = auditBinauralPair({ source: 't', label: 'Gamma', leftHz: 200, rightHz: 240, targetBand: 'gamma' })
    expect(a.worst).toBe('warn')
  })

  it('passes fast beats reinforced with an isochronic pulse', () => {
    const a = auditBinauralPair({ source: 't', label: 'Gamma', leftHz: 200, rightHz: 240, targetBand: 'gamma', isochronic: true })
    expect(a.worst).toBe('pass')
  })

  it('fails carriers above 1 kHz', () => {
    const a = auditBinauralPair({ source: 't', label: 'High', leftHz: 1495, rightHz: 1505, targetBand: 'alpha' })
    expect(a.worst).toBe('fail')
  })
})

describe('allBinauralPairs', () => {
  it('derives studio L/R from carrier ± beat/2', () => {
    const studio = allBinauralPairs().find(p => p.source === 'Glass studio')!
    expect(studio.leftHz).toBe(200)
    expect(studio.rightHz).toBe(240)
  })

  it('marks the studio gamma band as isochronic', () => {
    const studio = allBinauralPairs().find(p => p.source === 'Glass studio')!
    expect(studio.isochronic).toBe(true)
  })
})

describe('findPeaks', () => {
  it('locates a sub-bin peak with parabolic interpolation', () => {
    const sampleRate = 48000, fftSize = 32768
    const binHz = sampleRate / fftSize
    const spectrum = new Float32Array(fftSize / 2).fill(-120)
    const target = 205.3
    const centre = target / binHz
    for (let i = Math.floor(centre) - 3; i <= Math.floor(centre) + 3; i++) {
      spectrum[i] = -20 - 6 * (i - centre) ** 2 // parabola peaking at `target`
    }
    const [peak] = findPeaks(spectrum, sampleRate, fftSize)
    expect(peak.hz).toBeCloseTo(target, 1)
  })

  it('ignores content below the floor', () => {
    const spectrum = new Float32Array(1024).fill(-120)
    expect(findPeaks(spectrum, 48000, 2048)).toEqual([])
  })
})

describe('relativeLuminance', () => {
  it('is 0 for black and 1 for white', () => {
    expect(relativeLuminance(0, 0, 0)).toBe(0)
    expect(relativeLuminance(255, 255, 255)).toBeCloseTo(1, 5)
  })
})

describe('countFlashes', () => {
  const square = (hz: number, seconds: number) => {
    const out = []
    for (let t = 0; t < seconds * 1000; t += 33) {
      out.push({ t, lum: Math.floor((t / 1000) * hz * 2) % 2 === 0 ? 0.05 : 0.6 })
    }
    return out
  }

  it('passes a steady image', () => {
    const r = countFlashes(Array.from({ length: 60 }, (_, i) => ({ t: i * 33, lum: 0.3 })))
    expect(r.flashes).toBe(0)
    expect(r.verdict).toBe('pass')
  })

  it('passes a slow 1 Hz pulse', () => {
    expect(countFlashes(square(1, 4)).verdict).toBe('pass')
  })

  it('fails a 6 Hz strobe', () => {
    const r = countFlashes(square(6, 3))
    expect(r.maxPerSecond).toBeGreaterThan(3)
    expect(r.verdict).toBe('fail')
  })

  it('ignores small luminance wobble', () => {
    const r = countFlashes(Array.from({ length: 90 }, (_, i) => ({ t: i * 33, lum: 0.3 + (i % 2) * 0.05 })))
    expect(r.flashes).toBe(0)
  })
})
