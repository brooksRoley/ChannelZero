<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import {
  useAdaptiveEntrain, PHASE_LABELS,
  type EntrainPhase,
} from '@/composables/useAdaptiveEntrain'
import { useTextOverlay } from '@/composables/useTextOverlay'
import { useAudioMixer } from '@/composables/useAudioMixer'

// ── Composables ──
const {
  active, phase, phaseLabel, phaseColor, bandLabel,
  currentHz, phaseProgress, beatPulse, coherence, behavior,
  cursorX, cursorY, phases,
  update: entrainUpdate, start: entrainStart, stop: entrainStop, windDown,
} = useAdaptiveEntrain()

const {
  displayText, displayLabel, isVisible, isReaderMode,
  readerProgress, isPlaying, toggleOrSkip: overlayToggle,
} = useTextOverlay()

const { tracks, toggleTrack, setVolume: setTrackVolume } = useAudioMixer()

// ── UI state ──
const canvasRef = ref<HTMLCanvasElement>()
const showMixer = ref(false)

const showGate = computed(() => !active.value && phase.value === 'idle')
const canWindDown = computed(() =>
  active.value && !['engage', 'integrate', 'complete', 'idle'].includes(phase.value)
)
const currentPhaseIdx = computed(() => phases.findIndex(p => p.name === phase.value))
const phaseLabelsShort: Record<EntrainPhase, string> = {
  idle: '', engage: 'ground', relax: 'soften',
  theta: 'deepen', hold: 'open', integrate: 'rise', complete: '',
}

// ── Canvas internals ──
let ctx: CanvasRenderingContext2D
let W = 0, H = 0, dpr = 1
let raf = 0, prevTs = 0
let orbX = 0, orbY = 0
let cr = 100, cg = 120, cb = 180

interface Particle { x: number; y: number; vx: number; vy: number; size: number; alpha: number }
let particles: Particle[] = []

interface Ripple { r: number; alpha: number }
let ripples: Ripple[] = []
let lastRippleT = 0

function initParticles() {
  const w = W || window.innerWidth
  const h = H || window.innerHeight
  particles = Array.from({ length: 70 }, () => ({
    x: Math.random() * w, y: Math.random() * h,
    vx: (Math.random() - 0.5) * 0.2, vy: (Math.random() - 0.5) * 0.2,
    size: 0.4 + Math.random() * 2, alpha: 0.04 + Math.random() * 0.16,
  }))
}

function resize() {
  const c = canvasRef.value
  if (!c) return
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  W = c.clientWidth
  H = c.clientHeight
  c.width = W * dpr
  c.height = H * dpr
  ctx = c.getContext('2d')!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  if (!particles.length) initParticles()
}

// ── Drawing ──
function drawClear() {
  ctx.fillStyle = `rgba(8,6,14,${0.12 + coherence.value * 0.03})`
  ctx.fillRect(0, 0, W, H)
}

function drawNebula(t: number) {
  const blobs = [[0.3, 0.35, 0.32], [0.68, 0.65, 0.28]]
  const a = 0.035 + (active.value ? coherence.value * 0.02 : 0)
  for (const [bx, by, br] of blobs) {
    const x = bx * W + Math.sin(t * 0.03 + bx * 9) * 18
    const y = by * H + Math.cos(t * 0.025 + by * 9) * 14
    const r = br * Math.min(W, H) * (0.9 + 0.1 * Math.sin(t * 0.02))
    const g = ctx.createRadialGradient(x, y, 0, x, y, r)
    g.addColorStop(0, `rgba(${cr},${cg},${cb},${a})`)
    g.addColorStop(0.5, `rgba(${cr},${cg},${cb},${a * 0.3})`)
    g.addColorStop(1, `rgba(${cr},${cg},${cb},0)`)
    ctx.fillStyle = g
    ctx.fillRect(0, 0, W, H)
  }
}

