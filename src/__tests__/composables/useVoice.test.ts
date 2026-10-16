import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// jsdom/happy-dom lack Web Speech — provide a controllable fake.
class FakeUtterance {
  text: string
  rate = 1
  pitch = 1
  lang = ''
  voice: unknown = null
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(text: string) {
    this.text = text
  }
}

let spoken: FakeUtterance[] = []
const synth = {
  speak: vi.fn((u: FakeUtterance) => { spoken.push(u) }),
  cancel: vi.fn(),
  getVoices: vi.fn(() => [
    { name: 'Fred', lang: 'en-US' },
    { name: 'Samantha', lang: 'en-US' },
  ]),
}

// kokoro-js mock: behaviour switched per test.
const kokoroMode = { fail: false }
const fromPretrained = vi.fn(async () => ({
  generate: vi.fn(async () => ({ audio: new Float32Array(10), sampling_rate: 24000 })),
}))
vi.mock('kokoro-js', () => {
  if (kokoroMode.fail) throw new Error('chunk failed to load')
  return { KokoroTTS: { from_pretrained: fromPretrained } }
})

async function load() {
  vi.resetModules()
  const mod = await import('@/composables/useVoice')
  return mod.useVoice()
}

beforeEach(() => {
  spoken = []
  kokoroMode.fail = false
  vi.stubGlobal('SpeechSynthesisUtterance', FakeUtterance)
  Object.defineProperty(window, 'speechSynthesis', { value: synth, configurable: true, writable: true })
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useVoice — speech backend', () => {
  it('is supported and defaults to speech', async () => {
    const v = await load()
    expect(v.supported.value).toBe(true)
    expect(v.backend.value).toBe('speech')
    expect(v.kokoroStatus.value).toBe('off')
  })

  it('say resolves when onend fires, with calm rate/pitch and a preferred voice', async () => {
    const v = await load()
    let resolved = false
    const p = v.say('Let your eyes close.').then(() => { resolved = true })
    expect(spoken).toHaveLength(1)
    const u = spoken[0]
    expect(u.rate).toBeCloseTo(0.85)
    expect(u.pitch).toBeCloseTo(0.9)
    expect((u.voice as { name: string }).name).toBe('Samantha')
    await Promise.resolve()
    expect(resolved).toBe(false)
    u.onend!()
    await p
    expect(resolved).toBe(true)
  })

  it('say resolves via the safety timeout when onend never fires', async () => {
    vi.useFakeTimers()
    const v = await load()
    const text = 'Deeper now.' // 11 chars → 440 ms + 4000 ms
    let resolved = false
    void v.say(text).then(() => { resolved = true })
    await vi.advanceTimersByTimeAsync(4000)
    expect(resolved).toBe(false)
    await vi.advanceTimersByTimeAsync(500)
    expect(resolved).toBe(true)
  })

  it('cancel resolves the pending say', async () => {
    const v = await load()
    const p = v.say('And rise back up.')
    v.cancel()
    await expect(p).resolves.toBeUndefined()
    expect(synth.cancel).toHaveBeenCalled()
  })

  it('resolves on utterance error and never rejects', async () => {
    const v = await load()
    const p = v.say('Hello.')
    spoken[0].onerror!()
    await expect(p).resolves.toBeUndefined()
  })
})

describe('useVoice — kokoro backend', () => {
  it('falls back to speech with status error when the import throws', async () => {
    kokoroMode.fail = true
    const v = await load()
    const ok = await v.enableKokoro()
    expect(ok).toBe(false)
    expect(v.kokoroStatus.value).toBe('error')
    expect(v.backend.value).toBe('speech')
    expect(v.supported.value).toBe(true)
  })

  it('switches to kokoro when the model loads', async () => {
    const v = await load()
    const ok = await v.enableKokoro()
    expect(ok).toBe(true)
    expect(fromPretrained).toHaveBeenCalledWith('onnx-community/Kokoro-82M-v1.0-ONNX', { dtype: 'q8', device: 'wasm' })
    expect(v.kokoroStatus.value).toBe('ready')
    expect(v.backend.value).toBe('kokoro')
    v.disableKokoro()
    expect(v.backend.value).toBe('speech')
  })
})
