import { ref, computed, readonly } from 'vue'
import * as Tone from 'tone'
import { useAuthStore } from './useAuthStore'

export type TrancePhase = 'idle' | 'induction' | 'coherence' | 'deepen' | 'joy' | 'wake'

// ── Singleton reactive state ──
const phase = ref<TrancePhase>('idle')
const sessionActive = ref(false)
const coherenceScore = ref(0)
const progress = ref(0)
const syncCount = ref(0)
const isExpanding = ref(false)
const currentInstruction = ref('')
const isSyncing = ref(false)
const tunnelPulseStrength = ref(0)

// Post-session data for overlay (captured before stopSession clears state)
export interface CompletedSessionData {
  coherence: number
  syncCount: number
  sessionDurationMs: number
  dominantPhase: string
}
const completedSession = ref<CompletedSessionData | null>(null)

// Feature module states
const baselineModulatorActive = ref(false)
const ptosisInducerActive = ref(false)
const avSyncActive = ref(false)
const alphaWaveActive = ref(false)
const thetaDreamActive = ref(false)
const schumannActive = ref(false)
const solfeggioActive = ref(false)
const gammaPulseActive = ref(false)

const BREATH_CYCLE = 10
const INHALE_TIME = 5

// ── Audio node refs (not reactive, module-level singletons) ──
let audioReady = false
let osc: Tone.Oscillator | null = null
let lfo: Tone.LFO | null = null
let gainNode: Tone.Gain | null = null
let subBass: Tone.Synth | null = null
let deepenLoop: Tone.Loop | null = null
let swellOsc: Tone.Oscillator | null = null
let swellGain: Tone.Gain | null = null
let coherenceLoopId: number | undefined
let syncStartTime = 0
let sessionStartTime = 0
let phaseTimer: ReturnType<typeof setTimeout> | null = null
let phraseTimers: ReturnType<typeof setTimeout>[] = []

// External-driver mode (fractionation): when autoAdvance is false no phase
// schedules the next one; when phrasesEnabled is false the built-in phrase
// sequences stay silent so an outside voice can speak instead.
let autoAdvance = true
let phrasesEnabled = true
// Depth set by an external driver (0..1) — offsets the binaural balance.
let depthLevel = 0

// ── Guided phrase sequences ──────────────────────────────────────
const INDUCTION_PHRASES = [
  'Find a comfortable position...',
  'Close your eyes...',
  'Take a deep breath in...',
  'And slowly release...',
  'Feel the weight of your body...',
  'Sinking... with each breath...',
  'The sound carries you...',
  'You are safe here...',
  'Nothing to do...',
  'Just this moment...',
]

const DEEPEN_PHRASES = [
  'Deeper now...',
  'Further in...',
  'Let it take you...',
  'Surrender to the rhythm...',
  'Falling... softly...',
  'The pulse is yours...',
  'Nothing left to hold...',
  'Just the frequency...',
]

const JOY_PHRASES = [
  'A warmth begins...',
  'Spreading outward...',
  'A quiet joy...',
  'Let it fill you...',
  'You carry this with you...',
  'It is always here...',
]

const WAKE_PHRASES = [
  'Ten... feel this stillness...',
  'Eight... awareness returning...',
  'Six... breath deepening...',
  'Four... body beginning to stir...',
  'Two... gently returning...',
  'One... open your eyes...',
]

function clearPhraseTimers() {
  phraseTimers.forEach(clearTimeout)
  phraseTimers = []
}

function schedulePhrases(phrases: string[], intervalMs: number, onComplete?: () => void) {
  clearPhraseTimers()
  phraseTimers = phrases.map((text, i) =>
    setTimeout(() => {
      currentInstruction.value = text
      if (i === phrases.length - 1) onComplete?.()
    }, i * intervalMs)
  )
}

