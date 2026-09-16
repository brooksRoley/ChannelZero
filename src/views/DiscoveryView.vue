<script setup lang="ts">
import { ref, computed, reactive, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/composables/useAuthStore'
import { usePollStore } from '@/composables/usePollStore'
import { useVibeStore, type VibeMatch } from '@/composables/useVibeStore'
import { useJournalStore } from '@/composables/useJournalStore'
import { useCosmicPhysics, type OrbDef } from '@/composables/useCosmicPhysics'
import { prepare, layout } from '@chenglou/pretext'

const router = useRouter()
const { user, apiFetch, isAuthenticated } = useAuthStore()
const { token: pollToken } = usePollStore()
const { oauthState, markConnected, connectSpotify, fetchMatches, matches, matchesLoading } = useVibeStore()
const { getAllTodayText } = useJournalStore()

if (!isAuthenticated.value) router.replace('/login')

const accent = computed(() => pollToken.value?.palette?.accent || '#a78bfa')

// ── Discovery phases ─────────────────────────────────────────────
// mirror → ingestion → synthesis → resonance
type Phase = 'mirror' | 'ingestion' | 'synthesis' | 'resonance'

const phase = ref<Phase>('mirror')
const transitioning = ref(false)

// ── Physics canvas ───────────────────────────────────────────────
const canvasRef = ref<HTMLCanvasElement>()

// Custom orb palette: 3 orbs representing Self, Data, Others
const discoveryOrbs: OrbDef[] = [
  { r: 167, g: 139, b: 250 },  // violet — Self
  { r: 56,  g: 189, b: 248 },  // cyan — Data
  { r: 251, g: 146, b: 60  },  // amber — Others
]

const cosmic = useCosmicPhysics(canvasRef, {
  orbDefs: discoveryOrbs,
  particleCount: 180,
  starCount: 140,
  enableKeyboard: false,
  enableMouseInteract: true,
  clearAlpha: 0.09,
  mouseAttractForce: 0.6,
})

// ── Mirror phase: journal input ──────────────────────────────────

const journalInput = ref('')
const journalSubmitted = ref(false)
const journalSending = ref(false)
const oracleResponse = ref<string | null>(null)
const analysisResult = ref<{
  attachment_style: string
  defense_mechanism: string
  readiness_score: number
  insight: string
} | null>(null)

// Floating text words for canvas overlay
const floatingWords = reactive<{
  text: string; x: number; y: number; vx: number; vy: number
  alpha: number; size: number; age: number
}[]>([])

let wordEmitTimer = 0

// Use Pretext.js to measure words for canvas positioning
function measureWord(word: string, fontSize: number): number {
  try {
    const handle = prepare(word, `${fontSize}px "Inter", system-ui, sans-serif`)
    const result = layout(handle, 9999, fontSize * 1.2)
    // Approximate width from the handle — Pretext returns height/lineCount
    // Use canvas measureText as fallback for width
    return fontSize * word.length * 0.55
  } catch {
    return fontSize * word.length * 0.55
  }
}

// Emit words from journal input onto the canvas
watch(journalInput, (val, oldVal) => {
  if (!val || val.length <= (oldVal?.length ?? 0)) return
  const words = val.split(/\s+/)
  const lastWord = words[words.length - 1]
  if (lastWord && lastWord.length > 2 && val.endsWith(' ')) {
    const canvas = canvasRef.value
    if (!canvas) return
    const cx = canvas.clientWidth / 2
    const cy = canvas.clientHeight / 2
    const fontSize = 13 + Math.random() * 5
    const angle = Math.random() * Math.PI * 2
    const dist = 120 + Math.random() * 180

    floatingWords.push({
      text: lastWord,
      x: cx + Math.cos(angle) * dist,
      y: cy + Math.sin(angle) * dist,
      vx: (cx - (cx + Math.cos(angle) * dist)) * 0.003,
      vy: (cy - (cy + Math.sin(angle) * dist)) * 0.003,
      alpha: 0.8,
      size: fontSize,
      age: 0,
    })

    // Cap floating words
    if (floatingWords.length > 30) floatingWords.splice(0, 5)
  }
})

// Animate floating words toward center (spiral pull)
function animateFloatingWords() {
  const canvas = canvasRef.value
  if (!canvas) return
  const cx = canvas.clientWidth / 2
  const cy = canvas.clientHeight / 2

  for (let i = floatingWords.length - 1; i >= 0; i--) {
    const w = floatingWords[i]
    const dx = cx - w.x
    const dy = cy - w.y
    const dist = Math.hypot(dx, dy)

    // Spiral: attraction + tangential force
    if (dist > 10) {
      w.vx += (dx / dist) * 0.08
      w.vy += (dy / dist) * 0.08
      // Tangential (spiral)
      w.vx += (-dy / dist) * 0.04
      w.vy += (dx / dist) * 0.04
    }

    w.vx *= 0.96
    w.vy *= 0.96
    w.x += w.vx
    w.y += w.vy
    w.age++

    // Fade when close to center or old
    if (dist < 40 || w.age > 300) {
      w.alpha *= 0.95
    }
    if (w.alpha < 0.02) {
      floatingWords.splice(i, 1)
    }
  }
}

// Draw floating words on canvas overlay
function drawFloatingWords(ctx: CanvasRenderingContext2D) {
  for (const w of floatingWords) {
    ctx.save()
    ctx.font = `${w.size}px "Inter", system-ui, sans-serif`
    ctx.fillStyle = `rgba(167, 139, 250, ${w.alpha * 0.7})`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(w.text, w.x, w.y)
    ctx.restore()
  }
}

// ── Data bloom nodes (ingestion phase) ───────────────────────────

interface DataNode {
  label: string
  category: 'genre' | 'artist' | 'metric' | 'trait'
  x: number; y: number; vx: number; vy: number
  radius: number; alpha: number; born: number
  color: { r: number; g: number; b: number }
}

const dataNodes = reactive<DataNode[]>([])

function bloomDataNodes(labels: string[], category: DataNode['category']) {
  const canvas = canvasRef.value
  if (!canvas) return
  const cx = canvas.clientWidth / 2
  const cy = canvas.clientHeight / 2

  const colors: Record<string, { r: number; g: number; b: number }> = {
    genre:  { r: 56,  g: 189, b: 248 },
    artist: { r: 251, g: 146, b: 60  },
    metric: { r: 34,  g: 197, b: 94  },
    trait:  { r: 167, g: 139, b: 250 },
  }

  for (let i = 0; i < labels.length; i++) {
    const angle = (i / labels.length) * Math.PI * 2 + Math.random() * 0.3
    const dist = 40 + Math.random() * 30

    setTimeout(() => {
      dataNodes.push({
        label: labels[i],
        category,
        x: cx + Math.cos(angle) * dist,
        y: cy + Math.sin(angle) * dist,
        vx: Math.cos(angle) * 1.5,
        vy: Math.sin(angle) * 1.5,
        radius: 4 + Math.random() * 6,
        alpha: 0,
        born: Date.now(),
        color: colors[category],
      })
    }, i * 120)
  }
}

function animateDataNodes() {
  const canvas = canvasRef.value
  if (!canvas) return
  const cx = canvas.clientWidth / 2
  const cy = canvas.clientHeight / 2

  for (let i = dataNodes.length - 1; i >= 0; i--) {
    const n = dataNodes[i]
    const dx = cx - n.x
    const dy = cy - n.y
    const dist = Math.hypot(dx, dy)

    // Orbit: weak pull + tangential
    if (dist > 5) {
      n.vx += (dx / dist) * 0.02
      n.vy += (dy / dist) * 0.02
      n.vx += (-dy / dist) * 0.06
      n.vy += (dx / dist) * 0.06
    }

    n.vx *= 0.985
    n.vy *= 0.985
    n.x += n.vx
    n.y += n.vy

    // Fade in
    if (n.alpha < 0.85) n.alpha = Math.min(0.85, n.alpha + 0.02)
  }
}

function drawDataNodes(ctx: CanvasRenderingContext2D) {
  for (const n of dataNodes) {
    const { r, g, b } = n.color
    // Glow
    const grad = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.radius * 3)
    grad.addColorStop(0, `rgba(${r},${g},${b},${n.alpha * 0.3})`)
    grad.addColorStop(1, `rgba(${r},${g},${b},0)`)
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.arc(n.x, n.y, n.radius * 3, 0, Math.PI * 2)
    ctx.fill()

    // Core
    ctx.fillStyle = `rgba(${r},${g},${b},${n.alpha})`
    ctx.beginPath()
    ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2)
    ctx.fill()

    // Label
    ctx.save()
    ctx.font = '10px "Inter", system-ui, sans-serif'
    ctx.fillStyle = `rgba(${r},${g},${b},${n.alpha * 0.8})`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillText(n.label, n.x, n.y + n.radius + 4)
    ctx.restore()
  }
}

