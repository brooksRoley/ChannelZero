import { ref, readonly } from 'vue'
import * as Tone from 'tone'

/**
 * Analyses a media element's audio in real-time.
 *
 * Routes the element through Tone.js's AudioContext via a MediaElementSource
 * and an AnalyserNode. Provides a smoothed amplitude envelope and a
 * speech-detection flag that external consumers (tone presets, visualizers)
 * can read per frame.
 *
 * MediaElementSource can only be created ONCE per element — a WeakMap
 * caches the source so re-connecting the same element reuses it.
 */

const envelope = ref(0)
const isSpeaking = ref(false)
const rawAmplitude = ref(0)

let analyserNode: AnalyserNode | null = null
let dataArray: Uint8Array | null = null
let smoothed = 0
let rafId: number | undefined

const sourceCache = new WeakMap<HTMLMediaElement, MediaElementAudioSourceNode>()

const ATTACK = 0.15
const RELEASE = 0.04
const THRESHOLD = 0.06

// External per-frame hook (called before refs update)
let frameHook: ((env: number, speaking: boolean) => void) | null = null

function tick() {
  if (!analyserNode || !dataArray) {
    rafId = requestAnimationFrame(tick)
    return
  }
  analyserNode.getByteTimeDomainData(dataArray)

  // RMS amplitude
  let sum = 0
  for (let i = 0; i < dataArray.length; i++) {
    const v = (dataArray[i] - 128) / 128
    sum += v * v
  }
  const rms = Math.sqrt(sum / dataArray.length)
  rawAmplitude.value = rms

  // Asymmetric envelope follower
  const target = Math.min(rms * 3.5, 1)
  smoothed += (target - smoothed) * (target > smoothed ? ATTACK : RELEASE)
  envelope.value = smoothed

  const speaking = smoothed > THRESHOLD
  isSpeaking.value = speaking

  frameHook?.(smoothed, speaking)

  rafId = requestAnimationFrame(tick)
}

export function useAudioSync() {
  /**
   * Connect an audio/video element for analysis.
   * Safe to call repeatedly with the same element. `destination` defaults to
   * the speakers.
   */
  async function connect(el: HTMLMediaElement, destination?: AudioNode): Promise<AnalyserNode> {
    await Tone.start()
    const ctx = Tone.getContext().rawContext as AudioContext

    // Reuse or create the source (one-time per element)
    let src = sourceCache.get(el)
    if (!src) {
      src = ctx.createMediaElementSource(el)
      sourceCache.set(el, src)
    } else {
      // Disconnect previous routing so we can rebuild cleanly
      try { src.disconnect() } catch { /* not connected */ }
    }

    analyserNode = ctx.createAnalyser()
    analyserNode.fftSize = 2048
    analyserNode.smoothingTimeConstant = 0.85
    dataArray = new Uint8Array(analyserNode.fftSize)

    src.connect(analyserNode)
    analyserNode.connect(destination ?? ctx.destination)

    // Start analysis loop
    if (rafId) cancelAnimationFrame(rafId)
    rafId = requestAnimationFrame(tick)

    return analyserNode
  }

  /** Stop the analysis loop. Does NOT dispose the source (can't re-create it). */
  function disconnect() {
    if (rafId) cancelAnimationFrame(rafId)
    rafId = undefined
    smoothed = 0
    envelope.value = 0
    isSpeaking.value = false
    rawAmplitude.value = 0
  }

  /** Register a callback fired every analysis frame (60 fps). */
  function onFrame(cb: (env: number, speaking: boolean) => void) {
    frameHook = cb
  }

  function getAnalyserNode(): AnalyserNode | null {
    return analyserNode
  }

  return {
    envelope: readonly(envelope),
    isSpeaking: readonly(isSpeaking),
    rawAmplitude: readonly(rawAmplitude),
    connect,
    disconnect,
    onFrame,
    getAnalyserNode,
  }
}