// Runs a phase's phrases (if enabled) and then `next` (if autoAdvance).
// With phrases off, `next` still fires after the same duration.
function runPhrasesThen(phrases: string[], intervalMs: number, next: () => void) {
  if (phrasesEnabled) {
    schedulePhrases(phrases, intervalMs, autoAdvance ? next : undefined)
  } else {
    clearPhraseTimers()
    if (autoAdvance) phaseTimer = setTimeout(next, (phrases.length - 1) * intervalMs)
  }
}

function clearPhaseTimer() {
  if (phaseTimer) { clearTimeout(phaseTimer); phaseTimer = null }
}

// Module 1: 2.4 Hz Baseline Modulator
let bmCarrier: Tone.Oscillator | null = null
let bmPulse: Tone.LFO | null = null

// Module 2: 0.5 Hz Ptosis Inducer
let piFilter: Tone.Filter | null = null
let piNoise: Tone.Noise | null = null
let piLFO: Tone.LFO | null = null

// Module 3: Synchronized AV Entrainment
let avSynth: Tone.Synth | null = null
let avVisualCallback: ((flash: boolean) => void) | null = null
let avLoopId: number | undefined

// Modules 4–6: binaural layers (alpha 10 Hz, theta 6 Hz, Schumann 7.83 Hz).
// One Tone voice per active layer — same shape, different spec (BINAURAL_LAYERS).
interface BinauralVoice {
  left: Tone.Oscillator
  right: Tone.Oscillator
  panL: Tone.Panner
  panR: Tone.Panner
}
const binauralVoices: Partial<Record<'alpha' | 'theta' | 'schumann', BinauralVoice>> = {}

// Module 7: Solfeggio 528 Hz ("miracle tone" — restoration, DNA repair)
let solOsc: Tone.Oscillator | null = null
let solGain: Tone.Gain | null = null
let solLfo: Tone.LFO | null = null

// Module 8: Gamma Pulse (40 Hz isochronic — audible without headphones)
let gammaOsc: Tone.Oscillator | null = null
let gammaGain: Tone.Gain | null = null
let gammaLfo: Tone.LFO | null = null
let gammaFade: Tone.Gain | null = null

// ── Phase-aware layer balance ─────────────────────────────────────
// Defines per-phase dB levels for each entrainment layer and the Nerve Pulse
// LFO frequency. Binaural layers are staggered so only one is dominant per
// phase; the others act as harmonics rather than competing targets.
interface LayerBalance {
  alpha: number      // alpha voice volume dB — dominant during induction/coherence
  theta: number      // theta voice volume dB — dominant during deepen
  schumann: number   // schumann voice volume dB — dominant during joy
  baselineVol: number // bmCarrier.volume additive offset (LFO adds to this)
  baselineHz: number  // bmPulse.frequency — ramps down with session depth
}

const PHASE_BALANCE: Partial<Record<TrancePhase, LayerBalance>> = {
  //             alpha   theta   schumann  bVol  bHz
  induction: {   alpha: -18, theta: -30, schumann: -32, baselineVol:  -8, baselineHz: 4.0 },
  coherence: {   alpha: -20, theta: -22, schumann: -28, baselineVol:  -8, baselineHz: 4.0 },
  deepen:    {   alpha: -30, theta: -16, schumann: -26, baselineVol:  -4, baselineHz: 2.4 },
  joy:       {   alpha: -28, theta: -22, schumann: -18, baselineVol: -16, baselineHz: 2.0 },
  wake:      {   alpha: -40, theta: -40, schumann: -40, baselineVol: -30, baselineHz: 1.5 },
}

// dB offset from external depth: theta rises, alpha recedes as depth → 1
function depthOffsetDb(id: BinauralLayerSpec['id']): number {
  if (id === 'theta') return 6 * depthLevel
  if (id === 'alpha') return -6 * depthLevel
  return 0
}

