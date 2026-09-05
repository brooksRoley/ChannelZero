<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as Tone from 'tone'
import { useTextOverlay } from '@/composables/useTextOverlay'
import { useCosmicPhysics } from '@/composables/useCosmicPhysics'
import { useTranceEngine } from '@/composables/useTranceEngine'
import PostTranceOverlay from '@/components/PostTranceOverlay.vue'

const {
  displayText, displayLabel, isVisible,
  isReaderMode, readerProgress, isPlaying, toggleOrSkip
} = useTextOverlay()

const { completedSession, clearCompletedSession } = useTranceEngine()
const showOverlay = ref(false)

watch(completedSession, (data) => {
  if (data) showOverlay.value = true
})

function handleOverlayClose() {
  showOverlay.value = false
  clearCompletedSession()
}

// ── Canvas + cosmic physics ───────────────────────────────────────
const canvasRef = ref<HTMLCanvasElement>()
const { loaded, adapt, init: initCosmic, destroy: destroyCosmic, heatOrb, clickImpulse } = useCosmicPhysics(canvasRef)

// ── Audio state ───────────────────────────────────────────────────
const audioOn = ref(false)
const CHIME_NOTES = ['E4', 'G#4', 'B4', 'D5', 'F#4', 'A4']
const T = Tone as any
let audio: any = null
let lastChime = 0

// ── Tone.js audio ─────────────────────────────────────────────────
function initAudio() {
  if (audio) return
  const gain = new T.Gain(0.12).toDestination()

  const drone = new T.FMSynth({
    harmonicity: 2, modulationIndex: 3,
    oscillator: { type: 'sine' },
    envelope: { attack: 8, decay: 0, sustain: 1, release: 12 },
    modulation: { type: 'triangle' },
    modulationEnvelope: { attack: 5, decay: 0, sustain: 1, release: 12 },
    volume: -20,
  }).connect(gain)

  const sub = new T.Synth({
    oscillator: { type: 'sine' },
    envelope: { attack: 10, decay: 0, sustain: 1, release: 14 },
    volume: -24,
  }).connect(gain)

  const nGain = new T.Gain(0.03).connect(gain)
  const nFilter = new T.AutoFilter({
    frequency: 0.07, baseFrequency: 120, octaves: 3, depth: 0.5,
  }).connect(nGain).start()
  const noise = new T.Noise('pink').connect(nFilter)
  noise.volume.value = -26
  noise.start()

  const chime = new T.PolySynth(T.Synth, {
    oscillator: { type: 'sine' },
    envelope: { attack: 0.005, decay: 2.8, sustain: 0, release: 1.8 },
    volume: -22,
  }).connect(gain)

  const breathe = new T.LFO({ frequency: 0.1, min: 0.08, max: 0.14 }).start()
  breathe.connect(gain.gain)

  const modLfo = new T.LFO({ frequency: 0.02, min: 2, max: 8 }).start()
  modLfo.connect(drone.modulationIndex)

  drone.triggerAttack('C2')
  sub.triggerAttack('C1')

  audio = { gain, drone, sub, noise, nFilter, nGain, chime, breathe, modLfo }
}

function destroyAudio() {
  if (!audio) return
  try {
    audio.drone.triggerRelease()
    audio.sub.triggerRelease()
    audio.noise.stop()
    audio.breathe.stop()
    audio.modLfo.stop()
    Object.values(audio).forEach((n: any) => n?.dispose?.())
  } catch { /* swallow */ }
  audio = null
}

function chimeOrb(idx: number) {
  if (!audio || !audioOn.value) return
  const now = T.now()
  if (now - lastChime < 2) return
  lastChime = now
  audio.chime.triggerAttackRelease(CHIME_NOTES[idx % CHIME_NOTES.length], '4n', now)
}

// Feed adaptive engagement into noise brightness
watch(() => adapt.engage, (eng) => {
  if (audio && audioOn.value) {
    try { audio.nFilter.set({ baseFrequency: 120 + eng * 280 }) } catch { /* noop */ }
  }
})

// ── Tap / Click ───────────────────────────────────────────────────
async function handleClick(e: MouseEvent) {
  clickImpulse(e.clientX, e.clientY)
  if (!audioOn.value) {
    try { await T.start(); initAudio(); audioOn.value = true } catch { /* noop */ }
    if (isReaderMode.value && !isPlaying.value) toggleOrSkip()
    return
  }
  toggleOrSkip()
}

// ── Lifecycle ─────────────────────────────────────────────────────
onMounted(async () => {
  await initCosmic()
})

onUnmounted(() => {
  destroyCosmic()
  destroyAudio()
})
</script>

