<template>
  <div
    class="trance-root"
    @mousedown="onMouseDown"
    @mousemove="onMouseMove"
    @mouseup="onMouseUp"
    @touchstart.prevent="onTouchStart"
    @touchmove.prevent="onTouchMove"
    @touchend="onTouchEnd"
  >
    <!-- Category-driven canvas -->
    <canvas ref="canvasEl" class="canvas-layer" aria-hidden="true" />

    <!-- Audio-init overlay -->
    <Transition name="init-fade">
      <div v-if="!audioReady" class="init-overlay">
        <h1 class="init-title">trance tone engine</h1>
        <p class="init-sub">click to begin</p>
        <p class="init-warn">&#9888; stereo headphones required for binaural effect</p>
      </div>
    </Transition>

    <!-- Word + formula overlay (unified via useTextOverlay) -->
    <div class="text-overlay">
      <div v-if="overlayLabel" class="category-label" :class="{ fading: !overlayVisible }" :style="{ color: accentColor }">
        {{ overlayLabel }}
      </div>
      <div class="word-display" :class="[{ fading: !overlayVisible }, isReaderMode ? 'reader-word' : '']">
        {{ overlayText }}
      </div>
      <div v-if="!isReaderMode" class="formula-display" :class="{ fading: !overlayVisible }">{{ displayFormula }}</div>
      <div v-if="!isReaderMode" class="beat-info" :class="{ fading: !overlayVisible }">{{ displayBeat }}</div>
      <div v-if="isReaderMode" class="reader-status">
        <span class="reader-dot" :class="{ active: readerPlaying }" />
        {{ readerPlaying ? 'reading' : 'tap to play' }}
      </div>
    </div>

    <!-- Progress bar (reader or timelapse) -->
    <div v-if="isReaderMode" class="reader-progress-bar">
      <div class="reader-progress-fill" :style="{ width: `${readerProgress}%` }" />
    </div>

    <!-- Volume control -->
    <div v-if="audioReady" class="volume-ctrl">
      <label>vol</label>
      <input type="range" min="0" max="100" :value="volume" @input="onVolume" />
    </div>

    <!-- Hint -->
    <div v-if="audioReady" class="click-hint">click anywhere to shift &middot; auto-advances</div>


    <!-- Cursor glow -->
    <div
      class="cursor-glow"
      :style="{
        left: `${mouseX}px`,
        top: `${mouseY}px`,
        background: `radial-gradient(circle, ${accentColor}, transparent)`,
      }"
    />

    <!-- Tutorial overlay -->
    <Transition name="tutorial-slide">
      <div v-if="tutorialInfo" class="tutorial-card">
        <div class="tutorial-title">{{ tutorialInfo.title }}</div>
        <div class="tutorial-text">{{ tutorialInfo.text }}</div>
        <button class="tutorial-dismiss" @click="dismissTutorial">Got it</button>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useBinauralEngine } from '@/composables/useBinauralEngine'
import { categories, type ViewOffset } from '@/composables/useTranceCategories'
import { useTextOverlay } from '@/composables/useTextOverlay'

const { initialized: audioReady, volume, init: initAudio, setBeat, setVolume, getWaveformData, destroy: destroyAudio } = useBinauralEngine()
const {
  displayText: overlayText,
  displayLabel: overlayLabel,
  activeCatKey: overlayCatKey,
  isVisible: overlayVisible,
  isReaderMode,
  readerProgress,
  isPlaying: readerPlaying,
  toggleOrSkip: overlayToggle,
} = useTextOverlay()

// ── Display state ──
const mouseX = ref(typeof window !== 'undefined' ? window.innerWidth / 2 : 0)
const mouseY = ref(typeof window !== 'undefined' ? window.innerHeight / 2 : 0)
const canvasEl = ref<HTMLCanvasElement | null>(null)

// Derived from the unified overlay's active category
const currentCatKey = computed(() => overlayCatKey.value)
const accentColor = computed(() => categories[currentCatKey.value]?.color ?? 'rgba(123, 94, 167, 0.4)')
const displayFormula = computed(() => categories[currentCatKey.value]?.formula ?? '')
const displayBeat = computed(() => {
  const cat = categories[currentCatKey.value]
  if (!cat) return ''
  const L = (cat.carrier - cat.beatHz / 2).toFixed(0)
  const R = (cat.carrier + cat.beatHz / 2).toFixed(0)
  return `\u03B3 ${cat.beatHz} Hz binaural \u00B7 ${cat.carrier} Hz carrier \u00B7 L ${L} Hz \u00B7 R ${R} Hz`
})

