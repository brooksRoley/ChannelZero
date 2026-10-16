import { ref, reactive, computed, readonly } from 'vue'
import { createBinauralPair, earFrequencies, type BinauralPair } from '@/audio/core'

export type EntrainPhase = 'idle' | 'engage' | 'relax' | 'theta' | 'hold' | 'integrate' | 'complete'

const CARRIER = 200

interface PhaseDef {
  name: EntrainPhase
  targetHz: number
  durationS: number
}

export const PHASES: PhaseDef[] = [
  { name: 'engage',    targetHz: 12,  durationS: 45 },
  { name: 'relax',     targetHz: 8,   durationS: 75 },
  { name: 'theta',     targetHz: 6,   durationS: 75 },
  { name: 'hold',      targetHz: 6.5, durationS: 120 },
  { name: 'integrate', targetHz: 10,  durationS: 50 },
]

export const PHASE_LABELS: Record<EntrainPhase, string> = {
  idle: '', engage: 'grounding', relax: 'softening',
  theta: 'deepening', hold: 'open', integrate: 'rising', complete: 'complete',
}

export const PHASE_COLORS: Record<EntrainPhase, string> = {
  idle: '#64748b', engage: '#4a90e2', relax: '#3ab5a0',
  theta: '#7b5ea7', hold: '#4338ca', integrate: '#e09040', complete: '#e8d090',
}

