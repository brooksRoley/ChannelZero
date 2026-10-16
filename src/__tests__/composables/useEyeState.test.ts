import { describe, it, expect, vi, afterEach } from 'vitest'

vi.mock('@mediapipe/tasks-vision', () => ({
  FilesetResolver: { forVisionTasks: vi.fn(async () => ({})) },
  FaceLandmarker: {
    createFromOptions: vi.fn(async () => ({ detectForVideo: vi.fn(), close: vi.fn() })),
  },
}))

import {
  classifyEyes,
  INITIAL_EYE_STATE,
  useEyeState,
  type EyeClassState,
} from '@/composables/useEyeState'

/** Feed `n` samples of the same blink score, `dt` ms apart. */
function feed(state: EyeClassState, score: number, n: number, dt = 50): EyeClassState {
  let s = state
  for (let i = 0; i < n; i++) s = classifyEyes(score, score, s, dt)
  return s
}

function closedState(): EyeClassState {
  return feed(INITIAL_EYE_STATE, 0.9, 8)
}

describe('classifyEyes', () => {
  it('starts open', () => {
    expect(INITIAL_EYE_STATE.closed).toBe(false)
    expect(classifyEyes(0, 0, INITIAL_EYE_STATE, 50).closed).toBe(false)
  })

  it('ignores a blink shorter than 300 ms', () => {
    let s = feed(INITIAL_EYE_STATE, 0.1, 4)
    s = feed(s, 0.95, 5) // pending reaches 200 ms
    expect(s.closed).toBe(false)
    expect(s.candidateClosed).toBe(true)
    s = feed(s, 0.1, 3)
    expect(s.closed).toBe(false)
    expect(s.pendingMs).toBe(0)
  })

  it('does not let separate blinks add up', () => {
    let s = INITIAL_EYE_STATE
    for (let i = 0; i < 5; i++) {
      s = feed(s, 0.9, 5)
      s = feed(s, 0.1, 2)
    }
    expect(s.closed).toBe(false)
  })

  it('flips to closed after a sustained close of 300 ms', () => {
    let s = feed(INITIAL_EYE_STATE, 0.9, 6) // pending 250 ms
    expect(s.closed).toBe(false)
    s = classifyEyes(0.9, 0.9, s, 50) // 300 ms
    expect(s.closed).toBe(true)
    expect(s.closedForMs).toBe(300)
    expect(s.openForMs).toBe(0)
  })

  it('averages both eyes', () => {
    // avg 0.6 closes, avg 0.5 does not cross the threshold
    expect(feed(INITIAL_EYE_STATE, 0.6, 8).closed).toBe(true)
    let s = INITIAL_EYE_STATE
    for (let i = 0; i < 10; i++) s = classifyEyes(1, 0, s, 50)
    expect(s.closed).toBe(false)
    s = INITIAL_EYE_STATE
    for (let i = 0; i < 10; i++) s = classifyEyes(1, 0.2, s, 50)
    expect(s.closed).toBe(true)
  })

  it('holds the open state inside the hysteresis band', () => {
    const s = feed(INITIAL_EYE_STATE, 0.45, 20)
    expect(s.closed).toBe(false)
    expect(s.candidateClosed).toBe(false)
    expect(s.openForMs).toBe(1000)
  })

  it('holds the closed state inside the hysteresis band', () => {
    let s = closedState()
    s = feed(s, 0.4, 20)
    expect(s.closed).toBe(true)
    expect(s.candidateClosed).toBe(true)
  })

  it('treats the thresholds as inclusive', () => {
    expect(classifyEyes(0.55, 0.55, INITIAL_EYE_STATE, 50).candidateClosed).toBe(true)
    const closed = closedState()
    expect(classifyEyes(0.35, 0.35, closed, 50).candidateClosed).toBe(false)
  })

  it('accumulates closedForMs while closed', () => {
    let s = closedState()
    const base = s.closedForMs
    s = feed(s, 0.9, 10, 100)
    expect(s.closedForMs).toBe(base + 1000)
    expect(s.openForMs).toBe(0)
  })

  it('accumulates openForMs while open', () => {
    const s = feed(INITIAL_EYE_STATE, 0.05, 12, 100)
    expect(s.openForMs).toBe(1200)
    expect(s.closedForMs).toBe(0)
  })

  it('needs 200 ms of open to reopen', () => {
    let s = closedState()
    s = feed(s, 0.1, 4) // pending 150 ms
    expect(s.closed).toBe(true)
    s = classifyEyes(0.1, 0.1, s, 50) // 200 ms
    expect(s.closed).toBe(false)
    expect(s.openForMs).toBe(200)
    expect(s.closedForMs).toBe(0)
  })

  it('keeps counting closedForMs through a brief flutter open', () => {
    let s = closedState()
    const base = s.closedForMs
    s = feed(s, 0.1, 3) // 100 ms pending open, not enough
    s = feed(s, 0.9, 2)
    expect(s.closed).toBe(true)
    expect(s.closedForMs).toBe(base + 250)
  })

  it('treats negative dt as zero', () => {
    const s = classifyEyes(0.1, 0.1, INITIAL_EYE_STATE, -500)
    expect(s.openForMs).toBe(0)
  })
})

describe('useEyeState', () => {
  const originalMediaDevices = navigator.mediaDevices

  afterEach(() => {
    useEyeState().stop()
    Object.defineProperty(navigator, 'mediaDevices', {
      value: originalMediaDevices,
      configurable: true,
    })
  })

  function stubGetUserMedia(impl: () => Promise<MediaStream>) {
    const getUserMedia = vi.fn(impl)
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia },
      configurable: true,
    })
    return getUserMedia
  }

  it('starts off', () => {
    const eyes = useEyeState()
    expect(eyes.status.value).toBe('off')
    expect(eyes.eyesClosed.value).toBe(false)
  })

  it('sets status denied when camera permission is refused', async () => {
    const err = Object.assign(new Error('Permission denied'), { name: 'NotAllowedError' })
    const getUserMedia = stubGetUserMedia(() => Promise.reject(err))
    const eyes = useEyeState()
    await expect(eyes.start()).resolves.toBeUndefined()
    expect(getUserMedia).toHaveBeenCalledWith({
      video: { facingMode: 'user', width: 320, height: 240 },
      audio: false,
    })
    expect(eyes.status.value).toBe('denied')
  })

  it('sets status error for other failures without throwing', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    stubGetUserMedia(() => Promise.reject(Object.assign(new Error('busy'), { name: 'NotReadableError' })))
    const eyes = useEyeState()
    await eyes.start()
    expect(eyes.status.value).toBe('error')
    warn.mockRestore()
  })

  it('stop resets to off', async () => {
    stubGetUserMedia(() => Promise.reject(Object.assign(new Error('x'), { name: 'NotAllowedError' })))
    const eyes = useEyeState()
    await eyes.start()
    eyes.stop()
    expect(eyes.status.value).toBe('off')
  })

  it('onChange returns an unsubscribe function', () => {
    const eyes = useEyeState()
    const off = eyes.onChange(() => {})
    expect(typeof off).toBe('function')
    off()
  })
})
