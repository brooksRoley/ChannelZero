import { createBinauralPair, earFrequencies, pinkNoiseBuffer } from '@/audio/core'
import { GLIDE_MS, entrainmentAt, beatIndexAt, type StoryStage, type Timeline, type TimedBeat } from './storyBeats'
import {
  padCutoffHz, heartbeatTimes, cueEvents, HEART_DUB_MS, BOWL_PARTIALS, RISE_MS, PULSE_DEPTH, STAGE_ROOM,
  type SoundDesign, type StemId,
} from './trance'

/**
 * The story's score, scheduled into any audio context from any story time.
 *
 * The aim is entranced, euphoric ease — never pressure. So the bed is music,
 * not test tones: a warm, slowly breathing pad that moves through chords in a
 * single key as the stages change, a soft ocean of filtered noise, the
 * entrainment beat tucked underneath, a heartbeat that slows with the
 * listener, and a bowl that marks every deepening. The beds dip under the
 * voice so the story stays in front.
 *
 * Each layer goes to its own stem input (see mixer.ts), so it can be mixed
 * live. Scheduling (instead of rendering a buffer) means sound design changes
 * apply on the next play, seeking is free, and the same code renders the
 * offline WAV mixdown. The entrainment ramps are the same ones
 * `entrainmentAt` samples for overlay motion.
 */

/** Unity gain per stem — the level a fader at 1 delivers. */
const STEM_GAIN = { music: 0.22, waves: 0.5, binaural: 0.08, heart: 0.9, cues: 0.32 }

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
function lfo(ctx: BaseAudioContext, param: AudioParam, rateHz: number, depth: number, when: number, stopAt: number, track: Track) {
  const osc = ctx.createOscillator()
  osc.frequency.value = rateHz
  const g = ctx.createGain()
  g.gain.value = depth
  osc.connect(g).connect(param)
  osc.start(when)
  osc.stop(stopAt)
  track(osc)
}

type Track = (src: AudioScheduledSourceNode) => void

/** Peak of every voice clip together — one gain keeps their balance with the beds. */
const peakCache = new WeakMap<AudioBuffer, number>()
function bufferPeak(buf: AudioBuffer): number {
  let peak = peakCache.get(buf)
  if (peak != null) return peak
  peak = 0
  for (let ch = 0; ch < buf.numberOfChannels; ch++) {
    const d = buf.getChannelData(ch)
    for (let i = 0; i < d.length; i++) peak = Math.max(peak, Math.abs(d[i]))
  }
  peakCache.set(buf, peak)
  return peak
}

export function voiceGainFor(voices: (AudioBuffer | null)[]): number {
  const peak = Math.max(0, ...voices.map((v) => (v ? bufferPeak(v) : 0)))
  return peak > 1e-4 ? 0.85 / peak : 1
}

/** Mono voice samples → AudioBuffer (no context needed; resampled on play). */
export function voiceBuffer(audio: Float32Array, sampleRate: number): AudioBuffer {
  const buf = new AudioBuffer({ length: audio.length, sampleRate, numberOfChannels: 1 })
  buf.getChannelData(0).set(audio)
  return buf
}

export interface ScoreOptions {
  design: SoundDesign
  /** Story time to start from, ms. */
  fromMs?: number
  /** Context time at which `fromMs` sounds. */
  startAt: number
}

export interface ScoreHandle {
  stop(): void
}

/**
 * Schedule the whole score from `fromMs` into `inputs` (one node per stem).
 * Anything already over by `fromMs` is skipped; anything mid-way joins in.
 */
