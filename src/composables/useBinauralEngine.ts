import { ref, readonly } from 'vue'

import {
  createBinauralPair, pinkNoiseBuffer, isochronicDepth, earFrequencies, type BinauralPair,
} from '@/audio/core'

// The isochronic rule lives in the shared audio core; re-exported for callers.
export { ISOCHRONIC_ABOVE_HZ, ISOCHRONIC_DEPTH, isochronicDepth } from '@/audio/core'

export type TextureId = 'noise' | 'pad' | 'shimmer'
export type TextureLevels = Record<TextureId, number> // 0..1 each

/** Peak gain of each texture at level 1, relative to the binaural pair. */
const TEXTURE_GAIN: Record<TextureId, number> = { noise: 0.35, pad: 0.45, shimmer: 0.08 }

/**
 * Raw Web Audio API binaural beat engine.
 *
 * Two sine oscillators (left / right channel) offset by `beatFreq` Hz.
 * The brain perceives the difference as a binaural beat at the gamma frequency.
 *
 *   L = carrier - beatFreq/2
 *   R = carrier + beatFreq/2
 *   Perceived beat = R - L = beatFreq
 */
class BinauralEngine {
  ctx: AudioContext | null = null
  pair: BinauralPair | null = null
  masterGain: GainNode | null = null
  /** Isochronic AM stage: gain = (1 - d/2) + (d/2)·sin(2π·beat·t). */
  pulseGain: GainNode | null = null
  pulseLfo: OscillatorNode | null = null
  pulseDepth: GainNode | null = null
  /** Texture bed under the beat: per-texture level gains + their sources. */
  textureGains: Partial<Record<TextureId, GainNode>> = {}
  textureSources: AudioScheduledSourceNode[] = []
  padOscs: OscillatorNode[] = []
  shimmerOscs: OscillatorNode[] = []
  analyser: AnalyserNode | null = null
  carrier = 220
  beatFreq = 40
  started = false
  /** True when we created our own AudioContext (so destroy() may close it). */
  ownsContext = true

  /**
   * @param externalCtx  When provided (e.g. Tone.js' shared rawContext), the
   *   oscillator graph is built inside that context so its output can be routed
   *   into other nodes in the same context — required for export capture. When
   *   omitted, the engine owns a fresh AudioContext (legacy behavior).
   */
  init(externalCtx?: AudioContext) {
    if (externalCtx) {
      this.ctx = externalCtx
      this.ownsContext = false
    } else {
      this.ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
      this.ownsContext = true
    }

    this.masterGain = this.ctx.createGain()
    this.masterGain.gain.value = 0.12

    this.analyser = this.ctx.createAnalyser()
    this.analyser.fftSize = 256

    this.pair = createBinauralPair(this.ctx, earFrequencies(this.carrier, this.beatFreq))

    // Isochronic stage between the stereo pair and the master volume. Starts
    // flat; only an explicit setBeat engages it (callers init at the 40 Hz
    // default and then ramp to their real beat).
    const depth = 0
    this.pulseGain = this.ctx.createGain()
    this.pulseGain.gain.value = 1 - depth / 2
    this.pulseLfo = this.ctx.createOscillator()
    this.pulseLfo.type = 'sine'
    this.pulseLfo.frequency.value = this.beatFreq
    this.pulseDepth = this.ctx.createGain()
    this.pulseDepth.gain.value = depth / 2
    this.pulseLfo.connect(this.pulseDepth)
    this.pulseDepth.connect(this.pulseGain.gain)

    this.pair.output.connect(this.pulseGain)
    this.pulseGain.connect(this.masterGain)
    this.buildTextures(this.ctx)
    this.masterGain.connect(this.analyser)
    this.analyser.connect(this.ctx.destination)

    this.pair.start()
    this.pulseLfo.start()
    for (const src of this.textureSources) src.start()
    this.started = true
  }

