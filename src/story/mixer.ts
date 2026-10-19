import { scheduleScore } from './score'
import type { Timeline } from './storyBeats'
import { STEM_IDS, stemGain, autoValueAt, type Automation, type MixState, type SoundDesign, type StemId } from './trance'

/**
 * The trance mixer: one channel strip per stem —
 *
 *   input (stage/beat automation) → fader (mute · solo · comfort cap) → meter
 *
 * — summed into a gentle glue compressor, a brick-wall limiter and the
 * session fade. Live playback, the video export and the WAV mixdown all run
 * through this same graph, so what you hear is what you get.
 */

export interface Mixer {
  /** Where each stem of the score plugs in. */
  inputs: Record<StemId, GainNode>
  /** Post-master output. */
  output: AudioNode
  /** Move faders / mute / solo (smoothed, safe while playing). */
  setMix(mix: MixState, comfort: boolean): void
  /** Lay the stage/beat level curves onto the inputs from story time `fromMs`. */
  scheduleAutomation(auto: Automation, startAt: number, fromMs: number): void
  /** Fade in from silence and out to silence at the story's edges. */
  scheduleFade(durationMs: number, fadeS: number, startAt: number, fromMs: number): void
  /** Current post-fader level per stem, 0–1 (−60 dB … 0 dB). Empty without meters. */
  levels(): Partial<Record<StemId, number>>
  dispose(): void
}

export function createMixer(ctx: BaseAudioContext, { meters = false } = {}): Mixer {
  const glue = ctx.createDynamicsCompressor()
  glue.threshold.value = -18
  glue.knee.value = 12
  glue.ratio.value = 2.5
  glue.attack.value = 0.02
  glue.release.value = 0.35
  const limiter = ctx.createDynamicsCompressor()
  limiter.threshold.value = -1.5
  limiter.knee.value = 0
  limiter.ratio.value = 20
  limiter.attack.value = 0.003
  limiter.release.value = 0.12
  const fade = ctx.createGain()
  glue.connect(limiter).connect(fade)

  const inputs = {} as Record<StemId, GainNode>
  const faders = {} as Record<StemId, GainNode>
  const analysers: Partial<Record<StemId, AnalyserNode>> = {}
  for (const id of STEM_IDS) {
    const input = ctx.createGain()
    const fader = ctx.createGain()
    input.connect(fader).connect(glue)
    if (meters) {
      const an = ctx.createAnalyser()
      an.fftSize = 1024
      fader.connect(an)
      analysers[id] = an
    }
    inputs[id] = input
    faders[id] = fader
  }

  const scratch = new Float32Array(1024)

  return {
    inputs,
    output: fade,
    setMix(mix, comfort) {
      for (const id of STEM_IDS) {
        const g = stemGain(mix, id, comfort)
        if (ctx instanceof OfflineAudioContext) faders[id].gain.value = g
        else faders[id].gain.setTargetAtTime(g, ctx.currentTime, 0.04)
      }
    },
    scheduleAutomation(auto, startAt, fromMs) {
      for (const id of STEM_IDS) {
        const p = inputs[id].gain
        const pts = auto[id]
        p.cancelScheduledValues(0)
        p.setValueAtTime(autoValueAt(pts, fromMs), startAt)
        for (const pt of pts) {
          if (pt.tMs > fromMs) p.linearRampToValueAtTime(pt.v, startAt + (pt.tMs - fromMs) / 1000)
        }
      }
    },
    scheduleFade(durationMs, fadeS, startAt, fromMs) {
      const f = Math.min(fadeS, durationMs / 2000)
      const at = (s: number) => startAt + s - fromMs / 1000
      const env = (s: number) => Math.max(0, Math.min(1, s / f, (durationMs / 1000 - s) / f))
      const fromS = fromMs / 1000
      const g = fade.gain
      g.cancelScheduledValues(0)
      g.setValueAtTime(0, startAt)
      // A short ramp in when starting mid-story, so a seek never clicks.
      g.linearRampToValueAtTime(env(fromS), startAt + (fromS > 0 ? 0.08 : 0.001))
      if (fromS < f) g.linearRampToValueAtTime(1, at(f))
      const outS = durationMs / 1000 - f
      if (outS > fromS) g.setValueAtTime(1, at(outS))
      g.linearRampToValueAtTime(0, at(durationMs / 1000))
    },
    levels() {
      const out: Partial<Record<StemId, number>> = {}
      for (const id of STEM_IDS) {
        const an = analysers[id]
        if (!an) continue
        an.getFloatTimeDomainData(scratch)
        let sum = 0
        for (let i = 0; i < scratch.length; i++) sum += scratch[i] * scratch[i]
        const db = 20 * Math.log10(Math.sqrt(sum / scratch.length) + 1e-9)
        out[id] = Math.max(0, Math.min(1, (db + 60) / 60))
      }
      return out
    },
    dispose() {
      for (const id of STEM_IDS) {
        inputs[id].disconnect()
        faders[id].disconnect()
        analysers[id]?.disconnect()
      }
      glue.disconnect()
      limiter.disconnect()
      fade.disconnect()
    },
  }
}

export interface MixdownOptions {
  timeline: Timeline
  voices: (AudioBuffer | null)[]
  design: SoundDesign
  mix: MixState
  automation: Automation
  fadeS: number
  sampleRate?: number
}

/** Render the whole story through the mixer, offline, faster than real time. */
export async function renderMixdown({ timeline, voices, design, mix, automation, fadeS, sampleRate = 44100 }: MixdownOptions): Promise<AudioBuffer> {
  const ctx = new OfflineAudioContext(2, Math.ceil((timeline.durationMs / 1000) * sampleRate), sampleRate)
  const mixer = createMixer(ctx)
  mixer.output.connect(ctx.destination)
  mixer.setMix(mix, design.comfort)
  mixer.scheduleAutomation(automation, 0, 0)
  mixer.scheduleFade(timeline.durationMs, fadeS, 0, 0)
  scheduleScore(ctx, timeline, voices, mixer.inputs, { design, fromMs: 0, startAt: 0 })
  return ctx.startRendering()
}

/** 16-bit PCM WAV. */
export function encodeWav(buf: AudioBuffer): Blob {
  const ch = buf.numberOfChannels
  const n = buf.length
  const bytes = 44 + n * ch * 2
  const view = new DataView(new ArrayBuffer(bytes))
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)) }
  str(0, 'RIFF'); view.setUint32(4, bytes - 8, true); str(8, 'WAVE')
  str(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, ch, true)
  view.setUint32(24, buf.sampleRate, true); view.setUint32(28, buf.sampleRate * ch * 2, true)
  view.setUint16(32, ch * 2, true); view.setUint16(34, 16, true)
  str(36, 'data'); view.setUint32(40, n * ch * 2, true)
  const data = Array.from({ length: ch }, (_, c) => buf.getChannelData(c))
  let o = 44
  for (let i = 0; i < n; i++) {
    for (let c = 0; c < ch; c++) {
      const v = Math.max(-1, Math.min(1, data[c][i]))
      view.setInt16(o, v < 0 ? v * 0x8000 : v * 0x7fff, true)
      o += 2
    }
  }
  return new Blob([view], { type: 'audio/wav' })
}
