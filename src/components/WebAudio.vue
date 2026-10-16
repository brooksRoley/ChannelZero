<template>
  <div class="trance-container" :style="{ opacity: avFlash ? 0.8 : 1 }">
    <canvas ref="canvasBus" class="spiral-canvas"></canvas>

    <!-- Breathing pacer ring — coherence phase only -->
    <div
      v-if="phase === 'coherence'"
      class="pacer-ring"
      :class="{ expanding: isExpanding }"
      :style="{ borderColor: phaseAccent + '88', boxShadow: `0 0 30px ${phaseAccent}44` }"
    ></div>

    <!-- ── Idle: begin screen ── -->
    <div v-if="!sessionActive" class="begin-screen">
      <h1 class="begin-title">Binaural Induction</h1>
      <p class="begin-sub">Use stereo headphones for full effect</p>
      <button @click="startSession()" class="start-btn">BEGIN ENTRAINMENT</button>
    </div>

    <!-- ── Narrative phases: floating text on tunnel ── -->
    <div v-else-if="isNarrativePhase" class="narrative-layer">
      <Transition name="phrase-fade" mode="out-in">
        <p :key="currentInstruction" class="narrative-text" :style="{ color: '#fff', textShadow: `0 0 40px ${phaseAccent}` }">
          {{ currentInstruction }}
        </p>
      </Transition>

      <div class="narrative-foot">
        <button
          v-if="phase === 'deepen'"
          class="wind-down-btn"
          @click="windDown"
        >Wind Down</button>
        <button class="stop-btn" @click="stopSession">End Session</button>
      </div>
    </div>

    <!-- ── Coherence phase: pacer UI ── -->
    <div v-else-if="phase === 'coherence'" class="coherence-layer">
      <nav class="hud-top">
        <div class="stat">
          <label>COHERENCE</label>
          <span :class="{ linked: coherenceScore > 70 }">{{ coherenceScore }}%</span>
        </div>
        <div class="stat">
          <label>PHASE</label>
          <span>COHERENCE</span>
        </div>
      </nav>

      <Transition name="phrase-fade" mode="out-in">
        <h2 :key="currentInstruction" class="instruction-text" :style="{ textShadow: `0 0 20px ${phaseAccent}88` }">
          {{ currentInstruction }}
        </h2>
      </Transition>

      <p class="sync-hint">Hold to match the pulse</p>

      <button
        @pointerdown="startSync"
        @pointerup="stopSync"
        class="sync-pad"
        :class="{ syncing: isSyncing }"
        :style="{ borderColor: phaseAccent }"
      >HOLD TO SYNC</button>

      <button class="stop-btn" @click="stopSession">End Session</button>
    </div>

    <!-- Tutorial overlay -->
    <div v-if="tutorialInfo" class="tutorial-card">
      <div class="tutorial-title">{{ tutorialInfo.title }}</div>
      <div class="tutorial-text">{{ tutorialInfo.text }}</div>
      <button class="tutorial-dismiss" @click="dismissTutorial">Dismiss Tutorial</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useTranceEngine } from '@/composables/useTranceEngine'

const {
  phase,
  sessionActive,
  coherenceScore,
  progress,
  isExpanding,
  currentInstruction,
  isSyncing,
  tunnelPulseStrength,
  avSyncActive,
  phaseAccent,
  isNarrativePhase,
  startSession,
  stopSession,
  windDown,
  startSync,
  stopSync,
  toggleAVSync,
} = useTranceEngine()

// --- Star Field (visual only) ---
const STAR_COUNT = 400
const stars = []

class Star {
  constructor(canvas) {
    this.reset(canvas)
  }
  reset(canvas) {
    this.x = (Math.random() - 0.5) * canvas.width * 2
    this.y = (Math.random() - 0.5) * canvas.height * 2
    this.z = canvas.width
    this.px = 0
    this.py = 0
  }
  update(speed, canvas) {
    this.px = this.x / (this.z / canvas.width)
    this.py = this.y / (this.z / canvas.width)
    this.z -= speed
    if (this.z < 1) this.reset(canvas)
  }
}

const canvasBus = ref(null)
const avFlash = ref(false)
let animFrameId

// --- AV Sync flash handler ---
function onAVFlash(flash) {
  avFlash.value = flash
}

