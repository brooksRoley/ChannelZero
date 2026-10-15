/**
 * useHypnoAudit — admin tooling for checking the hypnosis / entrainment stack.
 *
 * Pure helpers (exported individually, unit-tested):
 *   - classifyBand / auditBinauralPair  — is a stereo pair actually a usable binaural beat?
 *   - findPeaks                          — sub-bin peak frequencies from an AnalyserNode spectrum
 *   - relativeLuminance / countFlashes   — WCAG 2.3.1-style general flash approximation
 *
 * Browser tools (returned by useHypnoAudit()):
 *   - playChannelCheck — 440 Hz tone in one ear, to confirm headphones / channel routing
 *   - measureEngineLayer — taps Tone's master output, splits L/R, and measures what the
 *     trance engine really emits for one binaural layer
 *   - scanFlashes — captures the current tab (getDisplayMedia) and measures luminance
 *     flashes inside a given element's rect
 */

import * as Tone from 'tone'
import { BINAURAL_LAYERS, useTranceEngine, type BinauralLayerSpec } from './useTranceEngine'
import { BANDS } from './useStudioBinaural'

// ── Bands ─────────────────────────────────────────────────────────────

export type Band = 'delta' | 'theta' | 'alpha' | 'beta' | 'gamma'

export function classifyBand(hz: number): Band {
  if (hz < 4) return 'delta'
  if (hz < 8) return 'theta'
  if (hz < 12) return 'alpha'
  if (hz <= 30) return 'beta'
  return 'gamma'
}

// ── Binaural spec audit ───────────────────────────────────────────────

export type CheckLevel = 'pass' | 'warn' | 'fail'

export interface AuditCheck {
  level: CheckLevel
  message: string
}

export interface BinauralPair {
  source: string
  label: string
  leftHz: number
  rightHz: number
  targetBand: Band
}

export interface BinauralAudit extends BinauralPair {
  carrierHz: number
  beatHz: number
  band: Band
  checks: AuditCheck[]
  worst: CheckLevel
}

export function auditBinauralPair(pair: BinauralPair): BinauralAudit {
  const beatHz = Math.abs(pair.rightHz - pair.leftHz)
  const carrierHz = (pair.leftHz + pair.rightHz) / 2
  const band = classifyBand(beatHz)
  const checks: AuditCheck[] = []

  if (band === pair.targetBand) {
    checks.push({ level: 'pass', message: `${beatHz.toFixed(2)} Hz beat is in the ${band} band as labelled` })
  } else {
    checks.push({ level: 'fail', message: `Labelled ${pair.targetBand} but a ${beatHz.toFixed(2)} Hz beat is ${band}` })
  }

  if (beatHz > 30) {
    checks.push({ level: 'warn', message: 'Beats above ~30 Hz are only weakly perceived binaurally; consider an isochronic or monaural pulse' })
  }

  if (carrierHz > 1000) {
    checks.push({ level: 'fail', message: `${carrierHz.toFixed(0)} Hz carrier: binaural beats fade out above ~1 kHz` })
  } else if (carrierHz > 500) {
    checks.push({ level: 'warn', message: `${carrierHz.toFixed(0)} Hz carrier is above the 100–500 Hz range where beats are strongest` })
  } else if (carrierHz < 90) {
    checks.push({ level: 'warn', message: `${carrierHz.toFixed(0)} Hz carrier is low enough that many headphones roll it off` })
  } else {
    checks.push({ level: 'pass', message: `${carrierHz.toFixed(1)} Hz carrier is in the 100–500 Hz range` })
  }

  const worst: CheckLevel = checks.some(c => c.level === 'fail')
    ? 'fail'
    : checks.some(c => c.level === 'warn') ? 'warn' : 'pass'

  return { ...pair, carrierHz, beatHz, band, checks, worst }
}

/** Every binaural pair the app ships, from both engines' exported specs. */
export function allBinauralPairs(): BinauralPair[] {
  const engine = Object.values(BINAURAL_LAYERS).map((l: BinauralLayerSpec) => ({
    source: 'Trance engine',
    label: l.label,
    leftHz: l.leftHz,
    rightHz: l.rightHz,
    targetBand: l.targetBand,
  }))
  const studio = (Object.entries(BANDS) as [Band, { beatHz: number; carrierHz: number }][]).map(([band, def]) => ({
    source: 'Glass studio',
    label: band[0].toUpperCase() + band.slice(1),
    leftHz: def.carrierHz - def.beatHz / 2,
    rightHz: def.carrierHz + def.beatHz / 2,
    targetBand: band,
  }))
  return [...engine, ...studio]
}

// ── Spectrum peaks ────────────────────────────────────────────────────

export interface Peak {
  hz: number
  db: number
}

/**
 * Local maxima of a dB spectrum (AnalyserNode.getFloatFrequencyData) between
 * minHz and maxHz, refined with parabolic interpolation so a 1.46 Hz bin
 * (fftSize 32768 @ 48 kHz) still resolves sub-Hz beat differences.
 */