// ── Match nodes (resonance phase) ────────────────────────────────

interface MatchNode {
  match: VibeMatch
  x: number; y: number; vx: number; vy: number
  radius: number; alpha: number
  color: { r: number; g: number; b: number }
}

const matchNodes = reactive<MatchNode[]>([])

function spawnMatchNodes() {
  const canvas = canvasRef.value
  if (!canvas) return
  const W = canvas.clientWidth
  const H = canvas.clientHeight

  const matchColors = [
    { r: 251, g: 146, b: 60  },
    { r: 244, g: 114, b: 182 },
    { r: 34,  g: 197, b: 94  },
  ]

  matches.value.forEach((m, i) => {
    // Spawn from screen edge
    const edge = Math.random()
    let sx: number, sy: number
    if (edge < 0.25)      { sx = -40;    sy = Math.random() * H }
    else if (edge < 0.5)  { sx = W + 40; sy = Math.random() * H }
    else if (edge < 0.75) { sx = Math.random() * W; sy = -40 }
    else                   { sx = Math.random() * W; sy = H + 40 }

    setTimeout(() => {
      matchNodes.push({
        match: m,
        x: sx, y: sy,
        vx: (W / 2 - sx) * 0.008,
        vy: (H / 2 - sy) * 0.008,
        radius: 20 + m.similarity * 15,
        alpha: 0,
        color: matchColors[i % matchColors.length],
      })
    }, i * 800)
  })
}