function applyPhaseLayerBalance(p: TrancePhase, ramp = 6) {
  const b = PHASE_BALANCE[p]
  if (!b) return
  for (const [id, v] of Object.entries(binauralVoices) as [keyof typeof binauralVoices, BinauralVoice][]) {
    v.left.volume.rampTo(b[id] + depthOffsetDb(id), ramp)
    v.right.volume.rampTo(b[id] + depthOffsetDb(id), ramp)
  }
  if (bmCarrier) bmCarrier.volume.rampTo(b.baselineVol, ramp)
  if (bmPulse)   bmPulse.frequency.rampTo(b.baselineHz, ramp)
}

function phaseVol(key: keyof Omit<LayerBalance, 'baselineVol' | 'baselineHz'>, fallback = -18): number {
  return (PHASE_BALANCE[phase.value]?.[key] ?? fallback) + depthOffsetDb(key)
}

// ── Core audio setup ──
function initCoreAudio() {
  if (audioReady) return
  osc = new Tone.Oscillator(200, 'sine').start()
  gainNode = new Tone.Gain(0).toDestination()
  lfo = new Tone.LFO(12, 190, 210).connect(osc.frequency).start()
  osc.connect(gainNode)

  subBass = new Tone.Synth({
    oscillator: { type: 'sine' },
    envelope: { attack: 0.01, decay: 0.3, sustain: 0, release: 0.5 }
  }).toDestination()
  subBass.volume.value = -6
  audioReady = true
}

// ── Module 1: 2.4 Hz Baseline Modulator ──
// Carrier at 432 Hz with amplitude modulated at 2.4 Hz (square wave)
// to excite nervous system resonance
async function startBaselineModulator() {
  await Tone.start()
  if (bmCarrier) return
  bmCarrier = new Tone.Oscillator(432, 'sine').toDestination()
  // Base volume is the phase-appropriate offset; LFO adds ±12 dB swing on top
  bmCarrier.volume.value = PHASE_BALANCE[phase.value]?.baselineVol ?? -8
  // Sine LFO for smooth amplitude swell; frequency matches current phase depth
  const initHz = PHASE_BALANCE[phase.value]?.baselineHz ?? 2.4
  bmPulse = new Tone.LFO({ frequency: initHz, type: 'sine', min: -28, max: -4 }).start()
  bmPulse.connect(bmCarrier.volume)
  bmCarrier.start()
  baselineModulatorActive.value = true
}

function stopBaselineModulator() {
  if (!bmCarrier) return
  bmCarrier.stop()
  bmCarrier.dispose()
  bmPulse?.dispose()
  bmCarrier = null
  bmPulse = null
  baselineModulatorActive.value = false
}

// ── Module 2: 0.5 Hz Drifting Ptosis Inducer ──
// Pink noise through a lowpass filter whose cutoff is modulated at 0.5 Hz,
// drifting down to 0.42 Hz over 5 minutes to compensate for neural adaptation
async function startPtosisInducer() {
  await Tone.start()
  if (piNoise) return
  piFilter = new Tone.Filter(300, 'lowpass').toDestination()
  piNoise = new Tone.Noise('pink').connect(piFilter)
  piNoise.volume.value = -12
  piLFO = new Tone.LFO({ frequency: 0.5, type: 'sine', min: 100, max: 800 }).start()
  piLFO.connect(piFilter.frequency)
  piNoise.start()
  piLFO.frequency.rampTo(0.42, 300)
  ptosisInducerActive.value = true
}

function stopPtosisInducer() {
  if (!piNoise) return
  piNoise.stop()
  piNoise.dispose()
  piLFO?.dispose()
  piFilter?.dispose()
  piNoise = null
  piLFO = null
  piFilter = null
  ptosisInducerActive.value = false
}

// ── Module 3: Synchronized Audiovisual Entrainment ──
// Transport at 144 BPM = 2.4 beats/second. A low synth pulse fires on every
// quarter note; an optional visual callback flashes the UI in sync.
async function startAVSync(onFlash?: (flash: boolean) => void) {
  await Tone.start()
  if (avSynth) return
  avVisualCallback = onFlash || null
  avSynth = new Tone.Synth().toDestination()
  avSynth.volume.value = -18

  Tone.getTransport().bpm.value = 144
  avLoopId = Tone.getTransport().scheduleRepeat((time) => {
    avSynth!.triggerAttackRelease('C2', '16n', time)
    Tone.getDraw().schedule(() => {
      avVisualCallback?.(true)
      setTimeout(() => avVisualCallback?.(false), 50)
    }, time)
  }, '4n') as unknown as number

  if (Tone.getTransport().state !== 'started') {
    Tone.getTransport().start()
  }
  avSyncActive.value = true
}

