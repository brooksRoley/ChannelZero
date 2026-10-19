import { ref, computed, readonly } from 'vue'

// ── Guided voice composable ────────────────────────────────────────
// Sequencing-friendly speech for hypnosis lines: `say(text)` resolves
// when the line has FINISHED (or was cancelled / errored), so a state
// machine can simply `await say(...)` between beats. It never rejects
// and never hangs — every line carries a safety timeout.
//
// Backends:
//   • 'speech' (default) — Web Speech API, built into the browser.
//   • 'kokoro' (opt-in)  — kokoro-js, an 82M-param neural TTS that runs
//     fully in the browser (ONNX/WASM, no server, no paid API). Enabling
//     it downloads the model once (~90 MB, q8) into the browser cache;
//     later sessions load from cache. It is never loaded unless
//     `enableKokoro()` is called, and lives in its own lazy chunk.

export type VoiceBackend = 'speech' | 'kokoro'
export type KokoroStatus = 'off' | 'downloading' | 'ready' | 'error'

// ── Tuning ─────────────────────────────────────────────────────────

const SPEECH_RATE = 0.85
const SPEECH_PITCH = 0.9
const PREFERRED_VOICE_NAMES = ['Natural', 'Google', 'Samantha', 'Daniel']

const KOKORO_MODEL_ID = 'onnx-community/Kokoro-82M-v1.0-ONNX'
/** af_heart — warm, soft American English female; the model's top-graded voice. */
const KOKORO_VOICE = 'af_heart'
const KOKORO_SPEED = 0.9

/** Safety timeout: ~40 ms per character + 4 s (covers Chrome's missing onend). */
export function safetyTimeoutMs(text: string): number {
  return text.length * 40 + 4000
}
/** Upper bound on neural generation before falling back to speech. */
function generationTimeoutMs(text: string): number {
  return 20000 + text.length * 50
}

// ── Minimal kokoro-js surface we use (keeps the import type-only) ──

export interface KokoroAudio {
  audio: Float32Array
  sampling_rate: number
}
interface KokoroInstance {
  generate(text: string, opts: { voice: string; speed?: number }): Promise<KokoroAudio>
}

// ── Module-level singleton state ───────────────────────────────────

const backend = ref<VoiceBackend>('speech')
const kokoroStatus = ref<KokoroStatus>('off')
const speechAvailable = ref(hasSpeech())

let kokoro: KokoroInstance | null = null
let audioCtx: AudioContext | null = null
let currentSource: AudioBufferSourceNode | null = null
let currentFinish: (() => void) | null = null
/** Bumped on every say()/cancel() so stale async work can bail out. */
let generation = 0

function hasSpeech(): boolean {
  return (
    typeof window !== 'undefined' &&
    'speechSynthesis' in window &&
    typeof (globalThis as { SpeechSynthesisUtterance?: unknown }).SpeechSynthesisUtterance === 'function'
  )
}

const supported = computed(() => speechAvailable.value || kokoroStatus.value === 'ready')

// ── Speech backend ─────────────────────────────────────────────────

function pickVoice(): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices?.() ?? []
  const english = voices.filter((v) => v.lang?.toLowerCase().startsWith('en'))
  for (const name of PREFERRED_VOICE_NAMES) {
    const hit = english.find((v) => v.name.includes(name))
    if (hit) return hit
  }
  return english[0] ?? null
}

function speakWithSpeech(text: string, finish: () => void): void {
  speechAvailable.value = hasSpeech()
  if (!speechAvailable.value) {
    finish()
    return
  }
  try {
    const u = new SpeechSynthesisUtterance(text)
    u.rate = SPEECH_RATE
    u.pitch = SPEECH_PITCH
    const voice = pickVoice()
    if (voice) {
      u.voice = voice
      u.lang = voice.lang
    } else {
      u.lang = 'en-US'
    }
    u.onend = () => finish()
    u.onerror = () => finish()
    window.speechSynthesis.speak(u)
  } catch {
    finish()
  }
}

// ── Kokoro backend ─────────────────────────────────────────────────

function getAudioContext(): AudioContext {
  if (!audioCtx) {
    const Ctor =
      window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    audioCtx = new Ctor()
  }
  if (audioCtx.state === 'suspended') void audioCtx.resume()
  return audioCtx
}

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error('timeout')), ms)
    p.then(
      (v) => { clearTimeout(t); resolve(v) },
      (e) => { clearTimeout(t); reject(e) },
    )
  })
}