  /**
   * Texture bed, all silent until `setTextures` raises a level:
   *   noise   — pink noise through a 900 Hz lowpass (a soft "room")
   *   pad     — sub drone an octave under the carrier plus a fifth, breathing at 0.07 Hz
   *   shimmer — quiet high partials (carrier ×4, ×6) with a slow 0.2 Hz tremolo
   * Textures bypass the isochronic stage so only the beat itself pulses.
   */
  private buildTextures(ctx: AudioContext) {
    const level = (id: TextureId) => {
      const g = ctx.createGain()
      g.gain.value = 0
      g.connect(this.masterGain!)
      this.textureGains[id] = g
      return g
    }

    // Noise
    const noise = ctx.createBufferSource()
    noise.buffer = pinkNoiseBuffer(ctx)
    noise.loop = true
    const lp = ctx.createBiquadFilter()
    lp.type = 'lowpass'
    lp.frequency.value = 900
    noise.connect(lp)
    lp.connect(level('noise'))
    this.textureSources.push(noise)

    // Pad
    const padOut = level('pad')
    const breath = ctx.createGain()
    breath.gain.value = 0.75
    const breathLfo = ctx.createOscillator()
    breathLfo.frequency.value = 0.07
    const breathDepth = ctx.createGain()
    breathDepth.gain.value = 0.25
    breathLfo.connect(breathDepth)
    breathDepth.connect(breath.gain)
    const padLp = ctx.createBiquadFilter()
    padLp.type = 'lowpass'
    padLp.frequency.value = 400
    breath.connect(padLp)
    padLp.connect(padOut)
    for (const [ratio, detune, type] of [[0.5, -4, 'sine'], [0.5, 4, 'triangle'], [0.75, 0, 'sine']] as const) {
      const o = ctx.createOscillator()
      o.type = type
      o.frequency.value = this.carrier * ratio
      o.detune.value = detune
      const g = ctx.createGain()
      g.gain.value = ratio === 0.75 ? 0.4 : 0.6
      o.connect(g)
      g.connect(breath)
      this.padOscs.push(o)
      this.textureSources.push(o)
    }
    this.textureSources.push(breathLfo)

    // Shimmer
    const shimOut = level('shimmer')
    const trem = ctx.createGain()
    trem.gain.value = 0.6
    const tremLfo = ctx.createOscillator()
    tremLfo.frequency.value = 0.2
    const tremDepth = ctx.createGain()
    tremDepth.gain.value = 0.4
    tremLfo.connect(tremDepth)
    tremDepth.connect(trem.gain)
    trem.connect(shimOut)
    for (const ratio of [4, 6]) {
      const o = ctx.createOscillator()
      o.frequency.value = this.carrier * ratio
      o.detune.value = ratio === 6 ? 3 : -3
      o.connect(trem)
      this.shimmerOscs.push(o)
      this.textureSources.push(o)
    }
    this.textureSources.push(tremLfo)
  }

  setTextures(levels: Partial<TextureLevels>, rampTime = 0.8) {
    if (!this.ctx) return
    const now = this.ctx.currentTime
    for (const [id, v] of Object.entries(levels) as [TextureId, number][]) {
      const g = this.textureGains[id]
      if (!g) continue
      const target = Math.max(0, Math.min(1, v)) * TEXTURE_GAIN[id]
      g.gain.cancelScheduledValues(now)
      g.gain.setValueAtTime(g.gain.value, now)
      g.gain.linearRampToValueAtTime(target, now + rampTime)
    }
  }

  /** Send the engine's output to `node` instead of the speakers. */
  routeTo(node: AudioNode) {
    if (!this.analyser) return
    try { this.analyser.disconnect() } catch { /* ok */ }
    this.analyser.connect(node)
  }

