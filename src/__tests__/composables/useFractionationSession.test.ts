import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, effectScope, nextTick, type EffectScope } from 'vue'

// ── Mocks: eye sensor, voice, trance engine ───────────────────────
const status = ref<string>('off')
const eyesClosed = ref(false)
let eyeListener: ((closed: boolean) => void) | null = null
const eye = {
  status,
  eyesClosed,
  start: vi.fn(async () => {}),
  stop: vi.fn(),
  onChange: vi.fn((cb: (closed: boolean) => void) => {
    eyeListener = cb
    return () => { eyeListener = null }
  }),
}

let autoVoice = false
let pendingLines: (() => void)[] = []
const voice = {
  say: vi.fn((_text: string) =>
    autoVoice ? Promise.resolve() : new Promise<void>((r) => { pendingLines.push(r) }),
  ),
  cancel: vi.fn(),
}

const sessionActive = ref(false)
const engine = {
  sessionActive,
  startSession: vi.fn(async () => { sessionActive.value = true }),
  enterPhase: vi.fn(),
  setDepth: vi.fn(),
  finishSession: vi.fn(async () => { sessionActive.value = false }),
  stopSession: vi.fn(() => { sessionActive.value = false }),
}

vi.mock('tone', () => ({}))
vi.mock('@/composables/useEyeState', () => ({ useEyeState: () => eye }))
vi.mock('@/composables/useVoice', () => ({ useVoice: () => voice }))
vi.mock('@/composables/useTranceEngine', () => ({ useTranceEngine: () => engine }))

import { useFractionationSession, type FracConfig } from '@/composables/useFractionation'
import { FRACTIONATION_SCRIPT as S } from '@/data/fractionationScript'

let scope: EffectScope

function create(config: Partial<FracConfig> = {}) {
  scope = effectScope()
  return scope.run(() => useFractionationSession(config))!
}

/** Finish the line being spoken and let the VOICE_DONE land. */
async function finishLine() {
  pendingLines.shift()?.()
  await vi.advanceTimersByTimeAsync(0)
}

function lastSaid() {
  return voice.say.mock.calls.at(-1)?.[0]
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  status.value = 'off'
  eyesClosed.value = false
  eyeListener = null
  autoVoice = false
  pendingLines = []
  sessionActive.value = false
})

afterEach(() => {
  scope?.stop()
  vi.useRealTimers()
})

describe('useFractionationSession', () => {
  it('starts the engine in driver mode and speaks the first induction line', async () => {
    const s = create()
    await s.start({ camera: false })

    expect(engine.startSession).toHaveBeenCalledWith({ autoAdvance: false, phrases: false })
    expect(engine.enterPhase).toHaveBeenCalledWith('induction')
    expect(engine.setDepth).toHaveBeenCalledWith(0)
    expect(voice.say).toHaveBeenCalledTimes(1)
    expect(lastSaid()).toBe(S.induction[0])
    expect(s.running.value).toBe(true)
    expect(s.stage.value).toBe('induce')
    expect(s.round.value).toBe(1)
    expect(s.rounds.value).toBe(3)
    expect(eye.onChange).not.toHaveBeenCalled()
  })

  it('speaks the next line only once the current one has finished', async () => {
    const s = create()
    await s.start({ camera: false })

    // Time passing doesn't skip ahead while a line is still being spoken.
    await vi.advanceTimersByTimeAsync(10_000)
    expect(voice.say).toHaveBeenCalledTimes(1)

    await finishLine()
    expect(lastSaid()).toBe(S.induction[1])

    for (let i = 2; i < S.induction.length; i++) await finishLine()
    expect(lastSaid()).toBe(S.induction[S.induction.length - 1])

    await finishLine()
    expect(lastSaid()).toBe(S.descend)
    expect(s.stage.value).toBe('descend')
  })

  it('ignores eye events unless the camera is actually tracking', async () => {
    const s = create()
    status.value = 'loading'
    await s.start({ camera: true })
    expect(eye.onChange).toHaveBeenCalledTimes(1)

    for (let i = 0; i < S.induction.length; i++) await finishLine()
    await finishLine() // the "let your eyes close" line
    expect(s.stage.value).toBe('descend')

    // No face: the held "closed" reading must not count.
    status.value = 'no-face'
    eyesClosed.value = true
    eyeListener!(true)
    await vi.advanceTimersByTimeAsync(5_000)
    expect(s.stage.value).toBe('descend')

    // Tracking again: the eyes settle closed and the session moves on early.
    status.value = 'tracking'
    await nextTick()
    await vi.advanceTimersByTimeAsync(3_500)
    expect(s.stage.value).toBe('hold')
    expect(engine.enterPhase).toHaveBeenCalledWith('deepen')
  })

  it('runs to completion: finishes the engine and releases the camera', async () => {
    autoVoice = true
    const s = create({
      rounds: 2,
      descendTimeoutMs: 1000,
      holdBaseMs: 1000,
      holdPerRoundMs: 0,
      emergeTimeoutMs: 1000,
      finalHoldMs: 1000,
    })
    await s.start({ camera: false })
    await vi.advanceTimersByTimeAsync(20_000)

    expect(engine.finishSession).toHaveBeenCalledTimes(1)
    expect(eye.stop).toHaveBeenCalled()
    expect(voice.cancel).toHaveBeenCalled()
    expect(s.running.value).toBe(false)
    expect(s.stage.value).toBe('done')
    expect(voice.say).toHaveBeenCalledWith(S.wake[S.wake.length - 1])
    expect(engine.enterPhase).toHaveBeenCalledWith('coherence') // the emerge between rounds

    // The clock is gone: nothing else happens.
    const calls = voice.say.mock.calls.length
    await vi.advanceTimersByTimeAsync(10_000)
    expect(voice.say.mock.calls.length).toBe(calls)
  })

  it('stop() ends the engine, camera and voice and stops the clock', async () => {
    const s = create()
    status.value = 'tracking'
    await s.start({ camera: true })
    s.stop()

    expect(engine.stopSession).toHaveBeenCalledTimes(1)
    expect(engine.finishSession).not.toHaveBeenCalled() // never reached a hold
    expect(eye.stop).toHaveBeenCalled()
    expect(voice.cancel).toHaveBeenCalled()
    expect(s.running.value).toBe(false)
    expect(eyeListener).toBeNull()

    // A line that resolves late doesn't restart anything.
    await finishLine()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(voice.say).toHaveBeenCalledTimes(1)
  })

  it('cleans up when its scope is disposed', async () => {
    const s = create()
    await s.start({ camera: false })
    scope.stop()
    expect(engine.stopSession).toHaveBeenCalled()
    expect(voice.cancel).toHaveBeenCalled()
    expect(s.running.value).toBe(false)
  })

  it('stops when something else ends the engine', async () => {
    const s = create()
    await s.start({ camera: false })
    sessionActive.value = false
    await nextTick()
    expect(s.running.value).toBe(false)
    expect(voice.cancel).toHaveBeenCalled()
  })
})
