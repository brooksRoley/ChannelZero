import { createBinauralPair, earFrequencies, pinkNoiseBuffer } from '@/audio/core'
import { GLIDE_MS, type Timeline } from './storyBeats'

/**
 * Renders a story's whole soundtrack offline into one AudioBuffer:
 * voice lines at their beat starts, a binaural pair gliding beat-to-beat, and
 * a soft pink-noise bed, under a session fade.
 *
 * Rendering offline (instead of mixing live) makes the result deterministic
 * and lets the timeline be built from the voice's real lengths. The binaural
 * ramps are the same ones `entrainmentAt` samples for overlay motion.
 */

export interface SoundtrackLevels {
  voice: number
  binaural: number
  bed: number
}

export const DEFAULT_LEVELS: SoundtrackLevels = { voice: 0.9, binaural: 0.16, bed: 0.35 }

export interface SoundtrackOptions {
  levels?: Partial<SoundtrackLevels>
  /** Fade in / out at the edges, seconds. */
  fadeS?: number
  sampleRate?: number
}

/** Mono voice samples → AudioBuffer (no context needed; resampled on render). */
export function voiceBuffer(audio: Float32Array, sampleRate: number): AudioBuffer {
  const buf = new AudioBuffer({ length: audio.length, sampleRate, numberOfChannels: 1 })
  buf.getChannelData(0).set(audio)
  return buf
}

export async function renderSoundtrack(
  tl: Timeline,
  voices: (AudioBuffer | null)[],
  { levels, fadeS = 3, sampleRate = 48000 }: SoundtrackOptions = {},
): Promise<AudioBuffer> {
  const lv = { ...DEFAULT_LEVELS, ...levels }
  const durS = tl.durationMs / 1000
  const ctx = new OfflineAudioContext(2, Math.ceil(durS * sampleRate), sampleRate)

  // ── Master + session fade ──
  const master = ctx.createGain()
  master.connect(ctx.destination)
  const f = Math.min(fadeS, durS / 2)
  master.gain.setValueAtTime(0, 0)
  master.gain.linearRampToValueAtTime(1, f)
  master.gain.setValueAtTime(1, durS - f)
  master.gain.linearRampToValueAtTime(0, durS)

  // ── Binaural pair, scheduled beat by beat ──
  const first = tl.beats[0]
  const start = earFrequencies(first?.carrierHz ?? 210, first?.beatHz ?? 10)
  const pair = createBinauralPair(ctx, start)
  const binGain = ctx.createGain()
  binGain.gain.value = lv.binaural
  pair.output.connect(binGain).connect(master)
  pair.left.frequency.setValueAtTime(start.leftHz, 0)
  pair.right.frequency.setValueAtTime(start.rightHz, 0)
  for (let i = 1; i < tl.beats.length; i++) {
    const prev = tl.beats[i - 1]
    const cur = tl.beats[i]
    const from = earFrequencies(prev.carrierHz, prev.beatHz)
    const to = earFrequencies(cur.carrierHz, cur.beatHz)
    const t0 = cur.startMs / 1000
    const t1 = (cur.startMs + GLIDE_MS) / 1000
    pair.left.frequency.setValueAtTime(from.leftHz, t0)
    pair.left.frequency.linearRampToValueAtTime(to.leftHz, t1)
    pair.right.frequency.setValueAtTime(from.rightHz, t0)
    pair.right.frequency.linearRampToValueAtTime(to.rightHz, t1)
  }
  pair.start()

  // ── Pink-noise bed (stereo, decorrelated, warm) ──
  const bed = ctx.createBufferSource()
  bed.buffer = pinkNoiseBuffer(ctx, { seconds: 6, channels: 2 })
  bed.loop = true
  const lp = ctx.createBiquadFilter()
  lp.type = 'lowpass'
  lp.frequency.value = 900
  const bedGain = ctx.createGain()
  bedGain.gain.value = lv.bed
  bed.connect(lp).connect(bedGain).connect(master)
  bed.start(0)

  // ── Voice ──
  const voiceGain = ctx.createGain()
  voiceGain.gain.value = lv.voice
  voiceGain.connect(master)
  tl.beats.forEach((beat, i) => {
    const buf = voices[i]
    if (!buf || !beat.voiced) return
    const src = ctx.createBufferSource()
    src.buffer = buf
    src.connect(voiceGain)
    src.start(beat.startMs / 1000)
  })

  return ctx.startRendering()
}