function stopAVSync() {
  if (!avSynth) return
  if (avLoopId !== undefined) Tone.getTransport().clear(avLoopId)
  avSynth.dispose()
  avSynth = null
  avVisualCallback = null
  avLoopId = undefined
  avSyncActive.value = false
}

// ── Binaural layer spec ──
// Single source of truth for the stereo pairs below. Exported so the admin
// hypno audit can check the spec and measure the engine's real output.
export interface BinauralLayerSpec {
  id: 'alpha' | 'theta' | 'schumann'
  label: string
  leftHz: number
  rightHz: number
  targetBand: 'delta' | 'theta' | 'alpha' | 'beta' | 'gamma'
}

export const BINAURAL_LAYERS: Record<BinauralLayerSpec['id'], BinauralLayerSpec> = {
  alpha:    { id: 'alpha',    label: 'Alpha Wave',         leftHz: 195,     rightHz: 205,     targetBand: 'alpha' },
  theta:    { id: 'theta',    label: 'Theta Dream',        leftHz: 177,     rightHz: 183,     targetBand: 'theta' },
  schumann: { id: 'schumann', label: 'Schumann Resonance', leftHz: 246.085, rightHz: 253.915, targetBand: 'theta' },
}

// ── Modules 4–6: binaural layers ──
// alpha    195 / 205 Hz     → 10 Hz   relaxed alertness, flow
// theta    177 / 183 Hz     → 6 Hz    deep meditation, hypnagogic imagery
// schumann 246.085 / 253.915 → 7.83 Hz earth resonance, grounding
const binauralActive = { alpha: alphaWaveActive, theta: thetaDreamActive, schumann: schumannActive }

async function startBinauralLayer(id: BinauralLayerSpec['id']) {
  await Tone.start()
  if (binauralVoices[id]) return
  const spec = BINAURAL_LAYERS[id]
  const panL = new Tone.Panner(-1).toDestination()
  const panR = new Tone.Panner(1).toDestination()
  const left = new Tone.Oscillator(spec.leftHz, 'sine').connect(panL)
  const right = new Tone.Oscillator(spec.rightHz, 'sine').connect(panR)
  left.volume.value = right.volume.value = phaseVol(id)
  left.start()
  right.start()
  binauralVoices[id] = { left, right, panL, panR }
  binauralActive[id].value = true
}

function stopBinauralLayer(id: BinauralLayerSpec['id']) {
  const v = binauralVoices[id]
  if (v) {
    v.left.stop(); v.left.dispose()
    v.right.stop(); v.right.dispose()
    v.panL.dispose(); v.panR.dispose()
    delete binauralVoices[id]
  }
  binauralActive[id].value = false
}

const startAlphaWave = () => startBinauralLayer('alpha')
const stopAlphaWave = () => stopBinauralLayer('alpha')
const startThetaDream = () => startBinauralLayer('theta')
const stopThetaDream = () => stopBinauralLayer('theta')
const startSchumann = () => startBinauralLayer('schumann')
const stopSchumann = () => stopBinauralLayer('schumann')

// ── Module 7: Solfeggio 528 Hz ──
// Pure 528 Hz tone with gentle 1 Hz amplitude tremolo
// Associated with transformation, DNA repair, and restoration
async function startSolfeggio() {
  await Tone.start()
  if (solOsc) return
  solGain = new Tone.Gain(0.06).toDestination()
  solOsc = new Tone.Oscillator(528, 'sine').connect(solGain)
  solLfo = new Tone.LFO({ frequency: 1, type: 'sine', min: 0.02, max: 0.08 }).start()
  solLfo.connect(solGain.gain)
  solOsc.start()
  solfeggioActive.value = true
}

