import { describe, it, expect, beforeEach } from 'vitest'
import { readLocally, toneFor } from '@/composables/useReflection'
import {
  practiceThread, familiarity, averageShift, noticings, type PracticeEntry,
} from '@/composables/usePracticeJourney'
import { METHODS, METHOD_ORDER } from '@/data/practiceMethods'
import { LEARN_TOPICS } from '@/data/learn'

const DAY = 86_400_000

function entry(before: number, after: number | null, method: PracticeEntry['method'] = 'zeromind', tone?: string): PracticeEntry {
  return {
    id: Math.random().toString(36),
    method,
    startedAt: Date.now(),
    before: { rating: before },
    during: [],
    after: after === null ? undefined : { rating: after, reading: tone ? { tone, valence: 0, energy: 0, reflection: '', source: 'local' } : undefined },
  }
}

describe('readLocally', () => {
  it('reads settling language as positive and low energy', () => {
    const r = readLocally('my shoulders feel heavy and calm, sinking', 'during')
    expect(r.tone).toBe('settling')
    expect(r.valence).toBeGreaterThan(0)
    expect(r.energy).toBeLessThan(0.3)
    expect(r.source).toBe('local')
  })

  it('reads restless language and honours negation', () => {
    expect(readLocally('anxious and racing', 'before').tone).toBe('restless')
    expect(readLocally('not calm at all', 'during').valence).toBeLessThan(0)
  })

  it('falls back to a neutral mirror for unknown words', () => {
    const r = readLocally('purple', 'after')
    expect(r.tone).toBe('present')
    expect(r.reflection.length).toBeGreaterThan(0)
  })

  it('flags self-harm language with a care message', () => {
    expect(readLocally('I want to hurt myself', 'during').tone).toBe('unsafe')
  })

  it('names quadrants', () => {
    expect(toneFor(0.5, 0.8)).toBe('bright')
    expect(toneFor(-0.5, 0.1)).toBe('heavy')
  })
})

describe('practiceThread', () => {
  it('marks the days practiced, today last', () => {
    const now = new Date('2026-10-16T12:00:00').getTime()
    const t = practiceThread([now, now - DAY, now - 3 * DAY], now, 5)
    expect(t).toEqual([false, true, false, true, true])
  })
})

describe('familiarity', () => {
  it('climbs through gentle labels with progress', () => {
    expect(familiarity(0).label).toBe('new to you')
    expect(familiarity(5)).toMatchObject({ label: 'getting familiar', progress: 0.5 })
    expect(familiarity(40)).toMatchObject({ label: 'your own', progress: 1 })
  })
})

describe('averageShift / noticings', () => {
  it('averages after − before over reflected sessions only', () => {
    expect(averageShift([entry(2, 4), entry(3, 3), entry(1, null)])).toBe(1)
    expect(averageShift([])).toBeNull()
  })

  it('notices a run of lighter endings and the most shifting method', () => {
    const list = [entry(2, 4), entry(2, 3), entry(1, 4), entry(3, 4, 'spiral'), entry(3, 3, 'spiral')]
    const out = noticings(list, Array(14).fill(false))
    expect(out[0]).toMatch(/last three sessions/)
    expect(out.some((o) => o.includes('Breath descent'))).toBe(true)
  })

  it('nudges gently after a gap rather than scolding', () => {
    const thread = [...Array(10).fill(false), true, true, false, false]
    expect(noticings([], thread).join(' ')).toMatch(/pick the thread back up/)
  })
})

describe('practice methods', () => {
  it('every method links to a real learn article', () => {
    const slugs = new Set(LEARN_TOPICS.map((t) => t.slug))
    for (const id of METHOD_ORDER) expect(slugs.has(METHODS[id].learnSlug)).toBe(true)
  })
})
