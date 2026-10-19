import { createBinauralPair, earFrequencies, pinkNoiseBuffer } from '@/audio/core'
import { GLIDE_MS, type StoryStage, type Timeline } from './storyBeats'

/**
 * Renders a story's whole soundtrack offline into one AudioBuffer.
 *
 * The aim is entranced, euphoric ease — never pressure. So the bed is music,
 * not test tones: a warm, slowly breathing pad that moves through chords in a
 * single key as the stages change, a soft ocean of filtered noise, and the
 * binaural beat tucked underneath as an undercurrent rather than a lead.
 * Everything dips under the voice so the story stays in front, the voice
 * sits in a little room reverb, and the master is gently compressed and
 * normalised.
 *
 * Rendering offline (instead of mixing live) makes the result deterministic
 * and lets the timeline be built from the voice's real lengths. The binaural
 * ramps are the same ones `entrainmentAt` samples for overlay motion.
 */

export interface SoundtrackLevels {
  /** 0–1 user-facing mix amounts. */
  music: number
  waves: number
  binaural: number
}

export const DEFAULT_LEVELS: SoundtrackLevels = { music: 0.55, waves: 0.4, binaural: 0.3 }

/** Full-scale gains each 0–1 level maps onto. */
const MAX_GAIN = { music: 0.22, waves: 0.5, binaural: 0.08, voice: 1 }

export interface SoundtrackOptions {
  levels?: Partial<SoundtrackLevels>
  /** Fade in / out at the edges, seconds. */
  fadeS?: number
  sampleRate?: number
}

// ── Harmony ──────────────────────────────────────────────────────

const hz = (midi: number) => 440 * Math.pow(2, (midi - 69) / 12)

/**
 * One chord per stage, all diatonic to D major so every change is consonant:
 * Dmaj9 (home) → Bm9 (inward) → Gmaj9 (warm, deeper) → Em9 (floating rest).
 */
export const STAGE_CHORDS: Record<StoryStage, number[]> = {
  induce:   [50, 57, 66, 73, 76], // D3 A3 F#4 C#5 E5
  deepen:   [47, 54, 62, 69, 73], // B2 F#3 D4 A4 C#5
  emerge:   [50, 57, 66, 73, 76],
  reinduce: [43, 50, 59, 66, 69], // G2 D3 B3 F#4 A4
  final:    [40, 47, 55, 62, 66], // E2 B2 G3 D4 F#4
  wake:     [50, 57, 62, 66, 69, 76], // D major, open and bright
}

export interface PadSegment {
  chord: number[]
  startMs: number
  endMs: number
}

/** PURE: merge consecutive beats that share a chord into pad segments covering the whole story. */
export function padSegments(tl: Timeline): PadSegment[] {
  const segs: PadSegment[] = []
  tl.beats.forEach((b, i) => {
    const chord = STAGE_CHORDS[b.stage]
    const last = segs[segs.length - 1]
    if (last && last.chord === chord) last.endMs = b.endMs
    else segs.push({ chord, startMs: i === 0 ? 0 : b.startMs, endMs: b.endMs })
  })
  if (segs.length) segs[segs.length - 1].endMs = tl.durationMs
  return segs
}

/** PURE: when the voice is speaking (merged), so the music can make room. */
export function duckWindows(tl: Timeline, padMs = 300): { startMs: number; endMs: number }[] {
  const out: { startMs: number; endMs: number }[] = []
  for (const b of tl.beats) {
    if (!b.voiced) continue
    const w = { startMs: Math.max(0, b.startMs - padMs), endMs: b.bodyEndMs + padMs }
    const last = out[out.length - 1]
    if (last && w.startMs <= last.endMs) last.endMs = Math.max(last.endMs, w.endMs)
    else out.push(w)
  }
  return out
}

// ── Building blocks ──────────────────────────────────────────────

