/**
 * Shared raw Web Audio primitives for every entrainment experience.
 *
 * The experiences stay deliberately different — the studio glides beats
 * linearly, the adaptive journey eases toward targets, the learn animation
 * lets you drag each ear's tone — so this module only owns the parts that were
 * copy-pasted between them: the stereo tone pair, the pink-noise generator and
 * the isochronic rule. Each caller keeps its own levels, ramps and context.
 */

// ── Isochronic rule ──────────────────────────────────────────────

/**
 * Above this beat rate binaural beats are only weakly perceived, so engines
 * add an isochronic pulse: amplitude-modulating the carrier at the beat rate,
 * which is audible at any frequency and without headphones.
 */
export const ISOCHRONIC_ABOVE_HZ = 30

/** AM depth (0–1) applied when the isochronic pulse is engaged. */
export const ISOCHRONIC_DEPTH = 0.8

/** PURE: pulse depth for a beat rate (0 = pure binaural). */
export function isochronicDepth(beatHz: number): number {
  return beatHz > ISOCHRONIC_ABOVE_HZ ? ISOCHRONIC_DEPTH : 0
}

/** PURE: left / right ear frequencies for a carrier and beat. */
export function earFrequencies(carrierHz: number, beatHz: number): { leftHz: number; rightHz: number } {
  return { leftHz: carrierHz - beatHz / 2, rightHz: carrierHz + beatHz / 2 }
}

// ── Pink noise ───────────────────────────────────────────────────

/**
 * A looping buffer of pink noise (Paul Kellet's refined filter). Each channel
 * is generated independently, so a stereo buffer is decorrelated and wide.
 */
export function pinkNoiseBuffer(
  ctx: BaseAudioContext,
  { seconds = 4, channels = 1, level = 0.11 }: { seconds?: number; channels?: number; level?: number } = {},
): AudioBuffer {
  const len = Math.floor(ctx.sampleRate * seconds)
  const buf = ctx.createBuffer(channels, len, ctx.sampleRate)
  for (let ch = 0; ch < channels; ch++) {
    const d = buf.getChannelData(ch)
    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0
    for (let i = 0; i < len; i++) {
      const w = Math.random() * 2 - 1
      b0 = 0.99886 * b0 + w * 0.0555179
      b1 = 0.99332 * b1 + w * 0.0750759
      b2 = 0.969 * b2 + w * 0.153852
      b3 = 0.8665 * b3 + w * 0.3104856
      b4 = 0.55 * b4 + w * 0.5329522
      b5 = -0.7616 * b5 - w * 0.016898
      d[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * level
      b6 = w * 0.115926
    }
  }
  return buf
}

// ── Binaural pair ────────────────────────────────────────────────

export type Glide =
  | { kind: 'linear'; seconds: number } // reaches the target exactly at `seconds`
  | { kind: 'target'; timeConstant: number } // exponential ease, never overshoots

export interface BinauralPair {
  /** Stereo output (L = channel 0, R = channel 1), before any volume stage. */
  output: AudioNode
  left: OscillatorNode
  right: OscillatorNode
  start(): void
  /** Move both ears to a carrier ± beat/2. */
  setBeat(beatHz: number, carrierHz: number, glide?: Glide): void
  /** Move each ear independently (the learn animation's sliders). */
  setEars(leftHz: number, rightHz: number, glide?: Glide): void
  stop(): void
  dispose(): void
}

function glideTo(param: AudioParam, value: number, ctx: BaseAudioContext, glide: Glide) {
  const now = ctx.currentTime
  if (glide.kind === 'target') {
    param.setTargetAtTime(value, now, glide.timeConstant)
    return
  }
  param.cancelScheduledValues(now)
  param.setValueAtTime(param.value, now)
  param.linearRampToValueAtTime(value, now + glide.seconds)
}

/**
 * Two sine oscillators hard-panned to separate ears through a channel merger,
 * so the beat forms in the listener's head rather than in the air.
 */
export function createBinauralPair(
  ctx: BaseAudioContext,
  { leftHz, rightHz, type = 'sine' }: { leftHz: number; rightHz: number; type?: OscillatorType },
): BinauralPair {
  const merger = ctx.createChannelMerger(2)
  const left = ctx.createOscillator()
  const right = ctx.createOscillator()
  left.type = right.type = type
  left.frequency.value = leftHz
  right.frequency.value = rightHz
  left.connect(merger, 0, 0)
  right.connect(merger, 0, 1)

  let started = false
  return {
    output: merger,
    left,
    right,
    start() {
      if (started) return
      left.start()
      right.start()
      started = true
    },
    setBeat(beatHz, carrierHz, glide = { kind: 'linear', seconds: 1.5 }) {
      const { leftHz, rightHz } = earFrequencies(carrierHz, beatHz)
      glideTo(left.frequency, leftHz, ctx, glide)
      glideTo(right.frequency, rightHz, ctx, glide)
    },
    setEars(l, r, glide = { kind: 'target', timeConstant: 0.05 }) {
      glideTo(left.frequency, l, ctx, glide)
      glideTo(right.frequency, r, ctx, glide)
    },
    stop() {
      try { left.stop() } catch { /* not started / already stopped */ }
      try { right.stop() } catch { /* not started / already stopped */ }
    },
    dispose() {
      this.stop()
      try { left.disconnect(); right.disconnect(); merger.disconnect() } catch { /* already detached */ }
    },
  }
}