export function findPeaks(
  spectrum: Float32Array,
  sampleRate: number,
  fftSize: number,
  minHz = 20,
  maxHz = 1200,
  count = 4,
  floorDb = -90,
): Peak[] {
  const binHz = sampleRate / fftSize
  const lo = Math.max(1, Math.floor(minHz / binHz))
  const hi = Math.min(spectrum.length - 2, Math.ceil(maxHz / binHz))
  const peaks: Peak[] = []
  for (let i = lo; i <= hi; i++) {
    const a = spectrum[i - 1], b = spectrum[i], c = spectrum[i + 1]
    if (b < floorDb || b < a || b < c) continue
    const denom = a - 2 * b + c
    const offset = denom === 0 ? 0 : 0.5 * (a - c) / denom
    peaks.push({ hz: (i + offset) * binHz, db: b - 0.25 * (a - c) * offset })
  }
  return peaks.sort((x, y) => y.db - x.db).slice(0, count)
}

// ── Flash safety ──────────────────────────────────────────────────────

/** WCAG relative luminance from 8-bit sRGB. */
export function relativeLuminance(r: number, g: number, b: number): number {
  const lin = (v: number) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
  }
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

export interface LumSample {
  t: number   // ms
  lum: number // 0–1 mean relative luminance of the region
}

export interface FlashResult {
  flashes: number
  maxPerSecond: number
  verdict: CheckLevel
}

/**
 * Approximates the WCAG 2.3.1 general flash rule over a region's mean luminance:
 * a transition is a swing of ≥ 0.1 relative luminance (with the darker side < 0.8)
 * against the previous extreme; a flash is a pair of opposing transitions.
 * More than 3 flashes in any 1 s window fails. Whole-region averaging
 * under-reports small flashing areas, so treat a pass as necessary, not sufficient.
 */
export function countFlashes(samples: LumSample[]): FlashResult {
  const transitions: number[] = []
  if (samples.length > 1) {
    let extreme = samples[0].lum
    let dir = 0 // +1 rising, -1 falling, 0 unknown
    for (const s of samples.slice(1)) {
      const delta = s.lum - extreme
      const darker = Math.min(s.lum, extreme)
      if (Math.abs(delta) >= 0.1 && darker < 0.8 && Math.sign(delta) !== dir) {
        transitions.push(s.t)
        dir = Math.sign(delta)
        extreme = s.lum
      } else if ((dir >= 0 && s.lum > extreme) || (dir <= 0 && s.lum < extreme)) {
        extreme = s.lum // keep tracking the current extreme
      }
    }
  }
  const flashes = Math.floor(transitions.length / 2)
  let maxPerSecond = 0
  for (let i = 0; i < transitions.length; i++) {
    let j = i
    while (j < transitions.length && transitions[j] - transitions[i] < 1000) j++
    maxPerSecond = Math.max(maxPerSecond, Math.floor((j - i) / 2))
  }
  const verdict: CheckLevel = maxPerSecond > 3 ? 'fail' : maxPerSecond === 3 ? 'warn' : 'pass'
  return { flashes, maxPerSecond, verdict }
}

// ── Browser tools ─────────────────────────────────────────────────────

export interface LayerMeasurement {
  layer: BinauralLayerSpec
  leftPeak: Peak | null
  rightPeak: Peak | null
  measuredBeatHz: number | null
  isolationDb: number | null // how far the left tone sits below its own level in the right channel
  checks: AuditCheck[]
}

const MEASURE_FFT = 32768

function nearest(peaks: Peak[], hz: number, tolerance = 3): Peak | null {
  const hit = peaks
    .filter(p => Math.abs(p.hz - hz) <= tolerance)
    .sort((a, b) => Math.abs(a.hz - hz) - Math.abs(b.hz - hz))[0]
  return hit ?? null
}

function levelAt(spectrum: Float32Array, hz: number, sampleRate: number): number {
  return spectrum[Math.round(hz / (sampleRate / MEASURE_FFT))]
}