/** Soft stereo room: decaying noise, a short pre-delay, darker tail. */
function roomImpulse(ctx: BaseAudioContext, seconds = 2.6): AudioBuffer {
  const len = Math.floor(ctx.sampleRate * seconds)
  const pre = Math.floor(ctx.sampleRate * 0.02)
  const buf = ctx.createBuffer(2, len, ctx.sampleRate)
  for (let ch = 0; ch < 2; ch++) {
    const d = buf.getChannelData(ch)
    let lp = 0
    for (let i = pre; i < len; i++) {
      const t = (i - pre) / (len - pre)
      lp += 0.25 * ((Math.random() * 2 - 1) - lp) // gentle low-pass → warmer tail
      d[i] = lp * Math.pow(1 - t, 3.2)
    }
  }
  return buf
}

/** A slow sine LFO driving `param` by ±depth around its set value. */
function lfo(ctx: BaseAudioContext, param: AudioParam, rateHz: number, depth: number, phaseS = 0) {
  const osc = ctx.createOscillator()
  osc.frequency.value = rateHz
  const g = ctx.createGain()
  g.gain.value = depth
  osc.connect(g).connect(param)
  osc.start(phaseS)
}

/** One pad chord: each note a sine + soft triangle pair, slightly detuned, each breathing on its own. */
function schedulePadSegment(ctx: BaseAudioContext, seg: PadSegment, out: AudioNode, xfadeS: number, endS: number) {
  const env = ctx.createGain()
  env.connect(out)
  const t0 = seg.startMs / 1000
  const t1 = Math.min(endS, seg.endMs / 1000)
  const a = Math.max(0, t0 - xfadeS / 2)
  const z = Math.min(endS, t1 + xfadeS / 2)
  const xf = Math.min(xfadeS, (z - a) / 2) // short segments get shorter fades, never inverted ones
  env.gain.setValueAtTime(0, a)
  env.gain.linearRampToValueAtTime(1, a === 0 ? 0.01 : a + xf)
  env.gain.setValueAtTime(1, z - xf)
  env.gain.linearRampToValueAtTime(0, z)

  seg.chord.forEach((note, i) => {
    const level = 0.5 / (1 + i * 0.45) // top voices softer
    const g = ctx.createGain()
    g.gain.value = level * 0.75
    lfo(ctx, g.gain, 0.05 + i * 0.017, level * 0.25, a) // slow, independent swells
    g.connect(env)
    for (const [type, cents] of [['sine', -4], ['triangle', 5]] as const) {
      const o = ctx.createOscillator()
      o.type = type
      o.frequency.value = hz(note)
      o.detune.value = cents
      const og = ctx.createGain()
      og.gain.value = type === 'triangle' ? 0.35 : 1
      o.connect(og).connect(g)
      o.start(a)
      o.stop(z + 0.05)
    }
  })
}

// ── Render ───────────────────────────────────────────────────────

/** Mono voice samples → AudioBuffer (no context needed; resampled on render). */
export function voiceBuffer(audio: Float32Array, sampleRate: number): AudioBuffer {
  const buf = new AudioBuffer({ length: audio.length, sampleRate, numberOfChannels: 1 })
  buf.getChannelData(0).set(audio)
  return buf
}

/** Peak-normalise in place to `target` (never boosts silence). */
function normalise(buf: AudioBuffer, target = 0.89) {
  let peak = 0
  for (let ch = 0; ch < buf.numberOfChannels; ch++) {
    const d = buf.getChannelData(ch)
    for (let i = 0; i < d.length; i++) peak = Math.max(peak, Math.abs(d[i]))
  }
  if (peak < 1e-4) return
  const k = target / peak
  for (let ch = 0; ch < buf.numberOfChannels; ch++) {
    const d = buf.getChannelData(ch)
    for (let i = 0; i < d.length; i++) d[i] *= k
  }
}

