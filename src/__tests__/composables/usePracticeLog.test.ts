import { describe, it, expect, vi } from 'vitest'
import { recommendPractice } from '@/composables/usePracticeLog'

describe('recommendPractice', () => {
  it('routes unsettled moods to Zeromind regardless of time', () => {
    expect(recommendPractice(9, 'anxious').session).toBe('zeromind')
    expect(recommendPractice(14, 'heavy').session).toBe('zeromind')
  })

  it('routes scattered to Spiral and energized/focused to Audio', () => {
    expect(recommendPractice(22, 'scattered').session).toBe('spiral')
    expect(recommendPractice(22, 'energized').session).toBe('audio')
    expect(recommendPractice(6, 'focused').session).toBe('audio')
  })

  it('falls back to time of day for neutral or missing moods', () => {
    expect(recommendPractice(8, null).session).toBe('spiral')
    expect(recommendPractice(13, 'calm').session).toBe('audio')
    expect(recommendPractice(21, 'grateful').session).toBe('zeromind')
    expect(recommendPractice(2, null).session).toBe('zeromind')
  })

  it('always gives a reason', () => {
    for (const mood of [null, 'anxious', 'scattered', 'energized', 'hopeful']) {
      expect(recommendPractice(10, mood).reason.length).toBeGreaterThan(0)
    }
  })
})

describe('usePracticeLog', () => {
  async function fresh() {
    vi.resetModules()
    const mod = await import('@/composables/usePracticeLog')
    return mod.usePracticeLog()
  }

  it('records a session in today and persists it to localStorage', async () => {
    const { logPractice, todayPractice } = await fresh()
    logPractice('spiral', 300_000)
    expect(todayPractice.value).toHaveLength(1)
    expect(todayPractice.value[0].session).toBe('spiral')

    const { todayPractice: reloaded } = await fresh()
    expect(reloaded.value).toHaveLength(1)
  })

  it('excludes sessions from before today', async () => {
    localStorage.setItem('cz-practice-log', JSON.stringify([
      { session: 'audio', completedAt: Date.now() - 2 * 86_400_000, durationMs: 60_000 },
    ]))
    const { todayPractice, log } = await fresh()
    expect(log.value).toHaveLength(1)
    expect(todayPractice.value).toHaveLength(0)
  })

  it('survives corrupt storage', async () => {
    localStorage.setItem('cz-practice-log', '{not json')
    const { log } = await fresh()
    expect(log.value).toEqual([])
  })
})