function stopSolfeggio() {
  solOsc?.stop(); solOsc?.dispose(); solOsc = null
  solLfo?.dispose(); solLfo = null
  solGain?.dispose(); solGain = null
  solfeggioActive.value = false
}

// ── Module 8: Gamma Pulse (40 Hz isochronic) ──
// A single carrier amplitude-pulsed at the beat rate. 40 Hz is too fast to
// form a binaural beat, but an isochronic pulse is heard at any rate, in both
// ears, with or without headphones.
export interface IsochronicLayerSpec {
  id: 'gamma'
  label: string
  carrierHz: number
  pulseHz: number
  depth: number // 0..1 amplitude modulation depth
}

export const ISOCHRONIC_LAYERS: Record<IsochronicLayerSpec['id'], IsochronicLayerSpec> = {
  gamma: { id: 'gamma', label: 'Gamma Pulse', carrierHz: 220, pulseHz: 40, depth: 0.8 },
}

const GAMMA_PEAK = 0.05

async function startGammaPulse() {
  await Tone.start()
  if (gammaOsc) return
  const spec = ISOCHRONIC_LAYERS.gamma
  gammaFade = new Tone.Gain(0).toDestination()
  gammaGain = new Tone.Gain(0).connect(gammaFade)
  gammaOsc = new Tone.Oscillator(spec.carrierHz, 'sine').connect(gammaGain)
  gammaLfo = new Tone.LFO({
    frequency: spec.pulseHz,
    type: 'sine',
    min: GAMMA_PEAK * (1 - spec.depth),
    max: GAMMA_PEAK,
  })
  gammaLfo.connect(gammaGain.gain)
  gammaLfo.start()
  gammaOsc.start()
  gammaFade.gain.rampTo(1, 2) // ease in, no click
  gammaPulseActive.value = true
}

function stopGammaPulse() {
  gammaOsc?.stop(); gammaOsc?.dispose(); gammaOsc = null
  gammaLfo?.dispose(); gammaLfo = null
  gammaGain?.dispose(); gammaGain = null
  gammaFade?.dispose(); gammaFade = null
  gammaPulseActive.value = false
}

// ── Phase helpers ──
function setupCoherenceLoop() {
  if (swellOsc) return
  swellGain = new Tone.Gain(0).toDestination()
  swellOsc = new Tone.Oscillator(40, 'sine').connect(swellGain).start()

  coherenceLoopId = Tone.getTransport().scheduleRepeat((time) => {
    swellGain!.gain.rampTo(0.4, INHALE_TIME, time)

    Tone.getDraw().schedule(() => {
      if (phrasesEnabled) currentInstruction.value = 'BREATHE IN'
      isExpanding.value = true
    }, time)

    Tone.getDraw().schedule(() => {
      if (phrasesEnabled) currentInstruction.value = 'BREATHE OUT'
      isExpanding.value = false
    }, time + INHALE_TIME)

    swellGain!.gain.rampTo(0, INHALE_TIME, time + INHALE_TIME)
  }, BREATH_CYCLE) as unknown as number

  Tone.getTransport().start()
}

function scheduleDeepenSequence() {
  Tone.getTransport().start()
  if (deepenLoop) return
  deepenLoop = new Tone.Loop((time) => {
    subBass!.triggerAttackRelease('E1', '8n', time)
    Tone.getDraw().schedule(() => {
      tunnelPulseStrength.value = 1.0
    }, time)
  }, '2n').start(0)
}

function runInduction() {
  if (phase.value === 'induction') return
  phase.value = 'induction'
  clearPhaseTimer()
  gainNode?.gain.rampTo(0.5, 5)
  lfo?.frequency.rampTo(6, 30)
  applyPhaseLayerBalance('induction', 5)
  // Cycle through induction phrases every ~3s over the 30s window
  if (phrasesEnabled) schedulePhrases(INDUCTION_PHRASES, 3000)
  else clearPhraseTimers()
  if (autoAdvance) phaseTimer = setTimeout(() => runCoherence(), 30000)
}

