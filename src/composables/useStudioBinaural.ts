import { ref, readonly } from 'vue'
import * as Tone from 'tone'
import { useBinauralEngine } from './useBinauralEngine'
import type { Band, BinauralConfig } from './studioTypes'

/**
 * Glass Studio — binaural entrainment layer.
 *
 * Wraps the raw `useBinauralEngine` (dual-oscillator L/R pair) with the curated
 * band presets + journey scheduler the studio exposes. No raw carrier/beat
 * sliders — the user picks a band or sequences a journey, and this composable
 * maps that to `setBeat(beatHz, carrierHz, ramp)`.
 *
 * Export capture: the engine is built inside Tone.js' shared AudioContext (see
 * `start()`), so `getOutputNode()` can be routed into the export
 * MediaStreamAudioDestinationNode — which is also created from Tone's context.
 * Web Audio nodes only connect within one context, so sharing Tone's context is
 * what makes the beat land in the exported file.
 *
 * See docs/superpowers/specs/2026-08-04-glass-studio-subliminal-design.md
 */

export interface BandDef {
  beatHz: number
  carrierHz: number
  label: string
  /** 1–2 honest sentences drawn from the learn.ts framing. */
  blurb: string
  /** Slug of the deep-dive /learn article. */
  learnSlug: string
}

// BANDS (beat Hz @ carrier Hz): delta 2@180, theta 6@200, alpha 10@210,
// beta 18@220, gamma 40@220. Blurbs stay measured — matching learn.ts, which is
// candid that the evidence for entrainment is mixed.
export const BANDS: Record<Band, BandDef> = {
  delta: {
    beatHz: 2,
    carrierHz: 180,
    label: 'Delta',
    blurb:
      'Delta (0.5–4 Hz) is the band of deep sleep and unconscious processing. Sessions tend to be short — at this rate the brain genuinely tries to sleep.',
    learnSlug: 'targeting-brainwave-states',
  },
  theta: {
    beatHz: 6,
    carrierHz: 200,
    label: 'Theta',
    blurb:
      'Theta (4–8 Hz) is the workhorse of meditation and hypnotic depth — slow enough to settle into, still conscious. It has the steadiest support of any band, mostly for relaxation.',
    learnSlug: 'targeting-brainwave-states',
  },
  alpha: {
    beatHz: 10,
    carrierHz: 210,
    label: 'Alpha',
    blurb:
      'Alpha (8–12 Hz) is relaxed wakefulness — a good band for calm focus, creative work, or as a settling phase before descending into theta.',
    learnSlug: 'targeting-brainwave-states',
  },
  beta: {
    beatHz: 18,
    carrierHz: 220,
    label: 'Beta',
    blurb:
      'Beta (13–30 Hz) tracks active, alert thinking. It is occasionally used for alertness, though the entrainment case here is weak — plain caffeine usually does the same job.',
    learnSlug: 'targeting-brainwave-states',
  },
  gamma: {
    beatHz: 40,
    carrierHz: 220,
    label: 'Gamma',
    blurb:
      'Gamma (30 Hz and up) is associated with sustained focus and binding. The claims here are the most speculative of the bands — treat it as an auditory anchor, not a guarantee.',
    learnSlug: 'targeting-brainwave-states',
  },
}

/** A single resolved journey phase on the media timeline (seconds). */
export interface JourneyPhase {
  band: Band
  beatHz: number
  carrierHz: number
  startS: number
  endS: number
}

// ── Pure journey math (unit-tested) ────────────────────────────────

/**
 * Resolve a journey (bands + relative durations) onto an absolute timeline that
 * fills `totalS`. Durations are scaled proportionally so the last phase ends at
 * `totalS`. If `totalS` is unknown (0), the authored durations are used as-is.
 */
export function fitJourney(
  phases: { band: Band; durationS: number }[],
  totalS: number,
): JourneyPhase[] {
  if (!phases.length) return []
  const durs = phases.map((p) => Math.max(0.5, p.durationS))
  const sum = durs.reduce((a, b) => a + b, 0)
  const scale = totalS > 0 && sum > 0 ? totalS / sum : 1

  let acc = 0
  return phases.map((p, i) => {
    const startS = acc
    acc += durs[i] * scale
    const b = BANDS[p.band]
    return { band: p.band, beatHz: b.beatHz, carrierHz: b.carrierHz, startS, endS: acc }
  })
}