export async function renderSoundtrack(
  tl: Timeline,
  voices: (AudioBuffer | null)[],
  { levels, fadeS = 3, sampleRate = 48000 }: SoundtrackOptions = {},
): Promise<AudioBuffer> {
  const lv = { ...DEFAULT_LEVELS, ...levels }
  const durS = tl.durationMs / 1000
  const ctx = new OfflineAudioContext(2, Math.ceil(durS * sampleRate), sampleRate)

  // ── Master: gentle glue compression → session fade ──
  const fade = ctx.createGain()
  fade.connect(ctx.destination)
  const f = Math.min(fadeS, durS / 2)
  fade.gain.setValueAtTime(0, 0)
  fade.gain.linearRampToValueAtTime(1, f)
  fade.gain.setValueAtTime(1, durS - f)
  fade.gain.linearRampToValueAtTime(0, durS)
  const comp = ctx.createDynamicsCompressor()
  comp.threshold.value = -18
  comp.knee.value = 12
  comp.ratio.value = 2.5
  comp.attack.value = 0.02
  comp.release.value = 0.35
  comp.connect(fade)

  const reverb = ctx.createConvolver()
  reverb.buffer = roomImpulse(ctx)
  reverb.connect(comp)

  // ── Music bus (pad + waves + binaural), ducked under the voice ──
  const music = ctx.createGain()
  music.connect(comp)
  music.gain.setValueAtTime(1, 0)
  for (const w of duckWindows(tl)) {
    music.gain.setTargetAtTime(0.5, w.startMs / 1000, 0.25)
    music.gain.setTargetAtTime(1, w.endMs / 1000, 0.9)
  }

  // Pad — warm low-passed chords, with a generous reverb send.
  const padLp = ctx.createBiquadFilter()
  padLp.type = 'lowpass'
  padLp.frequency.value = 1300
  padLp.Q.value = 0.3
  const padGain = ctx.createGain()
  padGain.gain.value = MAX_GAIN.music * lv.music
  padLp.connect(padGain)
  padGain.connect(music)
  const padSend = ctx.createGain()
  padSend.gain.value = 0.35
  padGain.connect(padSend).connect(reverb)
  for (const seg of padSegments(tl)) schedulePadSegment(ctx, seg, padLp, GLIDE_MS / 1000, durS)

  // Waves — dark pink noise swelling like a slow sea (~12 s per wave).
  const bed = ctx.createBufferSource()
  bed.buffer = pinkNoiseBuffer(ctx, { seconds: 8, channels: 2 })
  bed.loop = true
  const bedLp = ctx.createBiquadFilter()
  bedLp.type = 'lowpass'
  bedLp.frequency.value = 520
  lfo(ctx, bedLp.frequency, 0.083, 180)
  const swell = ctx.createGain()
  swell.gain.value = 0.7
  lfo(ctx, swell.gain, 0.083, 0.3)
  const bedGain = ctx.createGain()
  bedGain.gain.value = MAX_GAIN.waves * lv.waves
  bed.connect(bedLp).connect(swell).connect(bedGain).connect(music)
  bed.start(0)

  // Binaural undercurrent, scheduled beat by beat.
  const first = tl.beats[0]
  const start = earFrequencies(first?.carrierHz ?? 210, first?.beatHz ?? 10)
  const pair = createBinauralPair(ctx, start)
  const binGain = ctx.createGain()
  binGain.gain.value = MAX_GAIN.binaural * lv.binaural
  pair.output.connect(binGain).connect(music)
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

  // ── Voice: cleaned of rumble, a touch of room ──
  const voiceHp = ctx.createBiquadFilter()
  voiceHp.type = 'highpass'
  voiceHp.frequency.value = 80
  const voiceGain = ctx.createGain()
  voiceGain.gain.value = MAX_GAIN.voice
  voiceHp.connect(voiceGain).connect(comp)
  const voiceSend = ctx.createGain()
  voiceSend.gain.value = 0.12
  voiceGain.connect(voiceSend).connect(reverb)
  tl.beats.forEach((beat, i) => {
    const buf = voices[i]
    if (!buf || !beat.voiced) return
    const src = ctx.createBufferSource()
    src.buffer = buf
    src.connect(voiceHp)
    src.start(beat.startMs / 1000)
  })

  const rendered = await ctx.startRendering()
  normalise(rendered)
  return rendered
}