function drawBreathRing(t: number) {
  const cx = W / 2, cy = H / 2
  const breath = Math.sin(t * 0.12 * Math.PI * 2) * 0.5 + 0.5
  const minR = Math.min(W, H) * 0.12
  const maxR = Math.min(W, H) * 0.3
  const radius = minR + breath * (maxR - minR)
  const a = 0.05 + coherence.value * 0.04

  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.strokeStyle = `rgba(${cr},${cg},${cb},${a})`
  ctx.lineWidth = 1.2
  ctx.stroke()

  const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius)
  g.addColorStop(0, `rgba(${cr},${cg},${cb},${a * 0.2})`)
  g.addColorStop(1, `rgba(${cr},${cg},${cb},0)`)
  ctx.fillStyle = g
  ctx.beginPath()
  ctx.arc(cx, cy, radius, 0, Math.PI * 2)
  ctx.fill()
}

function stepAndDrawRipples(dt: number) {
  for (let i = ripples.length - 1; i >= 0; i--) {
    const rp = ripples[i]
    rp.r += dt * 70
    rp.alpha *= Math.exp(-dt * 1.2)
    if (rp.alpha < 0.004 || rp.r > Math.min(W, H) * 0.5) {
      ripples.splice(i, 1)
      continue
    }
    ctx.beginPath()
    ctx.arc(W / 2, H / 2, rp.r, 0, Math.PI * 2)
    ctx.strokeStyle = `rgba(${cr},${cg},${cb},${rp.alpha})`
    ctx.lineWidth = 0.8
    ctx.stroke()
  }
}

function stepParticles(dt: number) {
  const cx = W / 2, cy = H / 2
  const dt60 = dt * 60
  for (const p of particles) {
    // Center attraction + orbital tangent
    const dx = cx - p.x, dy = cy - p.y
    const dc = Math.hypot(dx, dy)
    if (dc > 15) {
      const f = 0.12 * dt60 / 60
      p.vx += (dx / dc) * f
      p.vy += (dy / dc) * f
      p.vx += (-dy / dc) * 0.06 * dt60 / 60
      p.vy += (dx / dc) * 0.06 * dt60 / 60
    }
    // Attraction toward follow-orb
    if (active.value) {
      const ox = orbX - p.x, oy = orbY - p.y
      const od = Math.hypot(ox, oy)
      if (od > 8 && od < 280) {
        const f = 0.08 * (1 - od / 280) * dt60 / 60
        p.vx += (ox / od) * f
        p.vy += (oy / od) * f
      }
    }
    p.vx += (Math.random() - 0.5) * 0.01
    p.vy += (Math.random() - 0.5) * 0.01
    p.vx *= 0.99
    p.vy *= 0.99
    const spd = Math.hypot(p.vx, p.vy)
    if (spd > 1.2) { p.vx *= 1.2 / spd; p.vy *= 1.2 / spd }
    p.x += p.vx
    p.y += p.vy
    if (p.x < -15) p.x = W + 15
    if (p.x > W + 15) p.x = -15
    if (p.y < -15) p.y = H + 15
    if (p.y > H + 15) p.y = -15
  }
}

