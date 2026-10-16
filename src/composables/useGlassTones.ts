import { ref, readonly } from 'vue'
import * as Tone from 'tone'
import { createBinauralPair, earFrequencies } from '@/audio/core'

/**
 * Tone.js synthesis presets designed to sit beneath speech.
 *
 * Each preset creates a small audio graph and exposes an `update()` method
 * driven by the real-time amplitude envelope from useAudioSync.  The
 * presets swell during pauses and recede during speech so they support
 * rather than compete with the voice.
 *
 * All presets route through a shared raw GainNode (`master`) which
 * connects to both the live destination and — during export — an
 * additional MediaStreamAudioDestinationNode.
 */

export type TonePreset =
  | 'none'
  | 'warmDrone'
  | 'binauralTheta'
  | 'oceanWash'
  | 'subPulse'
  | 'crystalShimmer'

export const PRESET_LABELS: Record<TonePreset, string> = {
  none: 'None',
  warmDrone: 'Warm Drone',
  binauralTheta: 'Binaural \u03B8',
  oceanWash: 'Ocean Wash',
  subPulse: 'Sub Pulse',
  crystalShimmer: 'Crystal',
}

interface PresetEngine {
  start(): void
  stop(): void
  update(env: number, speaking: boolean): void
  dispose(): void
}

// ── Shared master gain (raw AudioNode) ─────────────────────────────
let masterGain: GainNode | null = null

function getMaster(): GainNode {
  if (!masterGain) {
    const ctx = Tone.getContext().rawContext as AudioContext
    masterGain = ctx.createGain()
    masterGain.gain.value = 0.5
    masterGain.connect(ctx.destination)
  }
  return masterGain
}

// ── Preset factories ───────────────────────────────────────────────

/** Low detuned sine pair — louder during pauses, filter follows speech. */
function createWarmDrone(): PresetEngine {
  const osc1 = new Tone.Oscillator({ frequency: 110, type: 'sine' })
  const osc2 = new Tone.Oscillator({ frequency: 110.8, type: 'sine' })
  const filter = new Tone.Filter({ frequency: 350, type: 'lowpass', rolloff: -24 })
  const gain = new Tone.Gain(0)

  osc1.connect(filter)
  osc2.connect(filter)
  filter.connect(gain)
  gain.connect(getMaster())

  return {
    start() { osc1.start(); osc2.start() },
    stop()  { osc1.stop(); osc2.stop() },
    update(env, speaking) {
      gain.gain.rampTo(speaking ? 0.04 : 0.12 - env * 0.04, 0.08)
      filter.frequency.rampTo(180 + env * 500, 0.1)
    },
    dispose() { osc1.dispose(); osc2.dispose(); filter.dispose(); gain.dispose() },
  }
}

/** 6 Hz theta binaural beat — calms during speech, opens in silence. */
function createBinauralTheta(): PresetEngine {
  const ctx = Tone.getContext().rawContext as AudioContext
  const pair = createBinauralPair(ctx, earFrequencies(200, 6)) // 197 / 203 Hz
  const out = ctx.createGain()
  out.gain.value = 0
  pair.output.connect(out)
  out.connect(getMaster())

  return {
    start() { pair.start() },
    stop()  { pair.stop() },
    update(env, speaking) {
      const now = ctx.currentTime
      out.gain.linearRampToValueAtTime(speaking ? 0.06 : 0.14, now + 0.06)
    },
    dispose() {
      pair.dispose()
      out.disconnect()
    },
  }
}

/** Pink noise through a breathing bandpass — opens in pauses. */
function createOceanWash(): PresetEngine {
  const noise = new Tone.Noise('pink')
  const filter = new Tone.Filter({ frequency: 600, type: 'bandpass', Q: 1.5 })
  const gain = new Tone.Gain(0)

  noise.connect(filter)
  filter.connect(gain)
  gain.connect(getMaster())

  return {
    start() { noise.start() },
    stop()  { noise.stop() },
    update(env, speaking) {
      gain.gain.rampTo(speaking ? 0.02 : 0.10, 0.15)
      filter.frequency.rampTo(speaking ? 300 : 800 + (1 - env) * 600, 0.2)
    },
    dispose() { noise.dispose(); filter.dispose(); gain.dispose() },
  }
}

/** Deep 55 Hz sine that pulses with speech rhythm. */
function createSubPulse(): PresetEngine {
  const osc = new Tone.Oscillator({ frequency: 55, type: 'sine' })
  const gain = new Tone.Gain(0)
  osc.connect(gain)
  gain.connect(getMaster())

  let phase = 0

  return {
    start() { osc.start() },
    stop()  { osc.stop() },
    update(env) {
      phase += 0.02
      gain.gain.rampTo(env * 0.15 * (Math.sin(phase) * 0.5 + 0.5), 0.05)
    },
    dispose() { osc.dispose(); gain.dispose() },
  }
}

/** Reverbed high tones triggered in speech pauses. */
function createCrystalShimmer(): PresetEngine {
  const synth = new Tone.Synth({
    oscillator: { type: 'sine' },
    envelope: { attack: 0.3, decay: 1.5, sustain: 0, release: 2 },
  })
  const reverb = new Tone.Reverb({ decay: 4, wet: 0.8 })
  const gain = new Tone.Gain(0.08)

  synth.connect(reverb)
  reverb.connect(gain)
  gain.connect(getMaster())

  let lastTrigger = 0
  const notes = ['C5', 'E5', 'G5', 'B5', 'D6', 'A5']
  let idx = 0

  return {
    start() { /* triggered on demand */ },
    stop()  { /* no continuous oscillator */ },
    update(env, speaking) {
      const now = Date.now()
      if (!speaking && env < 0.04 && now - lastTrigger > 2500) {
        synth.triggerAttackRelease(notes[idx % notes.length], '8n')
        idx++
        lastTrigger = now
      }
    },
    dispose() { synth.dispose(); reverb.dispose(); gain.dispose() },
  }
}

// ── Preset map ─────────────────────────────────────────────────────
const FACTORIES: Record<string, () => PresetEngine> = {
  warmDrone: createWarmDrone,
  binauralTheta: createBinauralTheta,
  oceanWash: createOceanWash,
  subPulse: createSubPulse,
  crystalShimmer: createCrystalShimmer,
}

// ── Public singleton ───────────────────────────────────────────────
const activePreset = ref<TonePreset>('none')
let engine: PresetEngine | null = null

export function useGlassTones() {
  async function setPreset(preset: TonePreset) {
    if (engine) { engine.stop(); engine.dispose(); engine = null }
    activePreset.value = preset
    if (preset === 'none') return

    await Tone.start()
    const factory = FACTORIES[preset]
    if (!factory) return
    engine = factory()
    engine.start()
  }

  /** Call every frame with the current audio envelope. */
  function update(env: number, speaking: boolean) {
    engine?.update(env, speaking)
  }

  function dispose() {
    if (engine) { engine.stop(); engine.dispose(); engine = null }
    activePreset.value = 'none'
  }

  /** Returns the raw GainNode all presets route through (for export mixing). */
  function getMasterNode(): GainNode {
    return getMaster()
  }

  return {
    activePreset: readonly(activePreset),
    setPreset,
    update,
    dispose,
    getMasterNode,
  }
}