// --- Tutorial ---
const tutorialActive = ref(!localStorage.getItem('trance-tutorial-done'))

const tutorialInfo = computed(() => {
  if (!tutorialActive.value) return null
  switch (phase.value) {
    case 'idle':
      return {
        title: 'Welcome',
        text: 'Use stereo headphones for the full binaural effect. Click BEGIN ENTRAINMENT to start your session.',
      }
    case 'induction':
      return {
        title: 'Induction Phase',
        text: 'Binaural tones are synchronizing. Breathe slowly and follow the rhythm. This phase lasts ~30 seconds.',
      }
    case 'coherence':
      return {
        title: 'Coherence Phase',
        text: 'The ring expands on inhale, contracts on exhale. Hold SYNC to match your breath. Aim for 70% coherence.',
      }
    case 'deepen':
      return {
        title: 'Deep Entrainment',
        text: 'You\'ve achieved coherence. Bass pulses drive deeper. Try additional modules from the navbar menu.',
      }
    default:
      return null
  }
})

function dismissTutorial() {
  tutorialActive.value = false
  localStorage.setItem('trance-tutorial-done', '1')
}

// --- Tunnel Rendering ---
// Interpolates smoothly toward phaseAccent each frame
let currentTrailColor = { r: 255, g: 255, b: 255 }

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return { r, g, b }
}

const renderTunnel = () => {
  if (!canvasBus.value) return
  const ctx = canvasBus.value.getContext('2d')
  const { width, height } = canvasBus.value

  // Joy/wake phases: warm canvas bg tint
  const isWarm = phase.value === 'joy' || phase.value === 'wake'
  ctx.fillStyle = isWarm ? 'rgba(8, 4, 0, 0.15)' : 'rgba(0, 0, 0, 0.15)'
  ctx.fillRect(0, 0, width, height)

  const currentSpeed = 5 + tunnelPulseStrength.value * 20
  tunnelPulseStrength.value *= 0.9

  // Smoothly lerp trail color toward phase accent
  const target = hexToRgb(phaseAccent.value)
  currentTrailColor.r += (target.r - currentTrailColor.r) * 0.02
  currentTrailColor.g += (target.g - currentTrailColor.g) * 0.02
  currentTrailColor.b += (target.b - currentTrailColor.b) * 0.02
  const { r, g, b } = currentTrailColor
  ctx.strokeStyle = `rgb(${Math.round(r)},${Math.round(g)},${Math.round(b)})`

  ctx.beginPath()
  stars.forEach((star) => {
    star.update(currentSpeed, canvasBus.value)
    const x2d = star.x / (star.z / width) + width / 2
    const y2d = star.y / (star.z / height) + height / 2
    if (star.px !== 0) {
      ctx.moveTo(star.px + width / 2, star.py + height / 2)
      ctx.lineTo(x2d, y2d)
    }
  })
  ctx.stroke()

  animFrameId = requestAnimationFrame(renderTunnel)
}

function resizeCanvas() {
  if (!canvasBus.value) return
  canvasBus.value.width = window.innerWidth
  canvasBus.value.height = window.innerHeight
}

onMounted(() => {
  resizeCanvas()

  for (let i = 0; i < STAR_COUNT; i++) {
    stars.push(new Star(canvasBus.value))
  }

  renderTunnel()
  window.addEventListener('resize', resizeCanvas)
})

onUnmounted(() => {
  if (animFrameId) cancelAnimationFrame(animFrameId)
  window.removeEventListener('resize', resizeCanvas)
})
</script>

<style scoped>
.trance-container {
  background: #050505;
  height: 100vh;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  transition: opacity 0.05s ease;
  position: relative;
}

.spiral-canvas {
  position: absolute;
  z-index: 1;
}

/* Pacer ring */
.pacer-ring {
  position: absolute;
  width: 320px;
  height: 320px;
  border-radius: 50%;
  border: 2px solid rgba(74, 144, 226, 0.5);
  box-shadow: 0 0 20px rgba(74, 144, 226, 0.2);
  transform: scale(0.75);
  transition:
    transform 5s linear,
    box-shadow 5s linear;
  z-index: 2;
  pointer-events: none;
}

.pacer-ring.expanding {
  transform: scale(1.35);
  box-shadow: 0 0 40px rgba(74, 144, 226, 0.5);
}