export function scheduleScore(
  ctx: BaseAudioContext,
  tl: Timeline,
  voices: (AudioBuffer | null)[],
  inputs: Record<StemId, AudioNode>,
  { design, fromMs = 0, startAt }: ScoreOptions,
): ScoreHandle {
  const now = startAt
  const at = (ms: number) => startAt + (ms - fromMs) / 1000
  const endS = at(tl.durationMs)
  const sources: AudioScheduledSourceNode[] = []
  const nodes: AudioNode[] = []
  const track: Track = (src) => { sources.push(src) }
  const keep = <N extends AudioNode>(n: N): N => { nodes.push(n); return n }
  const gain = (v: number) => { const g = keep(ctx.createGain()); g.gain.value = v; return g }
  const transpose = design.key

  // ── Ducking: the beds make room while the voice speaks ──
  const duck = (dest: AudioNode) => {
    const g = gain(1)
    const ws = duckWindows(tl)
    const inside = ws.find((w) => fromMs >= w.startMs && fromMs < w.endMs)
    g.gain.setValueAtTime(inside ? 0.5 : 1, now)
    for (const w of ws) {
      if (w.endMs <= fromMs) continue
      if (w.startMs > fromMs) g.gain.setTargetAtTime(0.5, at(w.startMs), 0.25)
      g.gain.setTargetAtTime(1, at(w.endMs), 0.9)
    }
    g.connect(dest)
    return g
  }

  // ── Music: warm low-passed chords in the chosen key, with room ──
  const padOut = gain(STEM_GAIN.music)
  padOut.connect(duck(inputs.music))
  const padRoom = keep(ctx.createConvolver())
  padRoom.buffer = roomImpulse(ctx)
  padRoom.connect(gain(0.35)).connect(padOut)
  const padLp = keep(ctx.createBiquadFilter())
  padLp.type = 'lowpass'
  padLp.frequency.value = padCutoffHz(design.warmth)
  padLp.Q.value = 0.3
  padLp.connect(padOut)
  padLp.connect(padRoom)
  const xfadeS = GLIDE_MS / 1000
  for (const seg of padSegments(tl)) {
    const a0 = at(seg.startMs) - xfadeS / 2
    const z = Math.min(endS, at(seg.endMs) + xfadeS / 2)
    if (z <= now) continue
    const xf = Math.min(xfadeS, (z - a0) / 2) // short segments get shorter fades, never inverted ones
    const a = Math.max(now, a0)
    const env = gain(0)
    env.connect(padLp)
    const inS = a0 >= now ? xf : 0.4
    env.gain.setValueAtTime(0, a)
    env.gain.linearRampToValueAtTime(1, seg.startMs === 0 && fromMs === 0 ? a + 0.01 : a + inS)
    if (z - xf > a + inS) env.gain.setValueAtTime(1, z - xf)
    env.gain.linearRampToValueAtTime(0, z)
    seg.chord.forEach((note, i) => {
      const level = 0.5 / (1 + i * 0.45) // top voices softer
      const g = gain(level * 0.75)
      lfo(ctx, g.gain, 0.05 + i * 0.017, level * 0.25, a, z + 0.05, track) // slow, independent swells
      g.connect(env)
      for (const [type, cents] of [['sine', -4], ['triangle', 5]] as const) {
        const o = ctx.createOscillator()
        o.type = type
        o.frequency.value = hz(note + transpose)
        o.detune.value = cents
        o.connect(gain(type === 'triangle' ? 0.35 : 1)).connect(g)
        o.start(a)
        o.stop(z + 0.05)
        track(o)
      }
    })
  }

  // ── Waves: dark pink noise swelling like a slow sea (~12 s per wave) ──
  const bed = ctx.createBufferSource()
  bed.buffer = pinkNoiseBuffer(ctx, { seconds: 8, channels: 2 })
  bed.loop = true
  const bedLp = keep(ctx.createBiquadFilter())
  bedLp.type = 'lowpass'
  bedLp.frequency.value = 520
  lfo(ctx, bedLp.frequency, 0.083, 180, now, endS, track)
  const swell = gain(0.7)
  lfo(ctx, swell.gain, 0.083, 0.3, now, endS, track)
  bed.connect(bedLp).connect(swell).connect(gain(STEM_GAIN.waves)).connect(duck(inputs.waves))
  bed.start(now)
  bed.stop(endS)
  track(bed)

  // ── Entrainment: binaural pair, isochronic swell, or both ──
  const binaural = design.entrainment !== 'isochronic'
  const pulse = design.entrainment !== 'binaural'
  const ears = (b: { carrierHz: number; beatHz: number }) => earFrequencies(b.carrierHz, binaural ? b.beatHz : 0)
  const e0 = entrainmentAt(tl, fromMs)
  const pair = createBinauralPair(ctx, ears(e0))
  const entOut = gain(STEM_GAIN.binaural)
  entOut.connect(duck(inputs.binaural))
  const am = gain(1)
  pair.output.connect(am).connect(entOut)
  let amRate: OscillatorNode | null = null
  if (pulse) {
    // A smooth sine swell at the beat rate — audible on speakers, never a hard pulse.
    const depth = design.comfort ? PULSE_DEPTH.comfort : PULSE_DEPTH.full
    am.gain.value = 1 - depth / 2
    amRate = ctx.createOscillator()
    amRate.frequency.value = e0.beatHz
    amRate.connect(gain(depth / 2)).connect(am.gain)
    amRate.start(now)
    amRate.stop(endS)
    track(amRate)
  }
  const glide = (param: AudioParam, pick: (b: TimedBeat) => number, current: number) => {
    param.setValueAtTime(current, now)
    for (let i = 1; i < tl.beats.length; i++) {
      const cur = tl.beats[i]
      const doneMs = cur.startMs + GLIDE_MS
      if (doneMs <= fromMs) continue
      if (cur.startMs >= fromMs) param.setValueAtTime(pick(tl.beats[i - 1]), at(cur.startMs))
      param.linearRampToValueAtTime(pick(cur), at(doneMs))
    }
  }
  glide(pair.left.frequency, (b) => ears(b).leftHz, ears(e0).leftHz)
  glide(pair.right.frequency, (b) => ears(b).rightHz, ears(e0).rightHz)
  if (amRate) glide(amRate.frequency, (b) => b.beatHz, e0.beatHz)
  pair.left.start(now)
  pair.right.start(now)
  pair.left.stop(endS)
  pair.right.stop(endS)
  track(pair.left)
  track(pair.right)

  // ── Heartbeat: lub-dub, slowing as the stages deepen ──
  const heartLp = keep(ctx.createBiquadFilter())
  heartLp.type = 'lowpass'
  heartLp.frequency.value = 140
  heartLp.connect(gain(STEM_GAIN.heart)).connect(inputs.heart)
  const attack = design.comfort ? 0.02 : 0.01
  const thump = (t: number, level: number) => {
    const o = ctx.createOscillator()
    o.frequency.setValueAtTime(64, t)
    o.frequency.exponentialRampToValueAtTime(40, t + 0.14)
    const env = gain(0)
    env.gain.setValueAtTime(0, t)
    env.gain.linearRampToValueAtTime(level, t + attack)
    env.gain.exponentialRampToValueAtTime(0.0005, t + 0.28)
    o.connect(env).connect(heartLp)
    o.start(t)
    o.stop(t + 0.3)
    track(o)
  }
  for (const ms of heartbeatTimes(tl)) {
    if (ms < fromMs) continue
    thump(at(ms), 1)
    thump(at(ms + HEART_DUB_MS), 0.6)
  }

  // ── Cues: a bowl on every deepening (the anchor), a rise into emerge and wake ──
  const cueOut = gain(STEM_GAIN.cues)
  cueOut.connect(inputs.cues)
  const cueRoom = keep(ctx.createConvolver())
  cueRoom.buffer = roomImpulse(ctx, 3.5)
  cueRoom.connect(gain(0.5)).connect(cueOut)
  const cueDry = gain(1)
  cueDry.connect(cueOut)
  cueDry.connect(cueRoom)
  const root = hz(62 + transpose) // the key's tonic, D4 by default
  for (const cue of cueEvents(tl)) {
    if (cue.atMs < fromMs) continue
    if (cue.kind === 'bowl') {
      const t = at(cue.atMs)
      for (const [ratio, level, decay] of BOWL_PARTIALS) {
        const env = gain(0)
        env.gain.setValueAtTime(0, t)
        env.gain.linearRampToValueAtTime(level, t + 0.025) // soft strike, no startle
        env.gain.exponentialRampToValueAtTime(0.0003, t + decay)
        env.connect(cueDry)
        for (const detune of [-1.2, 1.2]) { // the slow beating that makes a bowl sing
          const o = ctx.createOscillator()
          o.frequency.value = root * ratio + detune
          o.connect(gain(0.5)).connect(env)
          o.start(t)
          o.stop(t + decay + 0.1)
          track(o)
        }
      }
    } else {
      const peak = at(cue.atMs)
      const t0 = Math.max(now, peak - RISE_MS / 1000)
      const noise = ctx.createBufferSource()
      noise.buffer = pinkNoiseBuffer(ctx, { seconds: 2, channels: 2 })
      noise.loop = true
      const bp = keep(ctx.createBiquadFilter())
      bp.type = 'bandpass'
      bp.Q.value = 3
      bp.frequency.setValueAtTime(500, t0)
      bp.frequency.exponentialRampToValueAtTime(3200, peak)
      const env = gain(0)
      env.gain.setValueAtTime(0, t0)
      env.gain.linearRampToValueAtTime(0.9, peak)
      env.gain.setTargetAtTime(0, peak, 0.5)
      noise.connect(bp).connect(env).connect(cueDry)
      noise.start(t0)
      noise.stop(peak + 3)
      track(noise)
      // An open fifth in the key, rising with the shimmer.
      for (const n of [74, 81]) {
        const o = ctx.createOscillator()
        o.frequency.value = hz(n + transpose)
        const og = gain(0)
        og.gain.setValueAtTime(0, t0)
        og.gain.linearRampToValueAtTime(0.18, peak)
        og.gain.setTargetAtTime(0, peak, 0.8)
        o.connect(og).connect(cueDry)
        o.start(t0)
        o.stop(peak + 4)
        track(o)
      }
    }
  }

  // ── Voice: cleaned of rumble, in a room that closes in as trance deepens ──
  const voiceHp = keep(ctx.createBiquadFilter())
  voiceHp.type = 'highpass'
  voiceHp.frequency.value = 80
  const voiceOut = gain(voiceGainFor(voices))
  voiceHp.connect(voiceOut).connect(inputs.voice)
  const voiceRoom = keep(ctx.createConvolver())
  voiceRoom.buffer = roomImpulse(ctx)
  voiceRoom.connect(inputs.voice)
  const send = gain(0)
  voiceOut.connect(send).connect(voiceRoom)
  const roomFor = (stage: StoryStage) => 0.24 * design.room * STAGE_ROOM[stage]
  const bi = beatIndexAt(tl, fromMs)
  send.gain.setValueAtTime(bi >= 0 ? roomFor(tl.beats[bi].stage) : 0, now)
  tl.beats.forEach((beat, i) => {
    if (i > 0 && beat.startMs > fromMs && beat.stage !== tl.beats[i - 1].stage) {
      send.gain.setTargetAtTime(roomFor(beat.stage), at(beat.startMs), 1.5)
    }
    const buf = voices[i]
    if (!buf || !beat.voiced) return
    const endMs = beat.startMs + buf.duration * 1000
    if (endMs <= fromMs) return
    const src = ctx.createBufferSource()
    src.buffer = buf
    src.connect(voiceHp)
    if (beat.startMs >= fromMs) src.start(at(beat.startMs))
    else src.start(now, (fromMs - beat.startMs) / 1000)
    track(src)
  })

  return {
    stop() {
      for (const s of sources) {
        try { s.stop() } catch { /* not started */ }
        try { s.disconnect() } catch { /* already detached */ }
      }
      for (const n of nodes) {
        try { n.disconnect() } catch { /* already detached */ }
      }
    },
  }
}