function animateMatchNodes() {
  const canvas = canvasRef.value
  if (!canvas) return
  const cx = canvas.clientWidth / 2
  const cy = canvas.clientHeight / 2

  for (const mn of matchNodes) {
    const dx = cx - mn.x
    const dy = cy - mn.y
    const dist = Math.hypot(dx, dy)

    // Drift toward center-ish but orbit
    const targetDist = 120 + matchNodes.indexOf(mn) * 60
    if (dist > targetDist + 20) {
      mn.vx += (dx / dist) * 0.15
      mn.vy += (dy / dist) * 0.15
    } else if (dist < targetDist - 20) {
      mn.vx -= (dx / dist) * 0.05
      mn.vy -= (dy / dist) * 0.05
    }
    // Tangential orbit
    mn.vx += (-dy / Math.max(dist, 1)) * 0.08
    mn.vy += (dx / Math.max(dist, 1)) * 0.08

    mn.vx *= 0.97
    mn.vy *= 0.97
    mn.x += mn.vx
    mn.y += mn.vy

    if (mn.alpha < 0.9) mn.alpha = Math.min(0.9, mn.alpha + 0.015)
  }
}

function drawMatchNodes(ctx: CanvasRenderingContext2D) {
  const canvas = canvasRef.value
  if (!canvas) return
  const cx = canvas.clientWidth / 2
  const cy = canvas.clientHeight / 2

  for (const mn of matchNodes) {
    const { r, g, b } = mn.color

    // Connection line to center (vector overlap visualization)
    ctx.beginPath()
    ctx.moveTo(cx, cy)
    ctx.lineTo(mn.x, mn.y)
    ctx.strokeStyle = `rgba(${r},${g},${b},${mn.alpha * 0.12})`
    ctx.lineWidth = 1
    ctx.setLineDash([4, 6])
    ctx.stroke()
    ctx.setLineDash([])

    // Outer glow
    const grad = ctx.createRadialGradient(mn.x, mn.y, 0, mn.x, mn.y, mn.radius * 2.5)
    grad.addColorStop(0, `rgba(${r},${g},${b},${mn.alpha * 0.15})`)
    grad.addColorStop(1, `rgba(${r},${g},${b},0)`)
    ctx.fillStyle = grad
    ctx.beginPath()
    ctx.arc(mn.x, mn.y, mn.radius * 2.5, 0, Math.PI * 2)
    ctx.fill()

    // Core orb
    const cg = ctx.createRadialGradient(mn.x, mn.y, 0, mn.x, mn.y, mn.radius)
    cg.addColorStop(0, `rgba(${Math.min(255, r + 40)},${Math.min(255, g + 40)},${Math.min(255, b + 40)},${mn.alpha * 0.6})`)
    cg.addColorStop(1, `rgba(${r},${g},${b},${mn.alpha * 0.15})`)
    ctx.fillStyle = cg
    ctx.beginPath()
    ctx.arc(mn.x, mn.y, mn.radius, 0, Math.PI * 2)
    ctx.fill()

    // Name label
    ctx.save()
    ctx.font = 'bold 11px "Inter", system-ui, sans-serif'
    ctx.fillStyle = `rgba(${r},${g},${b},${mn.alpha})`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillText(mn.match.display_name, mn.x, mn.y + mn.radius + 6)

    // Similarity score
    ctx.font = '9px "Inter", system-ui, sans-serif'
    ctx.fillStyle = `rgba(255,255,255,${mn.alpha * 0.5})`
    ctx.fillText(`${Math.round(mn.match.similarity * 100)}%`, mn.x, mn.y + mn.radius + 20)
    ctx.restore()
  }
}