// ── Drag / swipe ──
const viewOffset: ViewOffset = { x: 0, y: 0 }
const dragTarget = { x: 0, y: 0 }
let dragActive = false
let dragStartX = 0
let dragStartY = 0
let dragMoved = false
const DRAG_THRESHOLD = 5

function dragStart(cx: number, cy: number) {
  dragActive = true
  dragStartX = cx
  dragStartY = cy
  dragMoved = false
}

function dragMove(cx: number, cy: number) {
  if (!dragActive) return
  if (Math.abs(cx - dragStartX) > DRAG_THRESHOLD || Math.abs(cy - dragStartY) > DRAG_THRESHOLD) dragMoved = true
  const maxShift = Math.min(window.innerWidth, window.innerHeight) * 0.14
  dragTarget.x = Math.max(-maxShift, Math.min(maxShift, (cx - window.innerWidth / 2) * 0.11))
  dragTarget.y = Math.max(-maxShift, Math.min(maxShift, (cy - window.innerHeight / 2) * 0.11))
}

function dragEnd(): boolean {
  dragActive = false
  return !dragMoved // true = tap
}

// ── Sync binaural beats with overlay category ──
let animFrame: number | undefined
let globalTime = 0

watch(overlayCatKey, (key) => {
  if (!audioReady.value) return
  const cat = categories[key]
  if (cat) setBeat(cat.beatHz, cat.carrier, 1.5)
})

function handleTap() {
  if (!audioReady.value) {
    initAudio()
    // Set initial beat from current category
    const cat = categories[overlayCatKey.value]
    if (cat) setBeat(cat.beatHz, cat.carrier, 1.5)
  }
  overlayToggle()
}

// ── Mouse / touch handlers ──
function onMouseDown(e: MouseEvent) {
  if ((e.target as HTMLElement)?.closest('.volume-ctrl, .tutorial-card')) return
  dragStart(e.clientX, e.clientY)
}
function onMouseMove(e: MouseEvent) {
  mouseX.value = e.clientX
  mouseY.value = e.clientY
  dragMove(e.clientX, e.clientY)
}
function onMouseUp(e: MouseEvent) {
  if ((e.target as HTMLElement)?.closest('.volume-ctrl, .tutorial-card')) return
  if (dragEnd()) handleTap()
}
function onTouchStart(e: TouchEvent) {
  if ((e.target as HTMLElement)?.closest('.volume-ctrl, .tutorial-card')) return
  const t = e.touches[0]
  if (t) { mouseX.value = t.clientX; mouseY.value = t.clientY }
  dragStart(t.clientX, t.clientY)
}
function onTouchMove(e: TouchEvent) {
  const t = e.touches[0]
  if (!t) return
  mouseX.value = t.clientX
  mouseY.value = t.clientY
  dragMove(t.clientX, t.clientY)
}
function onTouchEnd(e: TouchEvent) {
  if ((e.target as HTMLElement)?.closest('.volume-ctrl, .tutorial-card')) return
  if (dragEnd()) handleTap()
}

function onVolume(e: Event) {
  setVolume(parseInt((e.target as HTMLInputElement).value))
}

// ── Canvas render loop ──
function animate() {
  const canvas = canvasEl.value
  if (!canvas) { animFrame = requestAnimationFrame(animate); return }
  const ctx = canvas.getContext('2d')!
  const dpr = window.devicePixelRatio || 1
  const w = window.innerWidth, h = window.innerHeight
  if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
    canvas.width = w * dpr
    canvas.height = h * dpr
    ctx.scale(dpr, dpr)
  }
  ctx.clearRect(0, 0, w, h)
  globalTime += 0.016

  // Damped drift toward drag target
  viewOffset.x += (dragTarget.x - viewOffset.x) * 0.028
  viewOffset.y += (dragTarget.y - viewOffset.y) * 0.028
  dragTarget.x *= 0.989
  dragTarget.y *= 0.989

  const wf = audioReady.value ? getWaveformData() : null
  const cat = categories[currentCatKey.value]
  cat?.draw(ctx, w, h, globalTime, mouseX.value, mouseY.value, wf, viewOffset)

  // Audio waveform ring
  if (wf) {
    const cx = w / 2 + viewOffset.x, cy = h / 2 + viewOffset.y
    const bR = Math.min(w, h) * 0.18
    ctx.beginPath()
    for (let i = 0; i < wf.length; i++) {
      const a = (i / wf.length) * Math.PI * 2
      const r = bR + (wf[i] - 128) / 128 * 25
      const x = cx + r * Math.cos(a), y = cy + r * Math.sin(a)
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    }
    ctx.closePath()
    ctx.strokeStyle = accentColor.value.replace(/[\d.]+\)$/, '0.15)')
    ctx.lineWidth = 1
    ctx.stroke()
  }

  // Vignette
  const vG = ctx.createRadialGradient(w / 2, h / 2, w * 0.2, w / 2, h / 2, w * 0.7)
  vG.addColorStop(0, 'rgba(8,6,13,0)')
  vG.addColorStop(1, 'rgba(8,6,13,0.7)')
  ctx.fillStyle = vG
  ctx.fillRect(0, 0, w, h)

  animFrame = requestAnimationFrame(animate)
}