function runCoherence() {
  if (phase.value === 'coherence') return
  phase.value = 'coherence'
  clearPhaseTimer()
  clearPhraseTimers()
  // Re-entering from a deeper phase (external driver): stop the sub-bass pulses
  if (deepenLoop) { deepenLoop.stop().dispose(); deepenLoop = null }
  applyPhaseLayerBalance('coherence', 10)
  setupCoherenceLoop()
}

function runDeepen() {
  if (phase.value === 'deepen') return
  phase.value = 'deepen'
  clearPhaseTimer()
  lfo?.frequency.rampTo(4.5, 60)
  applyPhaseLayerBalance('deepen', 20)
  if (swellOsc) { swellOsc.stop(); swellOsc.dispose(); swellOsc = null }
  if (swellGain) { swellGain.dispose(); swellGain = null }
  if (coherenceLoopId !== undefined) {
    Tone.getTransport().clear(coherenceLoopId)
    coherenceLoopId = undefined
  }
  scheduleDeepenSequence()
  // Cycle deepen phrases every ~8s
  if (phrasesEnabled) schedulePhrases(DEEPEN_PHRASES, 8000)
  else clearPhraseTimers()
}

function runJoy() {
  if (phase.value === 'joy') return
  phase.value = 'joy'
  clearPhaseTimer()
  // Audio: stop sub-bass pulses, soften core gain
  if (deepenLoop) { deepenLoop.stop().dispose(); deepenLoop = null }
  gainNode?.gain.rampTo(0.2, 8)
  lfo?.frequency.rampTo(3, 12)
  applyPhaseLayerBalance('joy', 10)
  // Joy phrases every ~4s, then auto-wake
  runPhrasesThen(JOY_PHRASES, 4000, () => runWake())
}

function runWake() {
  if (phase.value === 'wake') return
  phase.value = 'wake'
  clearPhaseTimer()
  // Audio: fade core and all layers out over ~18s
  gainNode?.gain.rampTo(0, 18)
  lfo?.frequency.rampTo(1, 18)
  applyPhaseLayerBalance('wake', 18)
  // Wake countdown phrases every ~3s, then end session
  runPhrasesThen(WAKE_PHRASES, 3000, () => {
    phaseTimer = setTimeout(() => completeSession(), 2000)
  })
}

// ── Public API ──
async function startSession(opts: { autoAdvance?: boolean; phrases?: boolean } = {}) {
  autoAdvance = opts.autoAdvance ?? true
  phrasesEnabled = opts.phrases ?? true
  await Tone.start()
  initCoreAudio()
  sessionActive.value = true
  sessionStartTime = Date.now()
  syncCount.value = 0
  coherenceScore.value = 0
  progress.value = 0
  runInduction()
}

// External driver: jump straight to a phase. Each run* is idempotent.
function enterPhase(p: Exclude<TrancePhase, 'idle'>) {
  switch (p) {
    case 'induction': runInduction(); break
    case 'coherence': runCoherence(); break
    case 'deepen': runDeepen(); break
    case 'joy': runJoy(); break
    case 'wake': runWake(); break
  }
}

// External driver: end the session and produce completedSession.
function finishSession() {
  return completeSession()
}

// External driver: 0 = light, 1 = deep. Slows the core LFO (6 → 3 Hz over
// ~8 s) and tilts the binaural balance toward theta.
function setDepth(d: number) {
  depthLevel = Math.min(1, Math.max(0, Number.isFinite(d) ? d : 0))
  if (!audioReady) return
  lfo?.frequency.rampTo(6 - 3 * depthLevel, 8)
  applyPhaseLayerBalance(phase.value, 8)
}

function windDown() {
  if (phase.value === 'deepen') runJoy()
  else if (phase.value === 'joy') runWake()
}