// ── Custom overlay render loop ───────────────────────────────────
// Hooks into the canvas after cosmic physics renders each frame

let overlayRaf = 0

function overlayLoop() {
  const canvas = canvasRef.value
  if (!canvas) { overlayRaf = requestAnimationFrame(overlayLoop); return }
  const ctx = canvas.getContext('2d')
  if (!ctx) { overlayRaf = requestAnimationFrame(overlayLoop); return }

  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  ctx.save()
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  // Animate + draw based on phase
  if (phase.value === 'mirror' || phase.value === 'ingestion') {
    animateFloatingWords()
    drawFloatingWords(ctx)
  }
  if (phase.value === 'ingestion' || phase.value === 'synthesis') {
    animateDataNodes()
    drawDataNodes(ctx)
  }
  if (phase.value === 'resonance') {
    animateMatchNodes()
    drawMatchNodes(ctx)
    animateDataNodes()
    drawDataNodes(ctx)
  }

  ctx.restore()
  overlayRaf = requestAnimationFrame(overlayLoop)
}

// ── Phase transitions ────────────────────────────────────────────

async function submitJournal() {
  if (!journalInput.value.trim() || journalSending.value) return
  journalSending.value = true

  try {
    const result = await apiFetch<{
      attachment_style: string
      defense_mechanism: string
      readiness_score: number
      insight: string
    }>('/api/intake/confess', {
      method: 'POST',
      body: JSON.stringify({
        confessions: [journalInput.value.trim()],
        journal_context: getAllTodayText() || null,
        poll_theme: pollToken.value?.theme || null,
      }),
    })
    analysisResult.value = result
    oracleResponse.value = result.insight
  } catch {
    // Local fallback
    oracleResponse.value = 'Your signal has been processed. The vectors are forming.'
  }

  journalSubmitted.value = true
  journalSending.value = false

  // Brief pause, then advance
  await delay(2000)
  transitionTo('ingestion')
}

function transitionTo(next: Phase) {
  transitioning.value = true
  setTimeout(() => {
    phase.value = next
    transitioning.value = false

    if (next === 'resonance') {
      fetchMatches().then(() => {
        if (matches.value.length > 0) {
          spawnMatchNodes()
        }
      })
    }
  }, 600)
}