function drawParticles() {
  for (const p of particles) {
    ctx.beginPath()
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(${cr},${cg},${cb},${p.alpha})`
    ctx.fill()
  }
}

function drawFollowOrb() {
  const pulse = beatPulse.value
  const r = 10 + pulse * 7 + coherence.value * 5
  const glowR = r * 3.5

  // Outer glow
  const gg = ctx.createRadialGradient(orbX, orbY, 0, orbX, orbY, glowR)
  gg.addColorStop(0, `rgba(${cr},${cg},${cb},${0.12 + pulse * 0.08})`)
  gg.addColorStop(0.4, `rgba(${cr},${cg},${cb},${0.03 + pulse * 0.02})`)
  gg.addColorStop(1, `rgba(${cr},${cg},${cb},0)`)
  ctx.fillStyle = gg
  ctx.beginPath()
  ctx.arc(orbX, orbY, glowR, 0, Math.PI * 2)
  ctx.fill()

  // Core
  const br = Math.min(255, cr + 55)
  const bg = Math.min(255, cg + 55)
  const bb = Math.min(255, cb + 55)
  const coreG = ctx.createRadialGradient(orbX, orbY, 0, orbX, orbY, r)
  coreG.addColorStop(0, `rgba(${br},${bg},${bb},${0.4 + pulse * 0.25})`)
  coreG.addColorStop(1, `rgba(${cr},${cg},${cb},0.05)`)
  ctx.fillStyle = coreG
  ctx.beginPath()
  ctx.arc(orbX, orbY, r, 0, Math.PI * 2)
  ctx.fill()
}

function drawHarmonicRings() {
  const coh = coherence.value
  if (coh < 0.35) return
  const cx = W / 2, cy = H / 2
  const pulse = beatPulse.value
  const baseA = (coh - 0.35) * 0.12
  for (let i = 0; i < 4; i++) {
    const r = Math.min(W, H) * (0.18 + i * 0.07) + pulse * 6
    const a = baseA * (1 - i * 0.22) * (0.4 + pulse * 0.6)
    ctx.beginPath()
    ctx.arc(cx, cy, r, 0, Math.PI * 2)
    ctx.strokeStyle = `rgba(${cr},${cg},${cb},${a})`
    ctx.lineWidth = 0.5
    ctx.stroke()
  }
}

function drawVignette() {
  const g = ctx.createRadialGradient(
    W / 2, H / 2, Math.min(W, H) * 0.2,
    W / 2, H / 2, Math.max(W, H) * 0.65,
  )
  g.addColorStop(0, 'rgba(8,6,14,0)')
  g.addColorStop(1, `rgba(8,6,14,${0.45 + coherence.value * 0.15})`)
  ctx.fillStyle = g
  ctx.fillRect(0, 0, W, H)
}

// ── Frame loop ──
function frame(ts: number) {
  if (!ctx) { raf = requestAnimationFrame(frame); return }
  if (!prevTs) prevTs = ts
  const dt = Math.min((ts - prevTs) / 1000, 0.1)
  const t = ts / 1000
  prevTs = ts

  entrainUpdate(dt)

  // Phase color cache
  const hex = phaseColor.value
  cr = parseInt(hex.slice(1, 3), 16)
  cg = parseInt(hex.slice(3, 5), 16)
  cb = parseInt(hex.slice(5, 7), 16)

  // Smooth follow orb
  orbX += (cursorX.value - orbX) * Math.min(1, dt * 1.5)
  orbY += (cursorY.value - orbY) * Math.min(1, dt * 1.5)

  // Emit ripples
  if (active.value && phase.value !== 'complete') {
    const interval = (12 / Math.max(currentHz.value, 1)) * 0.8
    if (t - lastRippleT > interval) {
      ripples.push({ r: 5, alpha: 0.1 + coherence.value * 0.06 })
      lastRippleT = t
    }
  }

  // Render layers
  drawClear()
  drawNebula(t)
  stepParticles(dt)
  drawParticles()

  if (active.value && phase.value !== 'complete') {
    drawBreathRing(t)
    stepAndDrawRipples(dt)
    drawFollowOrb()
    drawHarmonicRings()
  }

  drawVignette()
  raf = requestAnimationFrame(frame)
}

// ── Interaction ──
function handleTap() {
  if (phase.value === 'complete') return
  if (!active.value) {
    entrainStart()
    return
  }
  overlayToggle()
}

// ── Lifecycle ──
onMounted(() => {
  resize()
  initParticles()
  orbX = W / 2
  orbY = H / 2
  window.addEventListener('resize', resize)
  raf = requestAnimationFrame(frame)
})

onUnmounted(() => {
  if (raf) cancelAnimationFrame(raf)
  entrainStop()
  window.removeEventListener('resize', resize)
})
</script>

<template>
  <div
    class="entrain"
    :tabindex="phase !== 'complete' ? 0 : -1"
    @click="handleTap"
    @keydown.space.prevent="handleTap"
    @keydown.enter.prevent="handleTap"
  >
    <canvas ref="canvasRef" class="entrain-canvas" aria-hidden="true" />

    <!-- Gate overlay -->
    <Transition name="gate">
      <div v-if="showGate" class="gate-overlay">
        <h1 class="gate-title">adaptive entrainment</h1>
        <p class="gate-sub">tap or press space to begin</p>
        <p class="gate-hint">stereo headphones required for binaural effect</p>
      </div>
    </Transition>

    <!-- Complete overlay -->
    <Transition name="gate">
      <div v-if="phase === 'complete'" class="gate-overlay">
        <h1 class="gate-title">session complete</h1>
      </div>
    </Transition>

    <!-- Text overlay -->
    <div v-if="active && phase !== 'complete'" class="text-layer">
      <div v-if="displayLabel" class="text-label" :class="{ dim: !isVisible }">{{ displayLabel }}</div>
      <span class="text-word" :class="[{ dim: !isVisible }, isReaderMode ? 'reader-text' : '']">
        {{ displayText }}
      </span>
      <div v-if="isReaderMode" class="reader-status">
        <span class="status-dot" :class="{ on: isPlaying }" />
        {{ isPlaying ? 'reading' : 'paused' }}
      </div>
    </div>

    <!-- Screen reader phase status -->
    <div v-if="active" class="sr-only" role="status" aria-live="polite">{{ phaseLabel }}</div>

    <!-- Phase journey bar -->
    <div v-if="active && phase !== 'complete'" class="journey-bar" aria-hidden="true">
      <div
        v-for="(p, i) in phases"
        :key="p.name"
        class="journey-seg"
        :class="{ active: currentPhaseIdx === i, done: currentPhaseIdx > i }"
      >
        <div class="seg-track">
          <div
            class="seg-fill"
            :style="currentPhaseIdx === i ? { width: `${phaseProgress * 100}%` } : {}"
          />
        </div>
        <span class="seg-name">{{ phaseLabelsShort[p.name] }}</span>
      </div>
    </div>

    <!-- HUD -->
    <div v-if="active && phase !== 'complete'" class="hud">
      <div class="hud-left">
        <span class="hz-val">{{ currentHz.toFixed(1) }}</span>
        <span class="hz-unit">Hz</span>
        <span class="band-tag" :style="{ borderColor: phaseColor, color: phaseColor }">
          {{ bandLabel }}
        </span>
      </div>
      <div class="hud-center">
        <span class="phase-name" :style="{ color: phaseColor }">{{ phaseLabel }}</span>
      </div>
      <div class="hud-right">
        <span class="coh-val">{{ Math.round(coherence * 100) }}</span>
        <span class="coh-pct">%</span>
        <span class="coh-label">sync</span>
      </div>
    </div>

    <!-- Mixer toggle -->
    <button v-if="active" class="mixer-toggle" @click.stop="showMixer = !showMixer" aria-label="Toggle mixer">
      <svg v-if="!showMixer" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M9 19V6l12-3v13M9 19c0 1.1-1.3 2-3 2s-3-.9-3-2 1.3-2 3-2 3 .9 3 2zm12-3c0 1.1-1.3 2-3 2s-3-.9-3-2 1.3-2 3-2 3 .9 3 2z"/>
      </svg>
      <span v-else class="mixer-close">&times;</span>
    </button>

    <!-- Mixer panel -->
    <Transition name="panel-slide">
      <div v-if="showMixer" class="mixer-panel" @click.stop>
        <div class="mixer-header">background</div>
        <div v-for="track in tracks" :key="track.id" class="mini-track">
          <button
            class="mini-play"
            :class="{ on: track.playing }"
            :aria-label="`${track.playing ? 'Pause' : 'Play'} ${track.name}`"
            @click="toggleTrack(track.id)"
          >
            <span aria-hidden="true">{{ track.playing ? '\u23F8' : '\u25B6' }}</span>
          </button>
          <span class="mini-name">{{ track.name }}</span>
          <input
            type="range" class="mini-vol" min="0" max="1" step="0.01"
            :value="track.volume"
            :aria-label="`${track.name} volume`"
            @input="setTrackVolume(track.id, parseFloat(($event.target as HTMLInputElement).value))"
          />
        </div>
        <hr class="mixer-divider" />
        <button v-if="canWindDown" class="mixer-btn wind-btn" @click="windDown()">Wind Down</button>
        <button class="mixer-btn stop-btn" @click="entrainStop()">End Session</button>
      </div>
    </Transition>

    <!-- Reader progress -->
    <div
      v-if="isReaderMode && active"
      class="progress-track"
      role="progressbar"
      :aria-valuenow="Math.round(readerProgress)"
      aria-valuemin="0"
      aria-valuemax="100"
      aria-label="Reader progress"
    >
      <div class="progress-fill" :style="{ width: `${readerProgress}%` }" />
    </div>
  </div>
</template>

<style scoped>
.entrain {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: #08060e;
  cursor: pointer;
}

.entrain-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

/* ── Gate overlay ── */
.gate-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 20;
  pointer-events: none;
}

.gate-title {
  font-size: clamp(1.2rem, 3vw, 2rem);
  font-weight: 300;
  letter-spacing: 0.2em;
  text-transform: lowercase;
  color: rgba(180, 170, 210, 0.7);
  margin: 0 0 0.8rem;
}

.gate-sub {
  font-size: clamp(0.7rem, 1.5vw, 0.9rem);
  color: rgba(148, 163, 184, 0.5);
  letter-spacing: 0.15em;
  margin: 0 0 1.5rem;
}

.gate-hint {
  font-size: 0.6rem;
  color: rgba(100, 116, 139, 0.4);
  letter-spacing: 0.1em;
  margin: 0;
}

.gate-enter-active,
.gate-leave-active {
  transition: opacity 1.2s ease;
}
.gate-enter-from,
.gate-leave-to {
  opacity: 0;
}

/* ── Text layer ── */
.text-layer {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 10;
  text-align: center;
  pointer-events: none;
}

.text-label {
  font-size: clamp(0.5rem, 1vw, 0.65rem);
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: rgba(160, 150, 200, 0.3);
  margin-bottom: 0.8rem;
  transition: opacity 0.6s ease;
}

.text-label.dim { opacity: 0; }

.text-word {
  font-family: 'Georgia', serif;
  font-size: clamp(2rem, 5vw, 4rem);
  font-weight: 300;
  font-style: italic;
  letter-spacing: 0.12em;
  text-transform: lowercase;
  color: rgba(220, 215, 240, 0.85);
  text-shadow:
    0 0 30px rgba(140, 120, 200, 0.35),
    0 0 60px rgba(100, 80, 180, 0.15);
  max-width: 85vw;
  line-height: 1.3;
  transition: opacity 0.8s ease;
  display: block;
}

.text-word.dim { opacity: 0; }

.text-word.reader-text {
  font-style: normal;
  font-size: clamp(1.6rem, 4vw, 3.2rem);
  letter-spacing: 0.06em;
  text-transform: none;
  color: rgba(230, 225, 245, 0.9);
  text-shadow: 0 0 24px rgba(140, 120, 200, 0.25);
  transition: none;
}

.reader-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  margin-top: 1rem;
  font-size: 0.55rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(148, 163, 184, 0.4);
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
  animation: pulse-dot 1s ease-in-out infinite alternate;
}

@keyframes pulse-dot {
  from { opacity: 0.5; }
  to { opacity: 1; }
}

/* ── Journey bar ── */
.journey-bar {
  position: absolute;
  bottom: 3rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  display: flex;
  gap: 3px;
  pointer-events: none;
}

.journey-seg {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 3.5rem;
}

.seg-track {
  width: 100%;
  height: 2px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 1px;
  overflow: hidden;
}

.seg-fill {
  height: 100%;
  background: rgba(148, 163, 184, 0.3);
  transition: width 0.3s linear;
  width: 0%;
}

.journey-seg.done .seg-fill { width: 100% !important; }
.journey-seg.active .seg-fill { background: rgba(180, 170, 220, 0.5); }
.journey-seg.active .seg-track { background: rgba(255, 255, 255, 0.08); }

.seg-name {
  font-size: 0.45rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: rgba(148, 163, 184, 0.2);
}

.journey-seg.active .seg-name,
.journey-seg.done .seg-name {
  color: rgba(148, 163, 184, 0.45);
}

/* ── HUD ── */
.hud {
  position: absolute;
  bottom: 0.75rem;
  left: 1.5rem;
  right: 1.5rem;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  pointer-events: none;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}

.hud-left,
.hud-right {
  display: flex;
  align-items: baseline;
  gap: 0.2rem;
}

.hud-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  bottom: 0;
}

.hz-val {
  font-size: 0.9rem;
  font-weight: 300;
  color: rgba(226, 232, 240, 0.4);
  font-variant-numeric: tabular-nums;
}

.hz-unit {
  font-size: 0.5rem;
  color: rgba(148, 163, 184, 0.25);
  text-transform: uppercase;
}

.band-tag {
  font-size: 0.45rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 0.1rem 0.35rem;
  border: 1px solid;
  border-radius: 0.75rem;
  margin-left: 0.4rem;
  opacity: 0.6;
}

.phase-name {
  font-size: 0.5rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  opacity: 0.5;
}

.coh-val {
  font-size: 0.9rem;
  font-weight: 300;
  color: rgba(226, 232, 240, 0.4);
  font-variant-numeric: tabular-nums;
}

.coh-pct {
  font-size: 0.5rem;
  color: rgba(148, 163, 184, 0.25);
}

.coh-label {
  font-size: 0.45rem;
  color: rgba(148, 163, 184, 0.2);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-left: 0.2rem;
}

/* ── Mixer toggle ── */
.mixer-toggle {
  position: absolute;
  top: 1rem;
  left: 1rem;
  z-index: 25;
  width: 2.2rem;
  height: 2.2rem;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(10, 10, 20, 0.5);
  color: rgba(148, 163, 184, 0.4);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  transition: all 0.2s;
}

.mixer-toggle:hover {
  border-color: rgba(255, 255, 255, 0.18);
  color: rgba(226, 232, 240, 0.7);
}

.mixer-toggle svg {
  width: 14px;
  height: 14px;
}

.mixer-close {
  font-size: 1.2rem;
  line-height: 1;
}

/* ── Mixer panel ── */
.mixer-panel {
  position: absolute;
  top: 4rem;
  left: 1rem;
  z-index: 25;
  background: rgba(10, 10, 25, 0.88);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 0.75rem;
  padding: 0.75rem;
  min-width: 210px;
  pointer-events: auto;
}

.mixer-header {
  font-size: 0.55rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(148, 163, 184, 0.35);
  margin-bottom: 0.5rem;
}

.mini-track {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.4rem;
}

.mini-play {
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  border: 1px solid rgba(99, 102, 241, 0.3);
  background: transparent;
  color: rgba(226, 232, 240, 0.5);
  cursor: pointer;
  font-size: 0.55rem;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  flex-shrink: 0;
  transition: all 0.15s;
}

.mini-play:active {
  transform: scale(0.92);
}

.mini-play.on {
  background: rgba(99, 102, 241, 0.25);
  border-color: rgba(99, 102, 241, 0.5);
}

.mini-name {
  font-size: 0.7rem;
  color: rgba(226, 232, 240, 0.55);
  flex: 1;
}

.mini-vol {
  width: 55px;
  height: 2px;
  -webkit-appearance: none;
  appearance: none;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 1px;
  outline: none;
}

.mini-vol::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(226, 232, 240, 0.45);
  cursor: pointer;
}

.mini-vol::-moz-range-thumb {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(226, 232, 240, 0.45);
  border: none;
  cursor: pointer;
}

.mixer-divider {
  border: none;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  margin: 0.5rem 0;
}

.mixer-btn {
  width: 100%;
  padding: 0.35rem;
  border-radius: 0.35rem;
  border: 1px solid rgba(255, 255, 255, 0.07);
  background: rgba(255, 255, 255, 0.03);
  color: rgba(226, 232, 240, 0.5);
  font-size: 0.65rem;
  font-family: inherit;
  cursor: pointer;
  margin-bottom: 0.25rem;
  transition: all 0.15s;
}

.mixer-btn:hover {
  background: rgba(255, 255, 255, 0.07);
}

.mixer-btn:active {
  transform: scale(0.97);
}

.wind-btn { border-color: rgba(224, 144, 64, 0.25); }
.wind-btn:hover { background: rgba(224, 144, 64, 0.1); }
.stop-btn { border-color: rgba(220, 38, 38, 0.2); }
.stop-btn:hover { background: rgba(220, 38, 38, 0.1); }

.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.panel-slide-enter-from,
.panel-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
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

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
