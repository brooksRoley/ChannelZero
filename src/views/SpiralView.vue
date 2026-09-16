<script setup lang="ts">
import { ref, watch } from 'vue'
import { useAnimationCanvas, type AnimationContext } from '@/composables/useAnimationCanvas'
import { useTextOverlay } from '@/composables/useTextOverlay'
import { categories } from '@/composables/useTranceCategories'
import { useTranceEngine } from '@/composables/useTranceEngine'
import PostTranceOverlay from '@/components/PostTranceOverlay.vue'

const canvasRef = ref<HTMLCanvasElement>()
const {
  displayText,
  displayLabel,
  activeCatKey,
  isVisible,
  isReaderMode,
  readerProgress,
  isPlaying,
  toggleOrSkip
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

// Map category keys to spiral color tints
const catColorMap: Record<string, [number, number, number]> = {
  focus:       [140, 160, 255],
  relaxation:  [160, 120, 255],
  deepening:   [120, 80, 200],
  sensory:     [100, 200, 180],
  suggestion:  [180, 160, 220]
}

function drawSpiral({ ctx, width, height, time }: AnimationContext) {
  const cx = width / 2
  const cy = height / 2
  const maxRadius = Math.max(width, height) * 0.7
  const col = catColorMap[activeCatKey.value] ?? [140, 160, 255]

  // Multiple spiral layers
  for (let layer = 0; layer < 3; layer++) {
    const arms = 2 + layer
    const rotations = 6 + layer * 2
    const lineWidth = 3 - layer * 0.8
    const spiralRot = time * 0.5 * (1 + layer * 0.3)

    for (let arm = 0; arm < arms; arm++) {
      ctx.beginPath()
      const armOffset = (arm / arms) * Math.PI * 2
      const points = 500

      for (let i = 0; i <= points; i++) {
        const p = i / points
        const angle = p * Math.PI * 2 * rotations + armOffset - spiralRot
        const r = p * maxRadius
        const breathe = 1 + 0.08 * Math.sin(p * 15 - time * 4 + layer)
        const x = cx + Math.cos(angle) * r * breathe
        const y = cy + Math.sin(angle) * r * breathe

        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }

      const alpha = (0.15 + 0.1 * Math.sin(time * 2 + (layer * 0.33) * Math.PI * 2)) * (1 - layer * 0.25)
      ctx.strokeStyle = `rgba(${col[0]}, ${col[1]}, ${col[2]}, ${alpha})`
      ctx.lineWidth = lineWidth
      ctx.stroke()
    }
  }

  // Central glow
  const glowSize = 80 + 30 * Math.sin(time * 1.5)
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowSize)
  grad.addColorStop(0, `rgba(${col[0]}, ${col[1]}, ${col[2]}, 0.15)`)
  grad.addColorStop(0.5, `rgba(${col[0]}, ${col[1]}, ${col[2]}, 0.05)`)
  grad.addColorStop(1, 'rgba(0, 0, 0, 0)')
  ctx.fillStyle = grad
  ctx.beginPath()
  ctx.arc(cx, cy, glowSize, 0, Math.PI * 2)
  ctx.fill()

  // Concentric rings pulsing outward
  for (let i = 0; i < 12; i++) {
    const phase = (time * 0.8 + i / 12) % 1
    const radius = phase * maxRadius
    const a = (1 - phase) * 0.08
    ctx.strokeStyle = `rgba(180, 160, 240, ${a})`
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.arc(cx, cy, radius, 0, Math.PI * 2)
    ctx.stroke()
  }

  // Floating particles drifting toward center
  for (let i = 0; i < 60; i++) {
    const seed = i * 137.508
    const phase = (time * 0.3 + (seed % 1)) % 1
    const angle = seed + time * 0.5
    const dist = (1 - phase) * maxRadius * 0.8
    const px = cx + Math.cos(angle) * dist
    const py = cy + Math.sin(angle) * dist
    const size = (1 - phase) * 2
    const a = Math.sin(phase * Math.PI) * 0.4
    ctx.fillStyle = `rgba(200, 190, 255, ${a})`
    ctx.beginPath()
    ctx.arc(px, py, size, 0, Math.PI * 2)
    ctx.fill()
  }
}

useAnimationCanvas(canvasRef, {
  draw: drawSpiral,
  plasmaBackground: true,
  plasmaIntensity: 0.35,
  snowCount: 100
})
</script>

<template>
  <div
    class="spiral-view"
    role="button"
    tabindex="0"
    aria-label="Spiral trance visualization — press Space or Enter to advance"
    @click="toggleOrSkip"
    @keydown.space.prevent="toggleOrSkip"
    @keydown.enter.prevent="toggleOrSkip"
  >
    <canvas ref="canvasRef" class="spiral-canvas" aria-hidden="true" />

    <div class="word-overlay" aria-live="polite" aria-atomic="true">
      <div v-if="displayLabel" class="category-label">{{ displayLabel }}</div>
      <div :class="['word-display', { visible: isVisible }]">{{ displayText }}</div>
    </div>

    <!-- Reader progress bar -->
    <div
      v-if="isReaderMode"
      class="reader-progress"
      role="progressbar"
      :aria-valuenow="Math.round(readerProgress)"
      aria-valuemin="0"
      aria-valuemax="100"
      aria-label="Reading progress"
    >
      <div class="reader-progress-fill" :style="{ width: `${readerProgress}%` }" />
    </div>

    <!-- Reader play state indicator -->
    <div v-if="isReaderMode" class="reader-badge">
      <span class="reader-dot" :class="{ active: isPlaying }" />
      {{ isPlaying ? 'reading' : 'paused' }}
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
.spiral-view {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: #000;
  cursor: pointer;
}

.spiral-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.word-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 10;
  text-align: center;
  pointer-events: none;
}

.category-label {
  font-size: clamp(0.6rem, 1.2vw, 0.8rem);
  color: rgba(180, 160, 220, 0.4);
  letter-spacing: 0.3em;
  text-transform: uppercase;
  margin-bottom: 1rem;
  font-weight: 400;
}

.word-display {
  font-size: clamp(2.5rem, 6vw, 5rem);
  font-weight: 300;
  color: white;
  font-family: 'Georgia', serif;
  text-shadow:
    0 0 30px rgba(255, 255, 255, 0.6),
    0 0 60px rgba(180, 140, 255, 0.4),
    0 0 100px rgba(140, 100, 255, 0.2);
  min-height: 6rem;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 0.15em;
  text-transform: lowercase;
  font-style: italic;
  opacity: 0;
  transition: opacity 1.2s ease-in-out;
}

.word-display.visible {
  opacity: 1;
}

/* Reader progress bar */
.reader-progress {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: rgba(255, 255, 255, 0.04);
  z-index: 10;
}

.reader-progress-fill {
  height: 100%;
  background: rgba(99, 102, 241, 0.6);
  transition: width 0.15s linear;
}

/* Reader badge */
.reader-badge {
  position: absolute;
  bottom: 1.5rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.6rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: rgba(148, 163, 184, 0.5);
  pointer-events: none;
}

.reader-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.4);
  transition: background 0.3s;
}

.reader-dot.active {
  background: #6366f1;
  animation: pulse-dot 1s ease-in-out infinite alternate;
}

@keyframes pulse-dot {
  from { opacity: 0.5; }
  to { opacity: 1; }
}
</style>