// ── Tutorial ──
const TUTORIAL_KEY = 'trance-canvas-tutorial-done'
const tutorialActive = ref(!localStorage.getItem(TUTORIAL_KEY))

const tutorialSteps = [
  { phase: 'init', title: 'Binaural Beats', text: 'Two sine tones with a slight frequency gap create a perceived beat in your brain. Stereo headphones are essential.' },
  { phase: 'running', title: 'Interaction', text: 'Tap anywhere to shift categories. Drag slowly to push the visual center. Each category has its own gamma frequency.' },
  { phase: 'categories', title: 'Five Categories', text: 'Focus, Relaxation, Deepening, Sensory, and Suggestion \u2014 each mapped to a specific binaural beat and canvas visualization.' },
]

const tutorialStep = ref(0)

const tutorialInfo = computed(() => {
  if (!tutorialActive.value) return null
  if (!audioReady.value) return tutorialSteps[0]
  return tutorialSteps[tutorialStep.value] ?? null
})

function dismissTutorial() {
  if (tutorialStep.value < tutorialSteps.length - 1) {
    tutorialStep.value++
  } else {
    tutorialActive.value = false
    localStorage.setItem(TUTORIAL_KEY, '1')
  }
}

// ── Lifecycle ──
onMounted(() => {
  animate()
})

onUnmounted(() => {
  if (animFrame) cancelAnimationFrame(animFrame)
  destroyAudio()
})
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;1,300&family=JetBrains+Mono:wght@200;300&display=swap');

.trance-root {
  position: relative;
  width: 100%;
  height: 100vh;
  background: #08060d;
  overflow: hidden;
  cursor: none;
  user-select: none;
  font-family: 'Cormorant Garamond', serif;
  color: rgba(220, 210, 240, 0.9);
}

.canvas-layer {
  position: absolute;
  top: 0; left: 0;
  width: 100%; height: 100%;
  z-index: 1;
}

/* ── Init overlay ── */
.init-overlay {
  position: absolute;
  inset: 0;
  z-index: 50;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(8, 6, 13, 0.95);
  cursor: pointer;
}
.init-title {
  font-size: clamp(1.8rem, 4vw, 3.5rem);
  font-weight: 300;
  letter-spacing: 0.2em;
  color: rgba(220, 210, 240, 0.8);
  margin-bottom: 1rem;
}
.init-sub {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  font-weight: 200;
  color: rgba(180, 170, 200, 0.4);
  letter-spacing: 0.15em;
  text-transform: uppercase;
}
.init-warn {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  font-weight: 200;
  color: rgba(200, 140, 140, 0.5);
  letter-spacing: 0.12em;
  margin-top: 2rem;
}

.init-fade-leave-active { transition: opacity 0.8s ease; }
.init-fade-leave-to { opacity: 0; }