<template>
  <div
    class="hypno"
    role="application"
    aria-label="Hypnotic orb field — tap to start, WASD or arrow keys to push orbs, Tab to select"
    @click="handleClick"
  >
    <canvas ref="canvasRef" class="hypno-canvas" aria-hidden="true" />

    <!-- Entry gate -->
    <Transition name="gate">
      <div v-if="loaded && !audioOn" class="gate-overlay">
        <h1 class="gate-title">enter the field</h1>
        <p class="gate-sub">tap anywhere &middot; headphones recommended</p>
        <p class="gate-hint">wasd / arrows to push orbs &middot; tab to select</p>
      </div>
    </Transition>

    <!-- Text layer (fades in after audio starts) -->
    <div class="text-layer" :class="{ active: audioOn }">
      <div v-if="displayLabel" class="text-label" :class="{ dim: !isVisible }">{{ displayLabel }}</div>
      <span class="text-word" :class="[{ dim: !isVisible }, isReaderMode ? 'reader-text' : '']">
        {{ displayText }}
      </span>
      <div v-if="isReaderMode" class="reader-status">
        <span class="status-dot" :class="{ on: isPlaying }" />
        {{ isPlaying ? 'reading' : 'paused' }}
      </div>
    </div>

    <!-- Reader progress -->
    <div v-if="isReaderMode && audioOn" class="progress-track">
      <div class="progress-fill" :style="{ width: `${readerProgress}%` }" />
    </div>

    <!-- Subtle focus meter -->
    <div v-if="audioOn" class="focus-meter">
      <div class="focus-fill" :style="{ height: `${adapt.focus * 100}%` }" />
    </div>

    <PostTranceOverlay
      v-if="showOverlay && completedSession"
      :coherence="completedSession.coherence"
      :sync-count="completedSession.syncCount"
      :session-duration="completedSession.sessionDurationMs"
      :dominant-phase="completedSession.dominantPhase"
      @close="handleOverlayClose"
    />
  </div>
</template>

<style scoped>
.hypno {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: #08060e;
  cursor: none;
  user-select: none;
}

.hypno-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

/* ── Entry gate ── */
.gate-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(8, 6, 14, 0.92);
  cursor: pointer;
}

.gate-title {
  font-size: clamp(1.6rem, 4vw, 3rem);
  font-weight: 200;
  letter-spacing: 0.25em;
  color: rgba(200, 190, 230, 0.7);
  text-transform: lowercase;
  margin: 0;
  font-family: 'Georgia', serif;
  font-style: italic;
}

.gate-sub {
  margin-top: 1.5rem;
  font-size: clamp(0.55rem, 1vw, 0.72rem);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(160, 150, 190, 0.3);
}

.gate-hint {
  margin-top: 2.5rem;
  font-size: clamp(0.5rem, 0.9vw, 0.62rem);
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: rgba(140, 130, 170, 0.2);
}

.gate-leave-active {
  transition: opacity 1.4s ease;
}
.gate-leave-to {
  opacity: 0;
}

/* ── Text overlay ── */
.text-layer {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  opacity: 0;
  transition: opacity 1.5s ease;
}

.text-layer.active {
  opacity: 1;
}

.text-label {
  font-size: clamp(0.5rem, 1vw, 0.68rem);
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: rgba(160, 150, 200, 0.3);
  margin-bottom: 0.8rem;
  transition: opacity 0.6s ease;
}

.text-label.dim {
  opacity: 0;
}

.text-word {
  font-family: 'Georgia', serif;
  font-size: clamp(2rem, 5.5vw, 4.5rem);
  font-weight: 300;
  font-style: italic;
  letter-spacing: 0.12em;
  text-transform: lowercase;
  color: rgba(220, 215, 240, 0.85);
  text-shadow:
    0 0 40px rgba(140, 120, 200, 0.4),
    0 0 80px rgba(100, 80, 180, 0.2);
  text-align: center;
  max-width: 85vw;
  line-height: 1.3;
  transition: opacity 0.8s ease;
}

.text-word.dim {
  opacity: 0;
}

/* Reader mode: clean, stable, no animation lag */
.text-word.reader-text {
  font-style: normal;
  font-family: 'Georgia', serif;
  font-size: clamp(1.6rem, 4vw, 3.2rem);
  letter-spacing: 0.06em;
  text-transform: none;
  color: rgba(230, 225, 245, 0.9);
  text-shadow: 0 0 24px rgba(140, 120, 200, 0.25);
  transition: none;
}

.reader-status {
  margin-top: 1.5rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.55rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: rgba(140, 135, 170, 0.35);
}

.status-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.3);
  transition: background 0.3s;
}

.status-dot.on {
  background: #6366f1;
  animation: dot-pulse 1s ease-in-out infinite alternate;
}

@keyframes dot-pulse {
  from { opacity: 0.4; }
  to { opacity: 1; }
}

/* ── Reader progress ── */
.progress-track {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: rgba(255, 255, 255, 0.03);
  z-index: 10;
}

.progress-fill {
  height: 100%;
  background: rgba(99, 102, 241, 0.5);
  transition: width 0.15s linear;
}

/* ── Focus meter ── */
.focus-meter {
  position: absolute;
  right: 1rem;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 60px;
  border-radius: 1px;
  background: rgba(255, 255, 255, 0.04);
  z-index: 10;
  overflow: hidden;
}

.focus-fill {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(99, 102, 241, 0.25);
  border-radius: 1px;
  transition: height 0.5s ease;
}

/* ── Mobile ── */
@media (max-width: 768px) {
  .hypno {
    cursor: default;
  }

  .focus-meter {
    right: 0.5rem;
    height: 40px;
  }
}
</style>