async function completeSession() {
  // Capture data before stopSession clears everything
  const sessionData = {
    dominant_phase: phase.value,
    session_duration_ms: Date.now() - sessionStartTime,
    sync_count: syncCount.value,
    coherence_peak: coherenceScore.value,
    modules_used: [
      baselineModulatorActive.value && 'baseline_modulator',
      ptosisInducerActive.value && 'ptosis_inducer',
      avSyncActive.value && 'av_sync',
      alphaWaveActive.value && 'alpha_wave',
      thetaDreamActive.value && 'theta_dream',
      schumannActive.value && 'schumann',
      solfeggioActive.value && 'solfeggio',
      gammaPulseActive.value && 'gamma_pulse',
    ].filter(Boolean) as string[],
  }

  // Capture for post-trance overlay before state is cleared
  completedSession.value = {
    coherence: coherenceScore.value,
    syncCount: syncCount.value,
    sessionDurationMs: Date.now() - sessionStartTime,
    dominantPhase: phase.value,
  }

  // Fire-and-forget to backend — signed-in users only. The endpoint requires
  // auth, and apiFetch treats a 401 as an expired session (logout + redirect to
  // /login), which would yank anonymous visitors out of the post-trance overlay.
  try {
    const { apiFetch, isAuthenticated } = useAuthStore()
    if (isAuthenticated.value) {
      await apiFetch('/api/vector/zeromind', {
        method: 'POST',
        body: JSON.stringify(sessionData),
      })
    }
  } catch { /* non-blocking */ }

  stopSession()
}

function clearCompletedSession() {
  completedSession.value = null
}

function stopSession() {
  clearPhraseTimers()
  clearPhaseTimer()
  depthLevel = 0
  if (deepenLoop) { deepenLoop.stop().dispose(); deepenLoop = null }
  if (coherenceLoopId !== undefined) { Tone.getTransport().clear(coherenceLoopId); coherenceLoopId = undefined }
  if (swellOsc) { swellOsc.stop(); swellOsc.dispose(); swellOsc = null }
  if (swellGain) { swellGain.dispose(); swellGain = null }
  if (osc) { osc.stop(); osc.dispose(); osc = null }
  if (lfo) { lfo.dispose(); lfo = null }
  if (gainNode) { gainNode.dispose(); gainNode = null }
  if (subBass) { subBass.dispose(); subBass = null }
  stopBaselineModulator()
  stopPtosisInducer()
  stopAVSync()
  stopAlphaWave()
  stopThetaDream()
  stopSchumann()
  stopSolfeggio()
  stopGammaPulse()
  Tone.getTransport().stop()

  phase.value = 'idle'
  sessionActive.value = false
  coherenceScore.value = 0
  progress.value = 0
  syncCount.value = 0
  isExpanding.value = false
  currentInstruction.value = ''
  isSyncing.value = false
  audioReady = false
}

function startSync() {
  if (phase.value === 'coherence') {
    isSyncing.value = true
    syncStartTime = Tone.getTransport().seconds
    tunnelPulseStrength.value = 0.2
  } else {
    syncCount.value++
    progress.value = Math.min(progress.value + 5, 100)
    tunnelPulseStrength.value = 0.3
    if (syncCount.value > 10 && autoAdvance) runDeepen()
  }
}

function stopSync() {
  if (phase.value !== 'coherence') return

  const holdDuration = Tone.getTransport().seconds - syncStartTime
  isSyncing.value = false

  const accuracy = 1 - Math.min(Math.abs(holdDuration - INHALE_TIME) / INHALE_TIME, 1)
  coherenceScore.value = Math.min(
    100,
    Math.round(coherenceScore.value * 0.7 + accuracy * 100 * 0.3)
  )

  tunnelPulseStrength.value = 0.3
  syncCount.value++
  progress.value = Math.min(progress.value + 5, 100)

  if (autoAdvance && coherenceScore.value > 70 && syncCount.value > 5) {
    runDeepen()
  }
}