  setBeat(beatHz: number, carrierHz?: number, rampTime = 1.5) {
    if (!this.started || !this.ctx || !this.pair) return
    const now = this.ctx.currentTime
    this.carrier = carrierHz ?? this.carrier
    this.beatFreq = beatHz
    this.pair.setBeat(beatHz, this.carrier, { kind: 'linear', seconds: rampTime })

    // Pad and shimmer follow the carrier so the bed stays consonant with the beat.
    const follow = (oscs: OscillatorNode[], ratios: number[]) => oscs.forEach((o, i) => {
      o.frequency.cancelScheduledValues(now)
      o.frequency.setValueAtTime(o.frequency.value, now)
      o.frequency.linearRampToValueAtTime(this.carrier * ratios[i], now + rampTime)
    })
    follow(this.padOscs, [0.5, 0.5, 0.75])
    follow(this.shimmerOscs, [4, 6])

    if (this.pulseLfo && this.pulseGain && this.pulseDepth) {
      const depth = isochronicDepth(beatHz)
      for (const [param, target] of [
        [this.pulseLfo.frequency, beatHz],
        [this.pulseGain.gain, 1 - depth / 2],
        [this.pulseDepth.gain, depth / 2],
      ] as [AudioParam, number][]) {
        param.cancelScheduledValues(now)
        param.setValueAtTime(param.value, now)
        param.linearRampToValueAtTime(target, now + rampTime)
      }
    }
  }

  setVolume(val: number) {
    if (!this.started || !this.masterGain || !this.ctx) return
    const now = this.ctx.currentTime
    this.masterGain.gain.cancelScheduledValues(now)
    this.masterGain.gain.setValueAtTime(this.masterGain.gain.value, now)
    this.masterGain.gain.linearRampToValueAtTime(val, now + 0.3)
  }

  getWaveformData(): Uint8Array | null {
    if (!this.analyser) return null
    const d = new Uint8Array(this.analyser.frequencyBinCount)
    this.analyser.getByteTimeDomainData(d)
    return d
  }

  destroy() {
    this.pair?.stop()
    try { this.pulseLfo?.stop() } catch { /* already stopped */ }
    for (const src of this.textureSources) {
      try { src.stop() } catch { /* already stopped */ }
    }
    // Detach from the graph. Only close the context if we own it — a shared
    // (Tone.js) context must outlive this engine.
    try { this.masterGain?.disconnect() } catch { /* ok */ }
    try { this.analyser?.disconnect() } catch { /* ok */ }
    if (this.ownsContext) {
      try { this.ctx?.close() } catch { /* already closed */ }
    }
    this.started = false
    this.ctx = null
    this.pair = null
    this.masterGain = null
    this.pulseGain = null
    this.pulseLfo = null
    this.pulseDepth = null
    this.textureGains = {}
    this.textureSources = []
    this.padOscs = []
    this.shimmerOscs = []
    this.analyser = null
  }
}

// ── Singleton ──
let engine: BinauralEngine | null = null
const initialized = ref(false)
const volume = ref(12)

export function useBinauralEngine() {
  function init(externalCtx?: AudioContext) {
    if (engine?.started) return
    engine = new BinauralEngine()
    engine.init(externalCtx)
    initialized.value = true
  }

  function setBeat(beatHz: number, carrierHz?: number, rampTime?: number) {
    engine?.setBeat(beatHz, carrierHz, rampTime)
  }

  function setTextures(levels: Partial<TextureLevels>, rampTime?: number) {
    engine?.setTextures(levels, rampTime)
  }

  function routeTo(node: AudioNode) {
    engine?.routeTo(node)
  }

  function setVolume(val: number) {
    volume.value = val
    engine?.setVolume(val / 100 * 0.25)
  }

  function getWaveformData(): Uint8Array | null {
    return engine?.getWaveformData() ?? null
  }

  /** The AudioContext the oscillator graph lives in (own or shared). */
  function getContext(): AudioContext | null {
    return engine?.ctx ?? null
  }

  /**
   * The engine's post-volume output node. Route this into an export
   * MediaStreamAudioDestinationNode (same context) to bake the beat into a file.
   */
  function getOutputNode(): AudioNode | null {
    return engine?.masterGain ?? null
  }

  function destroy() {
    engine?.destroy()
    engine = null
    initialized.value = false
  }

  return {
    initialized: readonly(initialized),
    volume,
    init,
    setBeat,
    setTextures,
    routeTo,
    setVolume,
    getWaveformData,
    getContext,
    getOutputNode,
    destroy,
  }
}