/* ── Text overlay ── */
.text-overlay {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.word-display {
  font-size: clamp(2rem, 6vw, 5rem);
  font-weight: 300;
  letter-spacing: 0.15em;
  text-transform: lowercase;
  text-align: center;
  line-height: 1.2;
  max-width: 80vw;
  transition: opacity 1.2s ease, transform 1.2s ease, filter 1.2s ease;
  filter: blur(0px);
}
.word-display.fading {
  opacity: 0;
  transform: scale(0.92) translateY(10px);
  filter: blur(6px);
}

.formula-display {
  font-family: 'JetBrains Mono', monospace;
  font-size: clamp(0.6rem, 1.2vw, 0.85rem);
  font-weight: 200;
  color: rgba(180, 170, 200, 0.5);
  margin-top: 2rem;
  letter-spacing: 0.08em;
  text-align: center;
  transition: opacity 1.5s ease;
}

.category-label {
  font-size: clamp(0.55rem, 1vw, 0.7rem);
  font-weight: 300;
  font-style: italic;
  color: rgba(180, 170, 200, 0.3);
  margin-bottom: 0.8rem;
  letter-spacing: 0.25em;
  text-transform: uppercase;
  transition: opacity 1.5s ease, color 1s ease;
}

.beat-info {
  font-family: 'JetBrains Mono', monospace;
  font-size: clamp(0.5rem, 0.9vw, 0.65rem);
  font-weight: 200;
  color: rgba(180, 170, 200, 0.25);
  margin-top: 0.6rem;
  letter-spacing: 0.1em;
  transition: opacity 1.5s ease;
}

.fading {
  opacity: 0;
}

/* ── Volume ── */
.volume-ctrl {
  position: absolute;
  bottom: 5vh; right: 2vw;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 8px;
  pointer-events: all;
  cursor: default;
}
.volume-ctrl label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.55rem;
  font-weight: 200;
  color: rgba(180, 170, 200, 0.3);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.volume-ctrl input[type="range"] {
  -webkit-appearance: none;
  appearance: none;
  width: 80px;
  height: 2px;
  background: rgba(180, 170, 200, 0.15);
  outline: none;
  border-radius: 1px;
  cursor: pointer;
}
.volume-ctrl input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 10px; height: 10px;
  border-radius: 50%;
  background: rgba(180, 170, 200, 0.5);
  cursor: pointer;
}
.volume-ctrl input[type="range"]::-moz-range-thumb {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: rgba(180, 170, 200, 0.5);
  cursor: pointer;
  border: none;
}

/* ── Click hint ── */
.click-hint {
  position: absolute;
  bottom: 3vh;
  left: 50%;
  transform: translateX(-50%);
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  font-weight: 200;
  color: rgba(180, 170, 200, 0.2);
  letter-spacing: 0.3em;
  text-transform: uppercase;
  z-index: 3;
  pointer-events: none;
  animation: pulse-hint 3s ease-in-out infinite;
}
@keyframes pulse-hint {
  0%, 100% { opacity: 0.15; }
  50% { opacity: 0.4; }
}


/* ── Cursor glow ── */
.cursor-glow {
  position: fixed;
  width: 40px; height: 40px;
  border-radius: 50%;
  pointer-events: none;
  z-index: 100;
  transform: translate(-50%, -50%);
  transition: background 0.8s;
  mix-blend-mode: screen;
}

/* ── Tutorial card ── */
.tutorial-card {
  position: absolute;
  bottom: 2rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  background: rgba(10, 10, 30, 0.85);
  border: 1px solid rgba(74, 144, 226, 0.3);
  border-radius: 12px;
  padding: 1rem 1.5rem;
  max-width: 420px;
  width: 90%;
  backdrop-filter: blur(8px);
  cursor: default;
  pointer-events: all;
}
.tutorial-title {
  font-size: 0.75rem;
  letter-spacing: 0.15em;
  color: #4a90e2;
  text-transform: uppercase;
  margin-bottom: 0.5rem;
}
.tutorial-text {
  font-size: 0.85rem;
  color: #ccc;
  line-height: 1.5;
}
.tutorial-dismiss {
  margin-top: 0.75rem;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #888;
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  font-size: 0.7rem;
  cursor: pointer;
  letter-spacing: 0.05em;
  transition: all 0.2s;
  font-family: inherit;
}
.tutorial-dismiss:hover {
  color: #ccc;
  border-color: rgba(255, 255, 255, 0.3);
}

.tutorial-slide-enter-active,
.tutorial-slide-leave-active {
  transition: all 0.4s ease;
}
.tutorial-slide-enter-from {
  opacity: 0;
  transform: translateX(-50%) translateY(12px);
}
.tutorial-slide-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}

/* ── Reader mode overlays ── */
.reader-word {
  font-size: clamp(1.8rem, 5vw, 4rem);
  letter-spacing: 0.08em;
}

.reader-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  margin-top: 1.5rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6rem;
  font-weight: 200;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: rgba(180, 170, 200, 0.35);
}

.reader-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.3);
  transition: background 0.3s;
}

.reader-dot.active {
  background: #6366f1;
  animation: reader-pulse 1s ease-in-out infinite alternate;
}

@keyframes reader-pulse {
  from { opacity: 0.5; }
  to { opacity: 1; }
}

.reader-progress-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: rgba(255, 255, 255, 0.04);
  z-index: 3;
}

.reader-progress-fill {
  height: 100%;
  background: rgba(99, 102, 241, 0.6);
  transition: width 0.15s linear;
}
</style>