export function useHypnoAudit() {
  const engine = useTranceEngine()

  async function playChannelCheck(side: 'left' | 'right', seconds = 1.2) {
    await Tone.start()
    const panner = new Tone.Panner(side === 'left' ? -1 : 1).toDestination()
    const osc = new Tone.Oscillator(440, 'sine').connect(panner)
    osc.volume.value = -18
    osc.start()
    osc.volume.rampTo(-80, 0.15, `+${seconds}`)
    osc.stop(`+${seconds + 0.2}`)
    setTimeout(() => { osc.dispose(); panner.dispose() }, (seconds + 0.5) * 1000)
  }

  const toggles: Record<BinauralLayerSpec['id'], { active: () => boolean; toggle: () => Promise<void> }> = {
    alpha:    { active: () => engine.alphaWaveActive.value, toggle: engine.toggleAlphaWave },
    theta:    { active: () => engine.thetaDreamActive.value, toggle: engine.toggleThetaDream },
    schumann: { active: () => engine.schumannActive.value,   toggle: engine.toggleSchumann },
  }

  /**
   * Turns one engine layer on (if it isn't already), listens to Tone's master
   * output split into L/R for `ms`, then restores the layer's previous state.
   */
  async function measureEngineLayer(id: BinauralLayerSpec['id'], ms = 2500): Promise<LayerMeasurement> {
    if (engine.sessionActive.value) throw new Error('Stop the running trance session before measuring')
    await Tone.start()
    const layer = BINAURAL_LAYERS[id]
    const ctx = Tone.getContext().rawContext as AudioContext
    const splitter = ctx.createChannelSplitter(2)
    const analysers = [ctx.createAnalyser(), ctx.createAnalyser()]
    analysers.forEach((a, ch) => {
      a.fftSize = MEASURE_FFT
      a.smoothingTimeConstant = 0.6
      splitter.connect(a, ch)
    })
    const destination = Tone.getDestination()
    destination.connect(splitter)

    const wasActive = toggles[id].active()
    if (!wasActive) await toggles[id].toggle()
    try {
      await new Promise(r => setTimeout(r, ms))
      const [left, right] = analysers.map(a => {
        const buf = new Float32Array(a.frequencyBinCount)
        a.getFloatFrequencyData(buf)
        return buf
      })
      const leftPeak = nearest(findPeaks(left, ctx.sampleRate, MEASURE_FFT, 20, 1200, 8), layer.leftHz)
      const rightPeak = nearest(findPeaks(right, ctx.sampleRate, MEASURE_FFT, 20, 1200, 8), layer.rightHz)
      const measuredBeatHz = leftPeak && rightPeak ? Math.abs(rightPeak.hz - leftPeak.hz) : null
      const isolationDb = leftPeak ? leftPeak.db - levelAt(right, layer.leftHz, ctx.sampleRate) : null
      const specBeat = Math.abs(layer.rightHz - layer.leftHz)

      const checks: AuditCheck[] = []
      if (!leftPeak || !rightPeak) {
        checks.push({ level: 'fail', message: `Expected tones not found (L ${layer.leftHz} Hz / R ${layer.rightHz} Hz); is the output muted?` })
      } else {
        const err = Math.abs((measuredBeatHz ?? 0) - specBeat)
        checks.push(err <= 0.5
          ? { level: 'pass', message: `Measured beat ${measuredBeatHz!.toFixed(2)} Hz matches spec ${specBeat.toFixed(2)} Hz` }
          : { level: 'fail', message: `Measured beat ${measuredBeatHz!.toFixed(2)} Hz is off spec ${specBeat.toFixed(2)} Hz by ${err.toFixed(2)} Hz` })
      }
      if (isolationDb !== null) {
        checks.push(isolationDb >= 20
          ? { level: 'pass', message: `Left tone is ${isolationDb.toFixed(0)} dB down in the right ear (channels are separated)` }
          : { level: 'fail', message: `Left tone leaks into the right ear (only ${isolationDb.toFixed(0)} dB down); the beat becomes monaural` })
      }
      return { layer, leftPeak, rightPeak, measuredBeatHz, isolationDb, checks }
    } finally {
      if (!wasActive && toggles[id].active()) await toggles[id].toggle()
      destination.disconnect(splitter)
      splitter.disconnect()
    }
  }

  /**
   * Records the current tab for `ms` and measures mean luminance inside `el`'s
   * rect at ~30 fps. The browser asks the admin to pick the tab to share.
   */
  async function scanFlashes(
    el: HTMLElement,
    ms = 6000,
    onSample?: (s: LumSample) => void,
  ): Promise<{ samples: LumSample[]; result: FlashResult }> {
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: 30 },
      audio: false,
      // Chrome-only hint; ignored elsewhere.
      preferCurrentTab: true,
    } as DisplayMediaStreamOptions)
    const video = document.createElement('video')
    video.muted = true
    video.srcObject = stream
    await video.play()

    const canvas = document.createElement('canvas')
    const ctx2d = canvas.getContext('2d', { willReadFrequently: true })!
    const samples: LumSample[] = []
    const start = performance.now()

    try {
      while (performance.now() - start < ms) {
        const rect = el.getBoundingClientRect()
        const sx = video.videoWidth / window.innerWidth
        const sy = video.videoHeight / window.innerHeight
        const w = 96, h = Math.max(1, Math.round(96 * rect.height / Math.max(1, rect.width)))
        canvas.width = w
        canvas.height = h
        ctx2d.drawImage(video, rect.left * sx, rect.top * sy, rect.width * sx, rect.height * sy, 0, 0, w, h)
        const px = ctx2d.getImageData(0, 0, w, h).data
        let sum = 0
        for (let i = 0; i < px.length; i += 4) sum += relativeLuminance(px[i], px[i + 1], px[i + 2])
        const sample = { t: performance.now() - start, lum: sum / (px.length / 4) }
        samples.push(sample)
        onSample?.(sample)
        await new Promise(r => setTimeout(r, 33))
      }
    } finally {
      stream.getTracks().forEach(t => t.stop())
    }
    return { samples, result: countFlashes(samples) }
  }

  return { playChannelCheck, measureEngineLayer, scanFlashes }
}
