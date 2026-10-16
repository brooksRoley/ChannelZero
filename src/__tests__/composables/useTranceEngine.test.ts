import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Minimal fake Tone: every node is a chainable stub with rampTo-able params.
// `rampLog` records parameter ramps so tests can inspect them.
const { rampLog, FakeNode, transport } = vi.hoisted(() => {
  const rampLog: { name: string; value: number; time: number }[] = []
  const param = (name: string, value = 0) => ({
    value,
    rampTo(v: number, time: number) { rampLog.push({ name, value: v, time }); this.value = v },
  })
  class FakeNode {
    kind: string
    frequency: ReturnType<typeof param>
    volume: ReturnType<typeof param>
    gain: ReturnType<typeof param>
    constructor(kind: string, ...args: unknown[]) {
      this.kind = kind
      const first = typeof args[0] === 'number' ? (args[0] as number) : 0
      this.frequency = param(`${kind}.frequency`, first)
      this.volume = param(`${kind}.volume`)
      this.gain = param(`${kind}.gain`, first)
    }
    start() { return this }
    stop() { return this }
    connect() { return this }
    toDestination() { return this }
    dispose() { return this }
    triggerAttackRelease() { return this }
  }
  const transport = {
    state: 'stopped',
    seconds: 0,
    bpm: { value: 120 },
    start() { this.state = 'started' },
    stop() { this.state = 'stopped' },
    scheduleRepeat: () => 1,
    clear: () => {},
  }
  return { rampLog, FakeNode, transport }
})

vi.mock('tone', () => {
  const make = (kind: string) => class extends FakeNode { constructor(...a: unknown[]) { super(kind, ...a) } }
  return {
    start: async () => {},
    Oscillator: make('Oscillator'),
    LFO: make('LFO'),
    Gain: make('Gain'),
    Synth: make('Synth'),
    Loop: make('Loop'),
    Filter: make('Filter'),
    Noise: make('Noise'),
    Panner: make('Panner'),
    getTransport: () => transport,
    getDraw: () => ({ schedule: () => {} }),
  }
})
const authState = vi.hoisted(() => ({ authed: false, apiFetch: null as unknown as ReturnType<typeof vi.fn> }))
vi.mock('@/composables/useAuthStore', async () => {
  const { ref } = await import('vue')
  authState.apiFetch = vi.fn().mockResolvedValue({})
  return {
    useAuthStore: () => ({ apiFetch: authState.apiFetch, isAuthenticated: ref(authState.authed) }),
  }
})

import { useTranceEngine } from '@/composables/useTranceEngine'