export function useAdaptiveEntrain() {
  // ── State ──
  const active = ref(false)
  const phase = ref<EntrainPhase>('idle')
  const currentHz = ref(12)
  const targetHz = ref(12)
  const sessionTime = ref(0)
  const phaseProgress = ref(0)
  const beatPulse = ref(0)
  const cursorX = ref(typeof window !== 'undefined' ? window.innerWidth / 2 : 0)
  const cursorY = ref(typeof window !== 'undefined' ? window.innerHeight / 2 : 0)

  const behavior = reactive({ agitation: 0, rhythm: 0, stillness: 0 })

  // ── Audio (Web Audio API binaural pair) ──
  let actx: AudioContext | null = null
  let pair: BinauralPair | null = null
  let master: GainNode | null = null

  // ── Internals ──
  let phaseIdx = -1
  let phaseStartHz = 12
  let phaseTimeS = 0
  let beatPhaseAcc = 0
  let lastMoveT = 0
  let lastInteractT = 0
  let prevMx = 0
  let prevMy = 0
  let moveVels: number[] = []
  let clickTimes: number[] = []
  let stopTimer: ReturnType<typeof setTimeout> | null = null

  // ── Audio lifecycle ──
  function initAudio() {
    actx = new AudioContext()
    master = actx.createGain()
    master.gain.value = 0
    master.gain.setTargetAtTime(0.12, actx.currentTime, 1)
    master.connect(actx.destination)

    pair = createBinauralPair(actx, earFrequencies(CARRIER, currentHz.value))
    pair.output.connect(master)
    pair.start()
  }

  function setFreq(hz: number) {
    if (!actx || !pair) return
    // Eases toward the target — this journey follows the person, it never snaps.
    pair.setBeat(hz, CARRIER, { kind: 'target', timeConstant: 0.3 })
  }

  function destroyAudio() {
    if (master && actx) {
      try { master.gain.setTargetAtTime(0, actx.currentTime, 0.3) } catch { /* noop */ }
    }
    const refs = { pair, actx }
    setTimeout(() => {
      refs.pair?.dispose()
      try { refs.actx?.close() } catch { /* noop */ }
    }, 500)
    pair = null
    master = null
    actx = null
  }

  // ── Behavioral tracking ──
  function handleMove(x: number, y: number) {
    const now = performance.now()
    cursorX.value = x
    cursorY.value = y
    if (lastMoveT > 0) {
      const dx = x - prevMx
      const dy = y - prevMy
      const dt = Math.max(1, now - lastMoveT)
      moveVels.push(Math.sqrt(dx * dx + dy * dy) / dt * 16)
      if (moveVels.length > 30) moveVels.shift()
    }
    prevMx = x
    prevMy = y
    lastMoveT = now
    lastInteractT = now
  }

  function handleClick() {
    const now = performance.now()
    clickTimes.push(now)
    if (clickTimes.length > 10) clickTimes.shift()
    lastInteractT = now
  }

  const onMM = (e: MouseEvent) => handleMove(e.clientX, e.clientY)
  const onTM = (e: TouchEvent) => {
    const t = e.touches[0]
    if (t) handleMove(t.clientX, t.clientY)
  }
  const onCl = () => handleClick()
  const onTS = () => handleClick()

  function addListeners() {
    window.addEventListener('mousemove', onMM)
    window.addEventListener('touchmove', onTM, { passive: true })
    window.addEventListener('click', onCl)
    window.addEventListener('touchstart', onTS, { passive: true })
  }

  function removeListeners() {
    window.removeEventListener('mousemove', onMM)
    window.removeEventListener('touchmove', onTM)
    window.removeEventListener('click', onCl)
    window.removeEventListener('touchstart', onTS)
  }

  // ── Behavior computation ──
  function updateBehavior(dt: number) {
    const now = performance.now()

    // Agitation from mouse velocity
    if (moveVels.length > 3) {
      const mean = moveVels.reduce((a, b) => a + b, 0) / moveVels.length
      behavior.agitation += (Math.min(1, mean / 8) - behavior.agitation) * dt * 2
    } else {
      behavior.agitation *= Math.exp(-dt * 1.5)
    }

    // Rhythm from click interval consistency
    if (clickTimes.length > 3) {
      const ivs: number[] = []
      for (let i = 1; i < clickTimes.length; i++) ivs.push(clickTimes[i] - clickTimes[i - 1])
      const m = ivs.reduce((a, b) => a + b, 0) / ivs.length
      const v = ivs.reduce((a, x) => a + (x - m) ** 2, 0) / ivs.length
      behavior.rhythm = Math.min(1, Math.max(0, 1 - Math.sqrt(v) / Math.max(m, 1)))
    }
    behavior.rhythm *= Math.exp(-dt * 0.15)

    // Stillness from idle time
    const idle = (now - lastInteractT) / 1000
    behavior.stillness += (Math.min(1, idle / 8) - behavior.stillness) * dt * 1.5

    // Decay stale velocity data
    if (now - lastMoveT > 500) moveVels.length = 0
  }

  // ── Phase progression ──
  function advancePhase() {
    phaseIdx++
    if (phaseIdx >= PHASES.length) {
      phase.value = 'complete'
      if (master && actx) master.gain.setTargetAtTime(0, actx.currentTime, 2)
      stopTimer = setTimeout(() => stop(), 4000)
      return
    }
    phase.value = PHASES[phaseIdx].name
    phaseStartHz = currentHz.value
    phaseTimeS = 0
    phaseProgress.value = 0
  }

  function getAdaptiveTarget(): number {
    const plan = PHASES[phaseIdx]
    if (!plan) return 10

    // Linear interpolation within phase
    const p = Math.min(1, phaseTimeS / plan.durationS)
    let target = phaseStartHz + (plan.targetHz - phaseStartHz) * p

    // Behavioral modifiers
    if (behavior.agitation > 0.7) return Math.max(target, 10)
    if (behavior.agitation > 0.4) {
      target += (10 - target) * (behavior.agitation - 0.4) / 0.3 * 0.4
    }
    if (behavior.stillness > 0.5 && behavior.agitation < 0.2) {
      target = Math.max(5, target - 0.5)
    }

    return target
  }

  // ── Per-frame update (called by view RAF loop) ──
  function update(dt: number) {
    if (!active.value || phase.value === 'complete') return

    sessionTime.value += dt
    phaseTimeS += dt
    updateBehavior(dt)

    const plan = PHASES[phaseIdx]
    if (plan) {
      phaseProgress.value = Math.min(1, phaseTimeS / plan.durationS)
      if (phaseTimeS >= plan.durationS) advancePhase()
    }

    // Smooth frequency chase
    const target = getAdaptiveTarget()
    targetHz.value = target
    currentHz.value += (target - currentHz.value) * Math.min(1, dt * 0.8)
    setFreq(currentHz.value)

    // Beat pulse (visual sub-harmonic of beat frequency)
    beatPhaseAcc += currentHz.value * dt / 8
    beatPulse.value = (Math.sin(beatPhaseAcc * Math.PI * 2) + 1) / 2
  }

  // ── Public API ──
  function start() {
    if (active.value) return
    if (stopTimer) { clearTimeout(stopTimer); stopTimer = null }
    initAudio()
    active.value = true
    currentHz.value = 12
    targetHz.value = 12
    sessionTime.value = 0
    phaseTimeS = 0
    phaseIdx = -1
    beatPhaseAcc = 0
    Object.assign(behavior, { agitation: 0, rhythm: 0, stillness: 0 })
    moveVels = []
    clickTimes = []
    lastInteractT = performance.now()
    lastMoveT = 0
    cursorX.value = window.innerWidth / 2
    cursorY.value = window.innerHeight / 2
    addListeners()
    advancePhase()
  }

  function stop() {
    if (!active.value && phase.value === 'idle') return
    active.value = false
    phase.value = 'idle'
    if (stopTimer) { clearTimeout(stopTimer); stopTimer = null }
    removeListeners()
    destroyAudio()
  }

  function windDown() {
    if (!active.value || phase.value === 'integrate' || phase.value === 'complete') return
    phaseIdx = PHASES.findIndex(p => p.name === 'integrate') - 1
    advancePhase()
  }

  function setVolume(v: number) {
    if (master && actx) {
      master.gain.setTargetAtTime(Math.max(0, Math.min(0.25, v)), actx.currentTime, 0.1)
    }
  }

  // ── Computed helpers ──
  const phaseLabel = computed(() => PHASE_LABELS[phase.value])
  const phaseColor = computed(() => PHASE_COLORS[phase.value])

  const bandLabel = computed(() => {
    const hz = currentHz.value
    if (hz >= 12) return 'beta edge'
    if (hz >= 8) return 'alpha'
    if (hz >= 6) return 'theta'
    return 'deep theta'
  })

  const coherence = computed(() =>
    Math.min(1, (1 - behavior.agitation) * 0.6 + behavior.stillness * 0.4)
  )

  return {
    active: readonly(active),
    phase: readonly(phase),
    phaseLabel,
    phaseColor,
    bandLabel,
    currentHz: readonly(currentHz),
    targetHz: readonly(targetHz),
    sessionTime: readonly(sessionTime),
    phaseProgress: readonly(phaseProgress),
    beatPulse: readonly(beatPulse),
    coherence,
    behavior,
    cursorX: readonly(cursorX),
    cursorY: readonly(cursorY),
    phases: PHASES,
    update,
    start,
    stop,
    windDown,
    setVolume,
  }
}