async function speakWithKokoro(text: string, finish: () => void, token: number): Promise<void> {
  let raw: KokoroAudio
  try {
    raw = await withTimeout(kokoro!.generate(text, { voice: KOKORO_VOICE, speed: KOKORO_SPEED }), generationTimeoutMs(text))
  } catch (err) {
    if (token !== generation) return
    console.warn('[useVoice] kokoro generation failed, using speech for this line', err)
    speakWithSpeech(text, finish)
    return
  }
  if (token !== generation) return // cancelled while generating

  try {
    const ctx = getAudioContext()
    const buffer = ctx.createBuffer(1, raw.audio.length, raw.sampling_rate)
    buffer.getChannelData(0).set(raw.audio)
    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(ctx.destination)
    source.onended = () => {
      if (currentSource === source) currentSource = null
      finish()
    }
    currentSource = source
    source.start()
  } catch (err) {
    console.warn('[useVoice] kokoro playback failed', err)
    finish()
  }
}

// ── Public API ─────────────────────────────────────────────────────

/** Stop whatever is speaking and resolve any pending `say()`. */
function cancel(): void {
  generation++
  if (currentSource) {
    const src = currentSource
    currentSource = null
    try { src.onended = null; src.stop() } catch { /* already stopped */ }
  }
  if (hasSpeech()) {
    try { window.speechSynthesis.cancel() } catch { /* ignore */ }
  }
  const finish = currentFinish
  currentFinish = null
  finish?.()
}

/**
 * Speak one line. Resolves when it has finished, been cancelled, errored,
 * or hit the safety timeout. A new `say()` interrupts the previous line.
 */
function say(text: string): Promise<void> {
  cancel()
  const token = generation
  const line = text.trim()
  if (!line) return Promise.resolve()

  return new Promise<void>((resolve) => {
    let done = false
    let safety: ReturnType<typeof setTimeout> | null = null
    const finish = () => {
      if (done) return
      done = true
      if (safety) clearTimeout(safety)
      if (currentFinish === finish) currentFinish = null
      resolve()
    }
    currentFinish = finish

    const armSafety = (ms: number) => {
      if (safety) clearTimeout(safety)
      safety = setTimeout(() => {
        // Chrome sometimes drops onend (or stalls on long lines) — move on.
        if (token === generation && hasSpeech()) {
          try { window.speechSynthesis.cancel() } catch { /* ignore */ }
        }
        finish()
      }, ms)
    }

    if (backend.value === 'kokoro' && kokoro) {
      // Generation time is bounded separately; arm the playback timer once audio exists.
      void speakWithKokoro(line, finish, token).then(() => {
        if (!done) {
          const dur = currentSource?.buffer ? currentSource.buffer.duration * 1000 + 2000 : 0
          armSafety(Math.max(dur, safetyTimeoutMs(line)))
        }
      })
    } else {
      armSafety(safetyTimeoutMs(line))
      speakWithSpeech(line, finish)
    }
  })
}

/**
 * Render one line to raw samples with the local neural voice, without playing
 * it — for offline mixing (story export). Web Speech can't be captured, so
 * this returns null unless Kokoro is ready, or if generation fails.
 */
async function synthesize(text: string): Promise<KokoroAudio | null> {
  const line = text.trim()
  if (!line || !kokoro || kokoroStatus.value !== 'ready') return null
  try {
    return await withTimeout(kokoro.generate(line, { voice: KOKORO_VOICE, speed: KOKORO_SPEED }), generationTimeoutMs(line))
  } catch (err) {
    console.warn('[useVoice] kokoro synthesis failed', err)
    return null
  }
}

/**
 * Opt in to the local neural voice. Lazily imports kokoro-js and downloads
 * the model (~90 MB once, then browser-cached). Returns false and stays on
 * Web Speech if anything fails.
 */
async function enableKokoro(): Promise<boolean> {
  if (kokoro) {
    kokoroStatus.value = 'ready'
    backend.value = 'kokoro'
    return true
  }
  kokoroStatus.value = 'downloading'
  try {
    const { KokoroTTS } = await import('kokoro-js')
    const tts = await KokoroTTS.from_pretrained(KOKORO_MODEL_ID, { dtype: 'q8', device: 'wasm' })
    kokoro = tts as unknown as KokoroInstance
    kokoroStatus.value = 'ready'
    backend.value = 'kokoro'
    return true
  } catch (err) {
    console.warn('[useVoice] kokoro unavailable, staying on Web Speech', err)
    kokoroStatus.value = 'error'
    backend.value = 'speech'
    return false
  }
}

/** Return to Web Speech. The loaded model stays in memory for quick re-enable. */
function disableKokoro(): void {
  if (backend.value === 'kokoro') cancel()
  backend.value = 'speech'
}

export function useVoice() {
  return {
    say,
    cancel,
    synthesize,
    backend: readonly(backend),
    kokoroStatus: readonly(kokoroStatus),
    supported,
    enableKokoro,
    disableKokoro,
  }
}