async function toggleBaselineModulator() {
  if (baselineModulatorActive.value) stopBaselineModulator()
  else await startBaselineModulator()
}

async function togglePtosisInducer() {
  if (ptosisInducerActive.value) stopPtosisInducer()
  else await startPtosisInducer()
}

async function toggleAVSync(onFlash?: (flash: boolean) => void) {
  if (avSyncActive.value) stopAVSync()
  else await startAVSync(onFlash)
}

async function toggleAlphaWave() {
  if (alphaWaveActive.value) stopAlphaWave()
  else await startAlphaWave()
}

async function toggleThetaDream() {
  if (thetaDreamActive.value) stopThetaDream()
  else await startThetaDream()
}

async function toggleSchumann() {
  if (schumannActive.value) stopSchumann()
  else await startSchumann()
}

async function toggleSolfeggio() {
  if (solfeggioActive.value) stopSolfeggio()
  else await startSolfeggio()
}

async function toggleGammaPulse() {
  if (gammaPulseActive.value) stopGammaPulse()
  else await startGammaPulse()
}

// ── Gamification helpers ──
const activeLayerCount = computed(() =>
  [
    baselineModulatorActive.value,
    ptosisInducerActive.value,
    avSyncActive.value,
    alphaWaveActive.value,
    thetaDreamActive.value,
    schumannActive.value,
    solfeggioActive.value,
    gammaPulseActive.value,
  ].filter(Boolean).length
)

const TOTAL_LAYERS = 8

const phaseDisplayName = computed(() => {
  const names: Record<TrancePhase, string> = {
    idle: '',
    induction: 'settling',
    coherence: 'breathing',
    deepen: 'descent',
    joy: 'glow',
    wake: 'return',
  }
  return names[phase.value]
})

// ── Phase-aware visual accent ────────────────────────────────────
// Used by WebAudio canvas to tint star trails and glow
const phaseAccent = computed(() => {
  switch (phase.value) {
    case 'induction': return '#4a90e2'   // cool blue
    case 'coherence': return '#4a90e2'   // blue (pulse-driven)
    case 'deepen':    return '#7b5ea7'   // deep violet
    case 'joy':       return '#e09040'   // warm amber
    case 'wake':      return '#e8d090'   // soft gold
    default:          return '#4a90e2'
  }
})

// Whether the current phase shows floating text (not the pacer UI)
const isNarrativePhase = computed(() =>
  ['induction', 'deepen', 'joy', 'wake'].includes(phase.value)
)

export function useTranceEngine() {
  return {
    // Reactive state (readonly where appropriate)
    phase: readonly(phase),
    sessionActive: readonly(sessionActive),
    coherenceScore: readonly(coherenceScore),
    progress: readonly(progress),
    isExpanding: readonly(isExpanding),
    currentInstruction: readonly(currentInstruction),
    isSyncing: readonly(isSyncing),
    tunnelPulseStrength, // writable — visual components decay this
    baselineModulatorActive: readonly(baselineModulatorActive),
    ptosisInducerActive: readonly(ptosisInducerActive),
    avSyncActive: readonly(avSyncActive),
    alphaWaveActive: readonly(alphaWaveActive),
    thetaDreamActive: readonly(thetaDreamActive),
    schumannActive: readonly(schumannActive),
    solfeggioActive: readonly(solfeggioActive),
    gammaPulseActive: readonly(gammaPulseActive),
    phaseAccent,
    isNarrativePhase,
    activeLayerCount,
    totalLayers: TOTAL_LAYERS,
    phaseDisplayName,
    completedSession: readonly(completedSession),
    clearCompletedSession,

    // Session control
    startSession,
    stopSession,
    completeSession,
    windDown,
    enterPhase,
    finishSession,
    setDepth,
    startSync,
    stopSync,

    // Entrainment modules
    toggleBaselineModulator,
    togglePtosisInducer,
    toggleAVSync,
    toggleAlphaWave,
    toggleThetaDream,
    toggleSchumann,
    toggleSolfeggio,
    toggleGammaPulse,
  }
}
