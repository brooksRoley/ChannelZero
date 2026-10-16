import { ref, computed } from 'vue'
import { pinkNoiseBuffer } from '@/audio/core'

const DURATION = 300 // 5 minutes

interface Affirmation {
  time: number
  text: string
}

const AFFIRMATIONS: Affirmation[] = [
  { time: 0, text: 'Find a comfortable position. Let your body settle.' },
  { time: 20, text: 'Close your eyes. Take a slow, deep breath.' },
  { time: 40, text: 'With each exhale, release any tension you are holding.' },
  { time: 60, text: 'You are safe. You are present. You are enough.' },
  { time: 85, text: 'Let thoughts pass like clouds — no need to follow them.' },
  { time: 110, text: 'Feel the weight of your body. Grounded. Supported.' },
  { time: 135, text: 'Your breath is your anchor. Return to it gently.' },
  { time: 155, text: 'Each moment is a chance to begin again.' },
  { time: 180, text: 'You are not your thoughts. You are the awareness behind them.' },
  { time: 205, text: 'Let stillness expand from your center outward.' },
  { time: 225, text: 'There is nowhere to go. Nothing to fix. Just this breath.' },
  { time: 245, text: 'You carry more strength than you know.' },
  { time: 262, text: 'Breathe in calm. Breathe out gratitude.' },
  { time: 278, text: 'Gently begin to notice the sounds around you.' },
  { time: 290, text: 'When you are ready, slowly open your eyes.' },
  { time: 298, text: 'Welcome back.' }
]

const RING_CIRCUMFERENCE = 2 * Math.PI * 52 // r=52 in 120x120 viewBox

export function useMeditation() {
  const isActive = ref(false)
  const isPaused = ref(false)
  const elapsed = ref(0)
  const musicVolume = ref(0.4)
  const natureVolume = ref(0.3)

  let startTime = 0
  let pausedElapsed = 0
  let rafId: number | null = null

  // Audio handles
  let musicEl: HTMLAudioElement | null = null
  let audioCtx: AudioContext | null = null
  let noiseGain: GainNode | null = null

  const currentAffirmation = computed(() => {
    const t = elapsed.value
    let text = AFFIRMATIONS[0].text
    for (const a of AFFIRMATIONS) {
      if (t >= a.time) text = a.text
      else break
    }
    return text
  })

  const affirmationKey = computed(() => {
    const t = elapsed.value
    let idx = 0
    for (let i = 0; i < AFFIRMATIONS.length; i++) {
      if (t >= AFFIRMATIONS[i].time) idx = i
      else break
    }
    return idx
  })

  const progress = computed(() => Math.min(elapsed.value / DURATION, 1))
  const remaining = computed(() => Math.max(0, DURATION - Math.floor(elapsed.value)))
  const isComplete = computed(() => elapsed.value >= DURATION)
  const ringOffset = computed(() => (1 - progress.value) * RING_CIRCUMFERENCE)

  function formatTime(secs: number): string {
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  // Pink noise → bandpass → slow LFO modulation → wind/rain texture
  function initNature() {
    audioCtx = new AudioContext()
    // Stereo (decorrelated) and quieter than the studio's bed: it sits under a voice.
    const buf = pinkNoiseBuffer(audioCtx, { seconds: 4, channels: 2, level: 0.04 })

    const src = audioCtx.createBufferSource()
    src.buffer = buf
    src.loop = true

    const bp = audioCtx.createBiquadFilter()
    bp.type = 'bandpass'
    bp.frequency.value = 600
    bp.Q.value = 0.4

    // Slow modulation for organic wind-like movement
    const lfo = audioCtx.createOscillator()
    const lfoGain = audioCtx.createGain()
    lfo.frequency.value = 0.06
    lfoGain.gain.value = 350
    lfo.connect(lfoGain)
    lfoGain.connect(bp.frequency)
    lfo.start()

    noiseGain = audioCtx.createGain()
    noiseGain.gain.value = natureVolume.value

    src.connect(bp)
    bp.connect(noiseGain)
    noiseGain.connect(audioCtx.destination)
    src.start()
  }

  function tick() {
    if (!isActive.value || isPaused.value) return
    elapsed.value = pausedElapsed + (performance.now() - startTime) / 1000

    if (elapsed.value >= DURATION) {
      elapsed.value = DURATION
      if (rafId) cancelAnimationFrame(rafId)
      // Gentle fade-out
      if (musicEl) musicEl.pause()
      if (audioCtx && noiseGain) {
        noiseGain.gain.linearRampToValueAtTime(0, audioCtx.currentTime + 2)
      }
      return
    }
    rafId = requestAnimationFrame(tick)
  }

  function start() {
    if (isActive.value) return
    isActive.value = true
    isPaused.value = false
    elapsed.value = 0
    pausedElapsed = 0
    startTime = performance.now()

    musicEl = new Audio('/audio/pulse.wav')
    // musicEl = new Audio('/audio/delta_descent.wav')
    musicEl.loop = true
    musicEl.volume = musicVolume.value
    musicEl.play().catch(() => {})

    initNature()
    rafId = requestAnimationFrame(tick)
  }

  function togglePause() {
    if (!isActive.value) return
    if (isPaused.value) {
      isPaused.value = false
      startTime = performance.now()
      musicEl?.play().catch(() => {})
      audioCtx?.resume()
      rafId = requestAnimationFrame(tick)
    } else {
      isPaused.value = true
      pausedElapsed = elapsed.value
      if (rafId) cancelAnimationFrame(rafId)
      musicEl?.pause()
      audioCtx?.suspend()
    }
  }

  function stop() {
    isActive.value = false
    isPaused.value = false
    elapsed.value = 0
    pausedElapsed = 0
    if (rafId) cancelAnimationFrame(rafId)
    if (musicEl) {
      musicEl.pause()
      musicEl.src = ''
      musicEl = null
    }
    if (audioCtx) {
      audioCtx.close().catch(() => {})
      audioCtx = null
      noiseGain = null
    }
  }

  function setMusicVol(v: number) {
    musicVolume.value = v
    if (musicEl) musicEl.volume = v
  }

  function setNatureVol(v: number) {
    natureVolume.value = v
    if (noiseGain) noiseGain.gain.value = v
  }

  return {
    isActive,
    isPaused,
    elapsed,
    progress,
    remaining,
    isComplete,
    currentAffirmation,
    affirmationKey,
    ringOffset,
    ringCircumference: RING_CIRCUMFERENCE,
    musicVolume,
    natureVolume,
    formatTime,
    start,
    togglePause,
    stop,
    setMusicVol,
    setNatureVol
  }
}