describe('useTranceEngine external-driver mode', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    rampLog.length = 0
  })
  afterEach(() => {
    useTranceEngine().stopSession()
    useTranceEngine().clearCompletedSession()
    vi.useRealTimers()
  })

  it('startSession({autoAdvance:false}) stays in induction for 60 s', async () => {
    const e = useTranceEngine()
    await e.startSession({ autoAdvance: false })
    expect(e.phase.value).toBe('induction')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(e.phase.value).toBe('induction')
    expect(e.currentInstruction.value).not.toBe('') // phrases still on by default
  })

  it('phrases:false keeps currentInstruction empty', async () => {
    const e = useTranceEngine()
    await e.startSession({ autoAdvance: false, phrases: false })
    await vi.advanceTimersByTimeAsync(40_000)
    expect(e.currentInstruction.value).toBe('')
  })

  it('default startSession() still auto-advances induction → coherence at 30 s', async () => {
    const e = useTranceEngine()
    await e.startSession()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(e.phase.value).toBe('coherence')
  })

  it('enterPhase drives phases directly and is idempotent', async () => {
    const e = useTranceEngine()
    await e.startSession({ autoAdvance: false, phrases: false })
    e.enterPhase('deepen')
    expect(e.phase.value).toBe('deepen')
    e.enterPhase('deepen')
    expect(e.phase.value).toBe('deepen')
    e.enterPhase('coherence')
    expect(e.phase.value).toBe('coherence')
    e.enterPhase('joy')
    expect(e.phase.value).toBe('joy')
    // No joy → wake auto-advance in driver mode
    await vi.advanceTimersByTimeAsync(60_000)
    expect(e.phase.value).toBe('joy')
    e.enterPhase('wake')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(e.phase.value).toBe('wake')
    expect(e.sessionActive.value).toBe(true)
  })

  it('sync logic does not trigger deepen when autoAdvance is false', async () => {
    const e = useTranceEngine()
    await e.startSession({ autoAdvance: false })
    for (let i = 0; i < 20; i++) e.startSync() // induction-phase taps
    expect(e.phase.value).toBe('induction')
  })

  it('phrases:false with autoAdvance still hands wake → complete', async () => {
    const e = useTranceEngine()
    await e.startSession({ phrases: false })
    e.enterPhase('wake')
    await vi.advanceTimersByTimeAsync(30_000)
    expect(e.sessionActive.value).toBe(false)
    expect(e.completedSession.value?.dominantPhase).toBe('wake')
  })

  it('finishSession produces completedSession and stops', async () => {
    const e = useTranceEngine()
    await e.startSession({ autoAdvance: false, phrases: false })
    e.enterPhase('deepen')
    await e.finishSession()
    expect(e.sessionActive.value).toBe(false)
    expect(e.phase.value).toBe('idle')
    expect(e.completedSession.value?.dominantPhase).toBe('deepen')
  })

  it('does not POST the session for anonymous visitors (a 401 would redirect them to /login)', async () => {
    const e = useTranceEngine()
    authState.authed = false
    await e.startSession({ autoAdvance: false, phrases: false })
    await e.finishSession()
    expect(authState.apiFetch).not.toHaveBeenCalled()
    expect(e.completedSession.value).not.toBeNull()

    authState.authed = true
    await e.startSession({ autoAdvance: false, phrases: false })
    await e.finishSession()
    expect(authState.apiFetch).toHaveBeenCalledWith('/api/vector/zeromind', expect.objectContaining({ method: 'POST' }))
    authState.authed = false
  })

  it('setDepth clamps and ramps the core LFO between 6 and 3 Hz', async () => {
    const e = useTranceEngine()
    e.setDepth(0.5) // audio not initialised: no-op, no throw
    expect(rampLog).toEqual([])

    await e.startSession({ autoAdvance: false, phrases: false })
    rampLog.length = 0
    e.setDepth(5)
    expect(rampLog).toContainEqual({ name: 'LFO.frequency', value: 3, time: 8 })
    e.setDepth(-2)
    expect(rampLog).toContainEqual({ name: 'LFO.frequency', value: 6, time: 8 })
    e.setDepth(0.5)
    expect(rampLog).toContainEqual({ name: 'LFO.frequency', value: 4.5, time: 8 })
  })

  it('setDepth offsets active binaural voices (theta up, alpha down)', async () => {
    const e = useTranceEngine()
    await e.startSession({ autoAdvance: false, phrases: false })
    await e.toggleThetaDream()
    await e.toggleAlphaWave()
    rampLog.length = 0
    e.setDepth(1)
    // induction balance: alpha −18, theta −30
    const vols = rampLog.filter((r) => r.name === 'Oscillator.volume').map((r) => r.value)
    expect(vols).toContain(-24) // theta −30 + 6
    expect(vols).toContain(-24) // alpha −18 − 6
    expect(vols).not.toContain(-30)
    // a later phase balance still includes the offset: deepen alpha −30−6, theta −16+6
    rampLog.length = 0
    e.enterPhase('deepen')
    const deepVols = rampLog.filter((r) => r.name === 'Oscillator.volume').map((r) => r.value)
    expect(deepVols).toContain(-36)
    expect(deepVols).toContain(-10)
  })
})