function onOAuthConnect(provider: string) {
  // Bloom some placeholder data nodes when connecting
  if (provider === 'spotify') {
    connectSpotify()
  }
  // Simulate data bloom after connection
  setTimeout(() => {
    if (provider === 'spotify') {
      bloomDataNodes(['indie', 'electronic', 'ambient', 'post-rock', 'shoegaze'], 'genre')
      setTimeout(() => bloomDataNodes(['valence: 0.42', 'energy: 0.67', 'tempo: 118'], 'metric'), 800)
    }
    markConnected(provider as any)
  }, 500)
}

function advanceFromIngestion() {
  if (analysisResult.value) {
    // Show synthesis briefly, then move to resonance
    transitionTo('synthesis')
    setTimeout(() => transitionTo('resonance'), 4000)
  } else {
    transitionTo('synthesis')
  }
}

function enterGame() {
  router.push('/journal')
}

function delay(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

// ── Lifecycle ────────────────────────────────────────────────────

onMounted(async () => {
  await cosmic.init()
  overlayRaf = requestAnimationFrame(overlayLoop)
})

onUnmounted(() => {
  cosmic.destroy()
  if (overlayRaf) cancelAnimationFrame(overlayRaf)
})
</script>

<template>
  <div class="discovery">
    <!-- Full-screen physics canvas -->
    <canvas ref="canvasRef" class="discovery-canvas" aria-hidden="true" />

    <!-- UI overlay -->
    <div :class="['discovery-ui', { 'discovery-ui--fade': transitioning }]">

      <!-- Phase: Mirror (journal input) -->
      <div v-if="phase === 'mirror'" class="panel mirror-panel">
        <p class="mirror-prompt">What are you carrying today?</p>

        <div v-if="!journalSubmitted" class="mirror-input-wrap">
          <textarea
            v-model="journalInput"
            class="mirror-input"
            rows="4"
            placeholder="The weight of the unspoken..."
            :disabled="journalSending"
            @keydown.meta.enter="submitJournal"
            @keydown.ctrl.enter="submitJournal"
          />
          <button
            class="mirror-submit"
            :style="{ background: accent }"
            :disabled="!journalInput.trim() || journalSending"
            @click="submitJournal"
          >
            {{ journalSending ? 'Processing...' : 'Release' }}
          </button>
          <p class="mirror-hint">Your words become vectors. Type freely.</p>
        </div>

        <div v-else class="mirror-result">
          <div class="oracle-insight">
            <span class="insight-label">Oracle</span>
            <p class="insight-text">{{ oracleResponse }}</p>
          </div>
        </div>
      </div>

      <!-- Phase: Ingestion (OAuth connections) -->
      <div v-if="phase === 'ingestion'" class="panel ingestion-panel">
        <p class="phase-title">The Ingestion</p>
        <p class="phase-desc">Connect your data. Watch it bloom.</p>

        <div class="oauth-nodes">
          <button
            v-for="provider in ['spotify', 'twitter', 'google', 'strava'] as const"
            :key="provider"
            :class="['oauth-node', { 'oauth-node--connected': oauthState[provider]?.connected }]"
            @click="onOAuthConnect(provider)"
          >
            <span class="node-name">{{ provider }}</span>
            <span v-if="oauthState[provider]?.connected" class="node-status">synced</span>
          </button>
        </div>

        <!-- Analysis slot: LLM reactionary CTA -->
        <div v-if="analysisResult" class="analysis-slot">
          <p class="slot-insight">
            I sense a heavy focus on <strong>{{ analysisResult.attachment_style }}</strong>.
            Your defense mechanism: <strong>{{ analysisResult.defense_mechanism }}</strong>.
            <span v-if="!oauthState.spotify?.connected">Shall we see how Spotify reflects this?</span>
          </p>
        </div>

        <button class="advance-btn" :style="{ borderColor: accent }" @click="advanceFromIngestion">
          Proceed to Resonance
        </button>
      </div>

      <!-- Phase: Synthesis (brief oracle moment) -->
      <div v-if="phase === 'synthesis'" class="panel synthesis-panel">
        <div class="synthesis-glow" :style="{ background: accent }" />
        <p class="synthesis-text">
          Synthesizing your psychological coordinates...<br />
          The vectors are converging.
        </p>
        <div v-if="analysisResult" class="synthesis-metrics">
          <div class="metric">
            <span class="metric-label">Attachment</span>
            <span class="metric-value" :style="{ color: accent }">{{ analysisResult.attachment_style }}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Defense</span>
            <span class="metric-value">{{ analysisResult.defense_mechanism }}</span>
          </div>
          <div class="metric">
            <span class="metric-label">Readiness</span>
            <span class="metric-value">{{ analysisResult.readiness_score }}/100</span>
          </div>
        </div>
      </div>

      <!-- Phase: Resonance (match reveal) -->
      <div v-if="phase === 'resonance'" class="panel resonance-panel">
        <p class="phase-title">Resonance</p>
        <p class="phase-desc" v-if="matchesLoading">Searching 1,536-dimensional space...</p>
        <p class="phase-desc" v-else-if="matches.length === 0">No resonant frequencies found yet. Complete more calibration.</p>

        <div v-if="matches.length > 0" class="resonance-cards">
          <div
            v-for="(m, i) in matches"
            :key="m.user_id"
            class="resonance-card"
          >
            <div class="res-header">
              <span class="res-name">{{ m.display_name }}</span>
              <span class="res-score" :style="{ color: accent }">{{ Math.round(m.similarity * 100) }}%</span>
            </div>
            <p class="res-reason">{{ m.match_reason }}</p>
            <p v-if="m.they_accepted" class="res-signal">They already accepted you</p>
          </div>
        </div>

        <button
          v-if="matches.length > 0"
          class="enter-btn"
          :style="{ background: accent }"
          @click="enterGame"
        >
          Your frequencies overlap. Begin your practice.
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.discovery {
  position: fixed;
  inset: 0;
  overflow: hidden;
  background: #08060e;
}

.discovery-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

/* ── UI overlay ── */
.discovery-ui {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 2rem;
  transition: opacity 0.6s ease;
}

.discovery-ui--fade { opacity: 0; }

.panel {
  max-width: 520px;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.25rem;
  text-align: center;
}

/* ── Mirror ── */
.mirror-prompt {
  font-size: 1.6rem;
  font-weight: 300;
  color: rgba(232, 228, 240, 0.85);
  letter-spacing: 0.02em;
  margin: 0;
}

.mirror-input-wrap {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.mirror-input {
  width: 100%;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 0.75rem;
  padding: 1rem;
  font-family: "Inter", system-ui, sans-serif;
  font-size: 0.95rem;
  color: #e2e8f0;
  outline: none;
  resize: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
  backdrop-filter: blur(12px);
}

.mirror-input:focus { border-color: rgba(167, 139, 250, 0.4); }
.mirror-input::placeholder { color: rgba(100, 116, 139, 0.6); }
.mirror-input:disabled { opacity: 0.5; }

.mirror-submit {
  padding: 0.65rem 1.5rem;
  border: none;
  border-radius: 0.5rem;
  color: #0f0f1a;
  font-size: 0.88rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
  align-self: center;
}
.mirror-submit:hover { opacity: 0.9; transform: translateY(-1px); }
.mirror-submit:disabled { opacity: 0.4; cursor: not-allowed; }

.mirror-hint {
  font-size: 0.7rem;
  color: rgba(100, 116, 139, 0.5);
  margin: 0;
}

.mirror-result {
  width: 100%;
}

.oracle-insight {
  background: rgba(10, 10, 25, 0.7);
  border: 1px solid rgba(167, 139, 250, 0.15);
  border-radius: 0.75rem;
  padding: 1.25rem;
  backdrop-filter: blur(12px);
}

.insight-label {
  font-size: 0.6rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: rgba(167, 139, 250, 0.7);
  font-weight: 600;
}

.insight-text {
  font-size: 0.88rem;
  color: #c4b5fd;
  line-height: 1.65;
  margin: 0.4rem 0 0;
}

/* ── Ingestion ── */
.phase-title {
  font-size: 1.3rem;
  font-weight: 600;
  color: #e2e8f0;
  margin: 0;
  letter-spacing: 0.02em;
}

.phase-desc {
  font-size: 0.82rem;
  color: #64748b;
  margin: 0;
}

.oauth-nodes {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  justify-content: center;
}

.oauth-node {
  padding: 0.5rem 1rem;
  border-radius: 2rem;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #94a3b8;
  font-size: 0.8rem;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  text-transform: capitalize;
}

.oauth-node:hover {
  border-color: rgba(56, 189, 248, 0.4);
  background: rgba(56, 189, 248, 0.06);
  color: #e2e8f0;
}

.oauth-node--connected {
  border-color: rgba(34, 197, 94, 0.4);
  background: rgba(34, 197, 94, 0.06);
}

.node-status {
  font-size: 0.6rem;
  color: #22c55e;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.analysis-slot {
  background: rgba(10, 10, 25, 0.7);
  border: 1px solid rgba(167, 139, 250, 0.1);
  border-radius: 0.6rem;
  padding: 1rem;
  backdrop-filter: blur(12px);
}

.slot-insight {
  font-size: 0.82rem;
  color: #94a3b8;
  line-height: 1.6;
  margin: 0;
}

.slot-insight strong {
  color: #c4b5fd;
  text-transform: capitalize;
}

.advance-btn {
  padding: 0.6rem 1.5rem;
  border-radius: 0.5rem;
  background: transparent;
  border: 1px solid;
  color: #e2e8f0;
  font-size: 0.85rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s;
  margin-top: 0.5rem;
}

.advance-btn:hover { background: rgba(255, 255, 255, 0.04); }

/* ── Synthesis ── */
.synthesis-panel { position: relative; }

.synthesis-glow {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 250px;
  height: 250px;
  border-radius: 50%;
  opacity: 0.05;
  filter: blur(60px);
  pointer-events: none;
  animation: pulse-glow 3s ease-in-out infinite;
}

@keyframes pulse-glow {
  0%, 100% { opacity: 0.04; transform: translate(-50%, -50%) scale(1); }
  50% { opacity: 0.08; transform: translate(-50%, -50%) scale(1.15); }
}

.synthesis-text {
  font-size: 0.95rem;
  color: #94a3b8;
  line-height: 1.7;
  margin: 0;
  font-style: italic;
}

.synthesis-metrics {
  display: flex;
  gap: 1.5rem;
  margin-top: 0.5rem;
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.metric-label {
  font-size: 0.55rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #475569;
}

.metric-value {
  font-size: 0.88rem;
  color: #cbd5e1;
  text-transform: capitalize;
}

/* ── Resonance ── */
.resonance-cards {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: 100%;
}

.resonance-card {
  background: rgba(10, 10, 25, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0.6rem;
  padding: 1rem;
  backdrop-filter: blur(12px);
  text-align: left;
  transition: border-color 0.2s;
}

.resonance-card:hover {
  border-color: rgba(167, 139, 250, 0.2);
}

.res-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.3rem;
}

.res-name {
  font-size: 0.95rem;
  font-weight: 600;
  color: #e2e8f0;
}

.res-score {
  font-size: 0.85rem;
  font-weight: 700;
}

.res-reason {
  font-size: 0.78rem;
  color: #64748b;
  line-height: 1.5;
  margin: 0;
}

.res-signal {
  font-size: 0.65rem;
  color: #22c55e;
  margin: 0.3rem 0 0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.enter-btn {
  padding: 0.75rem 2rem;
  border: none;
  border-radius: 0.5rem;
  color: #0f0f1a;
  font-size: 0.92rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
  margin-top: 0.5rem;
}

.enter-btn:hover { opacity: 0.9; transform: translateY(-1px); }

/* ── Mobile ── */
@media (max-width: 480px) {
  .discovery-ui { padding: 1.5rem 1rem; }
  .mirror-prompt { font-size: 1.3rem; }
  .synthesis-metrics { flex-direction: column; gap: 0.75rem; align-items: center; }
}
</style>