/** Index of the phase active at time `tS`, or -1 if the plan is empty. */
export function phaseAtTime(plan: JourneyPhase[], tS: number): number {
  if (!plan.length) return -1
  if (tS < plan[0].startS) return 0
  for (let i = 0; i < plan.length; i++) {
    if (tS >= plan[i].startS && tS < plan[i].endS) return i
  }
  return plan.length - 1 // past the end → hold last phase
}

// ── Composable ─────────────────────────────────────────────────────

/**
 * @param output  Optional node to send the engine into instead of the speakers
 *   (Glass Studio's session bus, so one fade/export tap covers every source).
 */
export function useStudioBinaural(config: BinauralConfig, output?: () => AudioNode | null) {
  const engine = useBinauralEngine()

  /** The beat currently playing (Hz). Read by preview/export for motion sync. */
  const activeBeatHz = ref(0)
  const running = ref(false)

  let mediaDurationS = 0
  let journeyPlan: JourneyPhase[] = []
  let lastPhaseIdx = -1

  const RAMP_S = 2 // beat glide at journey transitions / preset changes

  /** Ensure Tone's shared context exists and build the engine inside it. */
  async function ensureEngine() {
    await Tone.start()
    const ctx = Tone.getContext().rawContext as AudioContext
    engine.init(ctx) // no-op if already started
    const out = output?.()
    if (out) engine.routeTo(out)
  }

  function applyTextures() {
    engine.setTextures(config.textures ?? { noise: 0, pad: 0, shimmer: 0 })
  }

  function applyPreset(band: Band) {
    config.band = band
    const b = BANDS[band]
    engine.setBeat(b.beatHz, b.carrierHz, 1.5)
    activeBeatHz.value = b.beatHz
  }

  function rebuildJourney() {
    journeyPlan = fitJourney(config.journey, mediaDurationS)
    lastPhaseIdx = -1
  }

  /**
   * Advance the journey to the phase for `currentTimeS` (drive from media
   * currentTime). Only fires `setBeat` when the phase actually changes.
   */
  function tickJourney(currentTimeS: number) {
    if (!running.value || config.mode !== 'journey' || !journeyPlan.length) return
    const idx = phaseAtTime(journeyPlan, currentTimeS)
    if (idx === lastPhaseIdx) return
    lastPhaseIdx = idx
    const p = journeyPlan[idx]
    engine.setBeat(p.beatHz, p.carrierHz, RAMP_S)
    activeBeatHz.value = p.beatHz
  }

  /** Media duration is needed to auto-fit journey phases. */
  function setMediaDuration(durationS: number) {
    mediaDurationS = isFinite(durationS) ? durationS : 0
    if (running.value && config.mode === 'journey') rebuildJourney()
  }

  function setVolume(v: number) {
    config.volume = v
    engine.setVolume(v)
  }

  /** Re-apply texture levels only (no beat re-ramp, journey keeps its place). */
  function updateTextures() {
    if (running.value) applyTextures()
  }

  /** Apply the current config to a running engine (mode / band / journey edits). */
  function refresh() {
    if (!running.value) return
    engine.setVolume(config.volume)
    applyTextures()
    if (config.mode === 'preset') {
      applyPreset(config.band)
    } else {
      rebuildJourney()
      // Re-seat onto the current media position on the next tick; seed phase 0
      // immediately so there's always a beat.
      tickJourney(0)
    }
  }

  /** Start the beat (init in Tone's context + apply current config). */
  async function start() {
    await ensureEngine()
    engine.setVolume(config.volume)
    applyTextures()
    running.value = true
    if (config.mode === 'preset') {
      applyPreset(config.band)
    } else {
      rebuildJourney()
      lastPhaseIdx = -1
      tickJourney(0)
    }
  }

  /** Silence the beat but keep the graph (so the output node stays valid). */
  function stop() {
    running.value = false
    engine.setVolume(0)
  }

  function getContext(): AudioContext | null {
    return engine.getContext()
  }

  function getOutputNode(): AudioNode | null {
    return engine.getOutputNode()
  }

  function destroy() {
    engine.destroy()
    running.value = false
    activeBeatHz.value = 0
    journeyPlan = []
    lastPhaseIdx = -1
  }

  return {
    activeBeatHz: readonly(activeBeatHz),
    running: readonly(running),
    BANDS,
    start,
    stop,
    applyPreset,
    refresh,
    updateTextures,
    tickJourney,
    setMediaDuration,
    setVolume,
    getContext,
    getOutputNode,
    destroy,
  }
}
