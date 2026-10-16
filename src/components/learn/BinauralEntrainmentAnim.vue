<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { createBinauralPair, type BinauralPair } from '@/audio/core'

const carrier = ref(200)
const beat = ref(10)
const playing = ref(false)
const canvasRef = ref<HTMLCanvasElement | null>(null)

const leftFreq = computed(() => carrier.value)
const rightFreq = computed(() => carrier.value + beat.value)

let ctx: AudioContext | null = null
let pair: BinauralPair | null = null
let raf = 0
let t0 = 0

function start() {
  if (playing.value) return
  ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
  const out = ctx.createGain()
  out.gain.value = 0.08
  out.connect(ctx.destination)
  pair = createBinauralPair(ctx, { leftHz: leftFreq.value, rightHz: rightFreq.value })
  pair.output.connect(out)
  pair.start()
  playing.value = true
}

function stop() {
  if (!playing.value) return
  pair?.dispose()
  ctx?.close()
  ctx = null; pair = null
  playing.value = false
}

function toggle() {
  playing.value ? stop() : start()
}

watch([leftFreq, rightFreq], ([l, r]) => {
  pair?.setEars(l, r) // drag each ear independently
})

function draw() {
  const cv = canvasRef.value
  if (!cv) return
  const c = cv.getContext('2d')
  if (!c) return
  const dpr = window.devicePixelRatio || 1
  const w = cv.clientWidth
  const h = cv.clientHeight
  if (cv.width !== w * dpr) {
    cv.width = w * dpr
    cv.height = h * dpr
    c.scale(dpr, dpr)
  }
  c.clearRect(0, 0, w, h)
  const t = (performance.now() - t0) / 1000
  const rowH = h / 3

  drawWave(c, w, rowH * 0, rowH, leftFreq.value, t, '#818cf8', 'L')
  drawWave(c, w, rowH * 1, rowH, rightFreq.value, t, '#34d399', 'R')
  drawBeat(c, w, rowH * 2, rowH, beat.value, t)

  raf = requestAnimationFrame(draw)
}

function drawWave(c: CanvasRenderingContext2D, w: number, y: number, h: number, freq: number, t: number, color: string, label: string) {
  const mid = y + h / 2
  c.fillStyle = '#64748b'
  c.font = '11px system-ui, sans-serif'
  c.textBaseline = 'middle'
  c.fillText(`${label} · ${freq.toFixed(0)} Hz`, 8, y + 12)

  c.beginPath()
  c.strokeStyle = color
  c.lineWidth = 1.4
  // visual frequency is scaled — actual Hz would be too dense to render
  const visFreq = freq / 25
  for (let x = 0; x <= w; x++) {
    const ph = (x / w) * Math.PI * 2 * visFreq + t * Math.PI * 2 * (freq / 200) * 4
    const yPx = mid + Math.sin(ph) * (h * 0.32)
    if (x === 0) c.moveTo(x, yPx)
    else c.lineTo(x, yPx)
  }
  c.stroke()
}

function drawBeat(c: CanvasRenderingContext2D, w: number, y: number, h: number, freq: number, t: number) {
  const mid = y + h / 2
  c.fillStyle = '#a5b4fc'
  c.font = '11px system-ui, sans-serif'
  c.textBaseline = 'middle'
  c.fillText(`perceived beat · ${freq.toFixed(1)} Hz`, 8, y + 12)

  // pulse envelope at beat freq
  c.beginPath()
  c.strokeStyle = '#a5b4fc'
  c.lineWidth = 1.6
  for (let x = 0; x <= w; x++) {
    const ph = (x / w) * Math.PI * 2 * 8 - t * Math.PI * 2 * freq * 0.4
    const env = (Math.sin(ph) + 1) / 2
    const yPx = mid - env * (h * 0.42)
    if (x === 0) c.moveTo(x, yPx)
    else c.lineTo(x, yPx)
  }
  c.stroke()
  c.lineTo(w, mid)
  c.lineTo(0, mid)
  c.closePath()
  c.fillStyle = 'rgba(165, 180, 252, 0.12)'
  c.fill()
}

onMounted(() => {
  t0 = performance.now()
  raf = requestAnimationFrame(draw)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  stop()
})
</script>

<template>
  <figure class="bin">
    <div class="canvas-wrap">
      <canvas ref="canvasRef" class="canvas"></canvas>
    </div>

    <div class="controls">
      <label class="ctrl">
        <span class="ctrl-label">Carrier · {{ carrier }} Hz</span>
        <input type="range" min="100" max="500" step="10" v-model.number="carrier" />
      </label>
      <label class="ctrl">
        <span class="ctrl-label">Beat · {{ beat }} Hz</span>
        <input type="range" min="1" max="15" step="0.5" v-model.number="beat" />
      </label>
      <button
        type="button"
        class="play"
        :class="{ 'play--on': playing }"
        @click="toggle"
        :aria-pressed="playing"
      >
        {{ playing ? '◼ Stop' : '▶ Listen' }}
      </button>
    </div>

    <p class="warn">Headphones required to perceive the beat — without them you hear two close tones, not the third pulse.</p>
  </figure>
</template>

<style scoped>
.bin {
  margin: 0 0 2.5rem;
}

.canvas-wrap {
  background: #141420;
  border: 1px solid #2a2a2a;
  border-radius: 10px;
  overflow: hidden;
}

.canvas {
  display: block;
  width: 100%;
  height: 200px;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-top: 0.875rem;
  align-items: end;
}

.ctrl {
  flex: 1 1 200px;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.ctrl-label {
  font-size: 0.75rem;
  color: #94a3b8;
  letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums;
}

.ctrl input[type="range"] {
  width: 100%;
  accent-color: #6366f1;
  cursor: pointer;
}

.play {
  flex: 0 0 auto;
  background: transparent;
  color: #cbd5e1;
  border: 1px solid #3f3f5a;
  border-radius: 8px;
  padding: 0.55rem 1rem;
  font-size: 0.85rem;
  cursor: pointer;
  font-family: inherit;
  transition: background 180ms ease, color 180ms ease, border-color 180ms ease;
}

.play:hover {
  background: rgba(99, 102, 241, 0.1);
  color: #e2e8f0;
  border-color: #6366f1;
}

.play--on {
  background: #6366f1;
  border-color: #6366f1;
  color: #fff;
}

.play--on:hover {
  background: #4f52d6;
}

.warn {
  margin: 0.75rem 0 0;
  font-size: 0.78rem;
  color: #64748b;
  font-style: italic;
}
</style>