/* ── Begin screen ── */
.begin-screen {
  position: relative;
  z-index: 3;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.begin-title {
  font-size: 1.4rem;
  font-weight: 300;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.75);
}

.begin-sub {
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  color: rgba(255, 255, 255, 0.3);
  text-transform: uppercase;
  margin: 0;
}

.start-btn {
  margin-top: 0.5rem;
  padding: 0.9rem 2.5rem;
  border-radius: 50px;
  border: 1px solid rgba(74, 144, 226, 0.5);
  background: rgba(74, 144, 226, 0.08);
  color: rgba(255, 255, 255, 0.85);
  font-size: 0.82rem;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.3s;
}

.start-btn:hover {
  background: rgba(74, 144, 226, 0.2);
  border-color: rgba(74, 144, 226, 0.8);
  box-shadow: 0 0 30px rgba(74, 144, 226, 0.25);
  color: #fff;
}

/* ── Narrative layer — floating text on tunnel ── */
.narrative-layer {
  position: relative;
  z-index: 3;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2.5rem;
  width: 100%;
  max-width: 640px;
  padding: 2rem;
  text-align: center;
}

.narrative-text {
  font-size: clamp(1.6rem, 4vw, 2.4rem);
  font-weight: 300;
  letter-spacing: 0.12em;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.92);
  margin: 0;
}

.narrative-foot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.wind-down-btn {
  padding: 0.55rem 1.5rem;
  border-radius: 24px;
  border: 1px solid rgba(224, 144, 64, 0.4);
  background: rgba(224, 144, 64, 0.08);
  color: rgba(224, 144, 64, 0.85);
  font-size: 0.78rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.25s;
}

.wind-down-btn:hover {
  background: rgba(224, 144, 64, 0.18);
  border-color: rgba(224, 144, 64, 0.7);
  color: #e09040;
}

/* ── Coherence layer ── */
.coherence-layer {
  position: relative;
  z-index: 3;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 2rem;
}

/* HUD */
.hud-top {
  display: flex;
  justify-content: space-around;
  gap: 2rem;
  margin-bottom: 0.5rem;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}

.stat label {
  font-size: 0.6rem;
  letter-spacing: 0.15em;
  color: rgba(255,255,255,0.35);
  text-transform: uppercase;
}

.stat span {
  font-size: 1.1rem;
  font-weight: 500;
  color: #4a90e2;
  transition: color 0.5s, text-shadow 0.5s;
}

.stat span.linked {
  color: #7fff7f;
  text-shadow: 0 0 12px rgba(127, 255, 127, 0.6);
}

/* Crossfade for all instruction text */
.phrase-fade-enter-active,
.phrase-fade-leave-active {
  transition: opacity 0.55s ease, transform 0.55s ease;
}
.phrase-fade-enter-from {
  opacity: 0;
  transform: translateY(10px);
}
.phrase-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.instruction-text {
  font-size: clamp(1.4rem, 3.5vw, 2rem);
  font-weight: 300;
  letter-spacing: 0.22em;
  margin: 0;
  color: rgba(255, 255, 255, 0.9);
  text-transform: uppercase;
}

.sync-hint {
  font-size: 0.72rem;
  color: rgba(255,255,255,0.3);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin: 0;
}

.sync-pad {
  padding: 18px 42px;
  border-radius: 50px;
  border: 1px solid #4a90e2;
  background: transparent;
  color: white;
  cursor: pointer;
  letter-spacing: 0.12em;
  font-size: 0.78rem;
  text-transform: uppercase;
  font-family: inherit;
  transition: all 0.3s;
}

.sync-pad:active,
.sync-pad.syncing {
  background: rgba(74, 144, 226, 0.2);
  box-shadow: 0 0 24px rgba(74, 144, 226, 0.35);
}

.stop-btn {
  display: block;
  margin: 0 auto;
  padding: 0.35rem 1rem;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: transparent;
  color: rgba(255,255,255,0.25);
  font-size: 0.65rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.2s;
}

.stop-btn:hover {
  color: rgba(255,100,100,0.7);
  border-color: rgba(255,100,100,0.3);
}

/* Tutorial card */
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
}

.tutorial-dismiss:hover {
  color: #ccc;
  border-color: rgba(255, 255, 255, 0.3);
}
</style>
