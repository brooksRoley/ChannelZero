<script setup lang="ts">
import { ref, reactive, computed, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { usePollStore } from '@/composables/usePollStore'
import { useAnalytics, type StreakData } from '@/composables/useAnalytics'
import { useCosmicPhysics } from '@/composables/useCosmicPhysics'
import { useBinauralEngine } from '@/composables/useBinauralEngine'
import { useZenMode } from '@/composables/useZenMode'
import ConnectorPanel from '@/components/ConnectorPanel.vue'
import QuestLog from '@/components/QuestLog.vue'
import HomePoll from '@/components/home/HomePoll.vue'
import MeditationOverlay from '@/components/home/MeditationOverlay.vue'
import NavCardGrid from '@/components/home/NavCardGrid.vue'
import TodaysPractice from '@/components/home/TodaysPractice.vue'

const router = useRouter()
const { token, resetPoll } = usePollStore()

// ── Cosmic physics background ────────────────────────────────────
const bgCanvas = ref<HTMLCanvasElement>()
// Card element ref for physics attractor
const featuredCardEl = ref<HTMLElement>()

const { init: initCosmic, destroy: destroyCosmic, setTiltGravity, setCardAttractors, heatOrb, getOrbPositions } = useCosmicPhysics(bgCanvas, {
  particleCount: 120,
  starCount: 100,
  enableKeyboard: false,
  enableMouseInteract: true,
  clearAlpha: 0.08,
  mouseAttractForce: 0.5,
})

// ── Stage management ─────────────────────────────────────────────
type Stage = 'home' | 'poll'
const stage = ref<Stage>('home')
const showMeditation = ref(false)

const pollRef = ref<InstanceType<typeof HomePoll>>()

function retakePoll() {
  resetPoll()
  if (pollRef.value) {
    pollRef.value.pollStep = 1
    pollRef.value.pollDirection = 'forward'
  }
  stage.value = 'poll'
}

// ── Session data ─────────────────────────────────────────────────
interface SessionOption {
  route: string
  label: string
  description: string
  icon: string
  recommended?: boolean
}

const themeSessions: Record<string, SessionOption[]> = {
  dreamlike: [
    { route: '/webaudio', label: 'Star Tunnel', description: 'Immersive star field with binaural entrainment', icon: '✦', recommended: true },
    { route: '/zeromind', label: 'Zeromind', description: 'Generative visuals with streaming text', icon: '🔮' },
    { route: '/spiral', label: 'Spiral', description: 'Hypnotic spiral with trance words', icon: '🌀' },
    { route: '/trance', label: 'Tone Engine', description: 'Raw binaural tone laboratory', icon: '🎧' },
  ],
  electric: [
    { route: '/zeromind', label: 'Zeromind', description: 'Generative visuals with streaming text', icon: '🔮', recommended: true },
    { route: '/webaudio', label: 'Star Tunnel', description: 'Immersive star field with binaural entrainment', icon: '✦' },
    { route: '/spiral', label: 'Spiral', description: 'Hypnotic spiral with trance words', icon: '🌀' },
    { route: '/trance', label: 'Tone Engine', description: 'Raw binaural tone laboratory', icon: '🎧' },
  ],
  void: [
    { route: '/spiral', label: 'Spiral', description: 'Hypnotic spiral — minimalist and absorbing', icon: '🌀', recommended: true },
    { route: '/trance', label: 'Tone Engine', description: 'Raw binaural tone laboratory', icon: '🎧' },
    { route: '/webaudio', label: 'Star Tunnel', description: 'Immersive star field with binaural entrainment', icon: '✦' },
    { route: '/zeromind', label: 'Zeromind', description: 'Generative visuals with streaming text', icon: '🔮' },
  ],
  organic: [
    { route: '/trance', label: 'Tone Engine', description: 'Binaural tone engine — grounded and tactile', icon: '🎧', recommended: true },
    { route: '/webaudio', label: 'Star Tunnel', description: 'Immersive star field with binaural entrainment', icon: '✦' },
    { route: '/spiral', label: 'Spiral', description: 'Hypnotic spiral with trance words', icon: '🌀' },
    { route: '/zeromind', label: 'Zeromind', description: 'Generative visuals with streaming text', icon: '🔮' },
  ],
  liminal: [
    { route: '/webaudio', label: 'Star Tunnel', description: 'Ambient star drift with entrainment layers', icon: '✦', recommended: true },
    { route: '/zeromind', label: 'Zeromind', description: 'Generative visuals with streaming text', icon: '🔮' },
    { route: '/spiral', label: 'Spiral', description: 'Hypnotic spiral with trance words', icon: '🌀' },
    { route: '/trance', label: 'Tone Engine', description: 'Raw binaural tone laboratory', icon: '🎧' },
  ],
}

const themeLabels: Record<string, string> = {
  dreamlike: 'Dreamlike',
  electric: 'Electric',
  void: 'The Void',
  organic: 'Organic',
  liminal: 'Liminal',
}

const sessions = computed(() => {
  if (!token.value) return []
  return themeSessions[token.value.theme] || themeSessions.liminal
})

const recommendedSession = computed(() => sessions.value.find((s) => s.recommended) || sessions.value[0])
const otherSessions = computed(() => sessions.value.filter((s) => !s.recommended))

// ── Self-expression streak (routine / ritual loop) ───────────────
const { fetchStreak } = useAnalytics()
const streak = ref<StreakData | null>(null)

const streakNudge = computed(() => {
  if (!streak.value || streak.value.streak < 2) return ''
  const n = streak.value.streak
  if (n >= 21) return 'Three weeks of reflection — your portrait has real depth now.'
  if (n >= 14) return 'Two weeks in — your patterns are becoming visible.'
  if (n >= 7)  return 'A full week of practice — your mirror is sharpening.'
  if (n >= 5)  return 'Five sessions deep — the data is starting to cohere.'
  if (n >= 3)  return 'Each return adds a layer to your self-portrait.'
  return 'A second look — the mirror is forming.'
})

// Featured card adapts based on state
const featuredTitle = computed(() =>
  token.value && recommendedSession.value ? recommendedSession.value.label : 'Discover Your Experience'
)
const featuredDesc = computed(() =>
  token.value && recommendedSession.value
    ? recommendedSession.value.description
    : 'A quick introduction to find the right session for your mind'
)

function handleFeaturedClick() {
  if (token.value && recommendedSession.value) {
    router.push(recommendedSession.value.route)
  } else {
    stage.value = 'poll'
  }
}

// (Cosmic physics background replaces old ambient particle drift)

// ── Scene drag tilt ──────────────────────────────────────────────
const sceneTilt = reactive({ x: 0, y: 0 })
let tiltTarget = { x: 0, y: 0 }
let isDragging = false
let lastDragX = 0
let lastDragY = 0
let springId: number | null = null

function runSpring() {
  setTiltGravity(tiltTarget.y * 0.022, tiltTarget.x * 0.016)
  tiltTarget.x *= 0.87
  tiltTarget.y *= 0.87
  sceneTilt.x += (tiltTarget.x - sceneTilt.x) * 0.11
  sceneTilt.y += (tiltTarget.y - sceneTilt.y) * 0.11
  if (Math.abs(sceneTilt.x) > 0.02 || Math.abs(sceneTilt.y) > 0.02) {
    springId = requestAnimationFrame(runSpring)
  } else {
    sceneTilt.x = 0
    sceneTilt.y = 0
    springId = null
  }
}

function startSpring() {
  if (springId) cancelAnimationFrame(springId)
  springId = requestAnimationFrame(runSpring)
}

function onMouseDown(e: MouseEvent) {
  isDragging = true
  lastDragX = e.clientX
  lastDragY = e.clientY
  if (springId) { cancelAnimationFrame(springId); springId = null }
}

function onMouseMove(e: MouseEvent) {
  if (!isDragging) return
  const dx = e.clientX - lastDragX
  const dy = e.clientY - lastDragY
  lastDragX = e.clientX
  lastDragY = e.clientY
  tiltTarget.y = Math.max(-9, Math.min(9, tiltTarget.y + dx * 0.06))
  tiltTarget.x = Math.max(-6, Math.min(6, tiltTarget.x - dy * 0.06))
  sceneTilt.x = tiltTarget.x
  sceneTilt.y = tiltTarget.y
  setTiltGravity(tiltTarget.y * 0.022, tiltTarget.x * 0.016)
}

function onMouseUp() {
  if (!isDragging) return
  isDragging = false
  startSpring()
}

function onTouchStart(e: TouchEvent) {
  const t = e.touches[0]
  lastDragX = t.clientX
  lastDragY = t.clientY
  if (springId) { cancelAnimationFrame(springId); springId = null }
}

function onTouchMove(e: TouchEvent) {
  const t = e.touches[0]
  const dx = t.clientX - lastDragX
  const dy = t.clientY - lastDragY
  lastDragX = t.clientX
  lastDragY = t.clientY
  tiltTarget.y = Math.max(-9, Math.min(9, tiltTarget.y + dx * 0.04))
  tiltTarget.x = Math.max(-6, Math.min(6, tiltTarget.x - dy * 0.04))
  sceneTilt.x = tiltTarget.x
  sceneTilt.y = tiltTarget.y
  setTiltGravity(tiltTarget.y * 0.022, tiltTarget.x * 0.016)
}

function onTouchEnd() {
  startSpring()
}

const sceneStyle = computed(() => ({
  transform: `perspective(1100px) rotateX(${sceneTilt.x}deg) rotateY(${sceneTilt.y}deg)`,
}))

const titleStyle = computed(() => ({
  transform: `translate(${-sceneTilt.y * 3.5}px, ${sceneTilt.x * 2.5}px)`,
}))

// ── Physics integration ──────────────────────────────────────────
// Masses normalized from source file sizes (bytes → 0.4–3.0 range)
// min=useMeditation 6.6KB, max=HomeView 37.6KB
const CARD_MASSES: Record<string, number> = {
  featured:   1.5,  // discovery hub
  checkin:    1.3,  // CheckInView 17.8KB
  journal:    1.2,  // JournalView 16.4KB
  meditation: 0.4,  // useMeditation 6.6KB
  reader:     0.8,  // ReaderView 11.8KB
  audio:      1.7,  // AudioplayerView 21.6KB — heaviest view
  glass:      0.7,  // GlassView 10.4KB
}
const NAV_MASSES: Record<string, number> = {
  '/':               3.0,  // HomeView 37.6KB
  '/reader':         0.8,  // ReaderView 11.8KB
  '/studio':         0.7,  // GlassView 10.4KB
  '/audio':          1.7,  // AudioplayerView 21.6KB
  '/journal':        1.2,  // JournalView 16.4KB
  '/checkin':        1.3,  // CheckInView 17.8KB
  '/calibrate':      0.5,  // OauthView 6.3KB
  '/psychoanalysis': 1.1,  // PsychoanalysisView 15.2KB
}

function updateCardAttractors() {
  const attractors: { x: number; y: number; mass: number }[] = []

  // Featured card
  if (featuredCardEl.value) {
    const r = featuredCardEl.value.getBoundingClientRect()
    attractors.push({ x: r.left + r.width / 2, y: r.top + r.height / 2, mass: CARD_MASSES.featured })
  }

  // Nav grid cards (query from DOM)
  const gridCards = document.querySelectorAll<HTMLElement>('.nav-card')
  const gridKeys = ['checkin', 'journal', 'meditation', 'reader', 'audio', 'glass']
  gridCards.forEach((el, i) => {
    const r = el.getBoundingClientRect()
    attractors.push({ x: r.left + r.width / 2, y: r.top + r.height / 2, mass: CARD_MASSES[gridKeys[i]] || 0.8 })
  })

  // Nav links as additional attractors, sized by their bundle weight
  const navLinks = document.querySelectorAll<HTMLAnchorElement>('.nav-link')
  const linkRects: { rect: DOMRect; mass: number }[] = []
  navLinks.forEach((el) => {
    const href = el.getAttribute('href') ?? '/'
    const mass = NAV_MASSES[href] ?? 0.6
    const rect = el.getBoundingClientRect()
    linkRects.push({ rect, mass })
    attractors.push({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, mass })
  })

  // Gap attractors between adjacent nav links (lighter, proportional to neighbors)
  for (let i = 0; i < linkRects.length - 1; i++) {
    const a = linkRects[i], b = linkRects[i + 1]
    attractors.push({
      x: (a.rect.right + b.rect.left) / 2,
      y: (a.rect.top + a.rect.bottom + b.rect.top + b.rect.bottom) / 4,
      mass: (a.mass + b.mass) * 0.2,
    })
  }

  setCardAttractors(attractors)
}

watch(stage, (val) => {
  if (val === 'home') nextTick(updateCardAttractors)
  else setCardAttractors([])
})

// ── Featured card 3D tilt ─────────────────────────────────────────
const featuredTilt = reactive({ tx: 0, ty: 0, gx: 50, gy: 50, hover: false })

function onFeaturedMove(e: PointerEvent) {
  const el = e.currentTarget as HTMLElement
  const r = el.getBoundingClientRect()
  const nx = ((e.clientX - r.left) / r.width) * 2 - 1
  const ny = ((e.clientY - r.top) / r.height) * 2 - 1
  featuredTilt.tx = ny * -5
  featuredTilt.ty = nx * 5
  featuredTilt.gx = (nx + 1) * 50
  featuredTilt.gy = (ny + 1) * 50
}

function onFeaturedEnter() { featuredTilt.hover = true }

function onFeaturedLeave() {
  featuredTilt.tx = 0; featuredTilt.ty = 0
  featuredTilt.gx = 50; featuredTilt.gy = 50
  featuredTilt.hover = false
}

const featuredStyle = computed(() => ({
  transform: `perspective(600px) rotateX(${featuredTilt.tx}deg) rotateY(${featuredTilt.ty}deg)`,
  '--gx': `${featuredTilt.gx}%`,
  '--gy': `${featuredTilt.gy}%`,
  transition: featuredTilt.hover
    ? 'box-shadow 0.2s ease'
    : 'transform 0.6s cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.2s ease',
}))

// ── Zen mode ─────────────────────────────────────────────────────
const { zenMode, setZen } = useZenMode()
const binaural = useBinauralEngine()
const zenHintVisible = ref(false)

// Beat presets: alpha (10 Hz) for home field — meditative focus
const ZEN_BEAT_HZ = 10
const ZEN_CARRIER_HZ = 220

let zenRaf = 0
let zenBeatTimer = 0
let zenOrbIdx = 0
let zenHintTimer = 0

function enterZen() {
  setZen(true)
  // Browser fullscreen
  const el = document.documentElement
  if (el.requestFullscreen) el.requestFullscreen().catch(() => {})
  else if ((el as any).webkitRequestFullscreen) (el as any).webkitRequestFullscreen()

  // Start binaural at alpha
  binaural.init()
  binaural.setBeat(ZEN_BEAT_HZ, ZEN_CARRIER_HZ)
  binaural.setVolume(18)

  // Clear card attractors — let orbs drift freely
  setCardAttractors([])

  // Show exit hint briefly
  zenHintVisible.value = true
  clearTimeout(zenHintTimer)
  zenHintTimer = window.setTimeout(() => { zenHintVisible.value = false }, 3000)

  // Beat pulse: fire heatOrb at the beat frequency (10 Hz = 100ms interval)
  const intervalMs = 1000 / ZEN_BEAT_HZ
  zenBeatTimer = window.setInterval(() => {
    const waveform = binaural.getWaveformData()
    // Compute amplitude from waveform (0–1)
    let amp = 0
    if (waveform) {
      let sum = 0
      for (let i = 0; i < waveform.length; i++) sum += Math.abs(waveform[i] - 128)
      amp = Math.min(1, (sum / waveform.length) / 64)
    } else {
      amp = 0.4 // fallback if waveform not available
    }
    // Heat orbs in sequence — each beat lights the next
    heatOrb(zenOrbIdx % 6, 0.3 + amp * 0.5)
    zenOrbIdx++
    // Subtle breathing gravity from amplitude
    setTiltGravity(Math.sin(zenOrbIdx * 0.7) * amp * 0.008, Math.cos(zenOrbIdx * 0.5) * amp * 0.006)
  }, intervalMs)
}

function exitZen() {
  setZen(false)
  binaural.destroy()
  clearInterval(zenBeatTimer)
  cancelAnimationFrame(zenRaf)
  setTiltGravity(0, 0)
  setCardAttractors([])
  if (document.fullscreenElement || (document as any).webkitFullscreenElement) {
    if (document.exitFullscreen) document.exitFullscreen().catch(() => {})
    else if ((document as any).webkitExitFullscreen) (document as any).webkitExitFullscreen()
  }
  nextTick(updateCardAttractors)
}

function onZenKeydown(e: KeyboardEvent) {
  if (zenMode.value && e.key === 'Escape') exitZen()
}

function onFullscreenChange() {
  // If user exits fullscreen via browser UI while in zen mode, also exit zen
  if (zenMode.value && !document.fullscreenElement && !(document as any).webkitFullscreenElement) {
    exitZen()
  }
}

function onZenHint() {
  if (!zenMode.value) return
  zenHintVisible.value = true
  clearTimeout(zenHintTimer)
  zenHintTimer = window.setTimeout(() => { zenHintVisible.value = false }, 2000)
}

// ── Lifecycle ────────────────────────────────────────────────────
onMounted(async () => {
  window.addEventListener('mousedown', onMouseDown)
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
  window.addEventListener('touchstart', onTouchStart, { passive: true })
  window.addEventListener('touchmove', onTouchMove, { passive: true })
  window.addEventListener('touchend', onTouchEnd, { passive: true })
  window.addEventListener('resize', updateCardAttractors)
  window.addEventListener('keydown', onZenKeydown)
  window.addEventListener('mousemove', onZenHint)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('webkitfullscreenchange', onFullscreenChange)
  await initCosmic()
  await nextTick()
  updateCardAttractors()
  fetchStreak().then((s) => { streak.value = s })
})

onUnmounted(() => {
  if (springId) cancelAnimationFrame(springId)
  destroyCosmic()
  window.removeEventListener('mousedown', onMouseDown)
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
  window.removeEventListener('touchstart', onTouchStart)
  window.removeEventListener('touchmove', onTouchMove)
  window.removeEventListener('touchend', onTouchEnd)
  window.removeEventListener('resize', updateCardAttractors)
  window.removeEventListener('keydown', onZenKeydown)
  window.removeEventListener('mousemove', onZenHint)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('webkitfullscreenchange', onFullscreenChange)
  if (zenMode.value) exitZen()
})
</script>

<template>
  <div class="home" @dragstart.prevent>
    <canvas ref="bgCanvas" class="home-bg" aria-hidden="true"></canvas>

    <!-- ── Zen mode toggle (top-right corner) ── -->
    <button
      class="zen-btn"
      :class="{ 'zen-btn--active': zenMode }"
      @click="zenMode ? exitZen() : enterZen()"
      :title="zenMode ? 'Exit zen mode (Esc)' : 'Enter zen mode'"
      :aria-label="zenMode ? 'Exit zen mode' : 'Enter zen mode'"
    >{{ zenMode ? '✕' : '◎' }}</button>

    <!-- ── Zen exit hint (fades after 3s) ── -->
    <Transition name="zen-hint-fade">
      <div v-if="zenMode && zenHintVisible" class="zen-hint">
        move mouse to show · esc to exit
      </div>
    </Transition>

    <div class="content-scene" :style="sceneStyle" :class="{ 'content-scene--hidden': zenMode }">
      <h1 class="title" :style="titleStyle">Channel Zero: Dreamer</h1>
      <p class="tagline" :style="titleStyle">community over convenience — know yourself first</p>

      <!-- ── Stage: Home ── -->
      <Transition name="stage" mode="out-in">
        <div v-if="stage === 'home'" key="home" class="stage-content">
          <!-- Profile bar (returning user) -->
          <div v-if="token" class="profile-bar">
            <span class="profile-badge" :style="{ color: token.palette.accent }">
              {{ themeLabels[token.theme] }}
            </span>
            <span class="profile-arch">{{ token.archetype }}</span>
            <div class="profile-swatches">
              <span class="swatch-dot" :style="{ background: token.palette.primary }"></span>
              <span class="swatch-dot" :style="{ background: token.palette.accent }"></span>
            </div>
            <button class="profile-retake" @click="retakePoll">retake</button>
          </div>

          <!-- Quest Log — "you are here" with next action -->
          <QuestLog @start-poll="stage = 'poll'" />

          <!-- Self-expression streak — daily ritual counter -->
          <div v-if="streak && streak.streak > 0" class="streak-chip">
            <span class="streak-flame">🔥</span>
            <span class="streak-count">{{ streak.streak }}</span>
            <span class="streak-label">day{{ streak.streak === 1 ? '' : 's' }} in a row</span>
            <div class="streak-dots" aria-hidden="true">
              <span
                v-for="(d, i) in streak.last_7_days"
                :key="i"
                class="streak-dot"
                :class="{ 'streak-dot--active': d.active }"
              ></span>
            </div>
          </div>

          <!-- Streak nudge — frames returning practice as accumulating self-knowledge -->
          <p v-if="streakNudge" class="streak-nudge">{{ streakNudge }}</p>

          <!-- Today's Practice — three-step daily ritual sequence -->
          <TodaysPractice v-if="token" />

          <!-- Featured card -->
          <div
            class="featured-card"
            ref="featuredCardEl"
            role="button"
            tabindex="0"
            :style="featuredStyle"
            @pointermove="onFeaturedMove"
            @pointerenter="onFeaturedEnter"
            @pointerleave="onFeaturedLeave"
            @click="handleFeaturedClick"
            @keydown.enter="handleFeaturedClick"
            @keydown.space.prevent="handleFeaturedClick"
          >
            <span class="card-icon featured-icon">✦</span>
            <span class="card-title featured-title">{{ featuredTitle }}</span>
            <span class="card-desc">{{ featuredDesc }}</span>
            <span v-if="token && recommendedSession" class="rec-badge">Recommended</span>
            <div class="card-glare"></div>
          </div>

          <!-- Alt sessions (returning user) -->
          <div v-if="token" class="alt-sessions">
            <button
              v-for="s in otherSessions"
              :key="s.route"
              class="alt-session-btn"
              @click="router.push(s.route)"
            >
              <span class="alt-icon">{{ s.icon }}</span>
              {{ s.label }}
            </button>
          </div>

          <!-- Connector status panel -->
          <ConnectorPanel />

          <!-- Utility cards grid -->
          <NavCardGrid
            :get-orb-positions="getOrbPositions"
            :heat-orb="heatOrb"
            @open-meditation="showMeditation = true"
          />
        </div>

        <!-- ── Stage: Poll ── -->
        <div v-else-if="stage === 'poll'" key="poll" class="stage-content">
          <HomePoll ref="pollRef" @done="stage = 'home'" />
        </div>
      </Transition>
    </div>

    <!-- ── Meditation overlay ── -->
    <MeditationOverlay :show="showMeditation" @close="showMeditation = false" />
  </div>
</template>

<style scoped>
/* ── Layout ── */
.home {
  text-align: center;
  user-select: none;
  -webkit-user-select: none;
  position: relative;
  background: #08060e;
  min-height: calc(100vh - 3rem);
  padding-bottom: 2rem;
}

/* ── Zen mode ── */
.content-scene--hidden {
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.8s ease;
}

.zen-btn {
  position: fixed;
  top: 1rem;
  right: 1rem;
  z-index: 100;
  background: none;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 50%;
  width: 2rem;
  height: 2rem;
  color: rgba(148, 163, 184, 0.7);
  font-size: 0.85rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.2s, border-color 0.2s, opacity 0.2s;
  opacity: 0.65;
}
.zen-btn:hover {
  color: rgba(148, 163, 184, 0.9);
  border-color: rgba(255, 255, 255, 0.2);
  opacity: 1;
}
.zen-btn--active {
  color: rgba(192, 132, 252, 0.7);
  border-color: rgba(192, 132, 252, 0.3);
  opacity: 1;
}

.zen-hint {
  position: fixed;
  bottom: 1.5rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  font-family: monospace;
  font-size: 0.6rem;
  letter-spacing: 0.1em;
  color: rgba(71, 85, 105, 0.8);
  pointer-events: none;
}

.zen-hint-fade-enter-active,
.zen-hint-fade-leave-active {
  transition: opacity 0.6s ease;
}
.zen-hint-fade-enter-from,
.zen-hint-fade-leave-to {
  opacity: 0;
}

.home-bg {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
}

.content-scene {
  will-change: transform;
  transform-origin: center center;
  position: relative;
  z-index: 1;
}

.title {
  font-size: 2rem;
  font-weight: bold;
  margin-bottom: 0.25rem;
  color: #e2e8f0;
  margin-top: 2rem;
  will-change: transform;
}

.tagline {
  font-size: 0.72rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(148, 163, 184, 0.55);
  margin: 0 0 0.75rem;
  will-change: transform;
}

.stage-content {
  max-width: 600px;
  margin: 0 auto;
  padding: 0 1rem;
}

/* ── Stage transition ── */
.stage-enter-active,
.stage-leave-active {
  transition: all 0.3s ease;
}
.stage-enter-from {
  opacity: 0;
  transform: translateY(12px);
}
.stage-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* ── Profile bar ── */
.profile-bar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 1rem;
  margin-bottom: 1.25rem;
  background: rgba(30, 30, 50, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0.6rem;
}

.profile-badge {
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.03em;
}

.profile-arch {
  font-size: 0.78rem;
  color: #94a3b8;
}

.profile-swatches {
  display: flex;
  gap: 0.3rem;
  margin-left: auto;
}

.swatch-dot {
  width: 0.75rem;
  height: 0.75rem;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.profile-retake {
  background: none;
  border: none;
  color: #64748b;
  font-size: 0.7rem;
  font-family: inherit;
  cursor: pointer;
  padding: 0.2rem 0.4rem;
  transition: color 0.15s;
}

.profile-retake:hover {
  color: #94a3b8;
}

/* ── Featured card ── */
.featured-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 2.5rem 2rem;
  margin-bottom: 1rem;
  background: linear-gradient(135deg, rgba(30, 20, 60, 0.9), rgba(20, 20, 50, 0.85));
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 1rem;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  will-change: transform;
  text-decoration: none;
  color: #e2e8f0;
}

.featured-card:hover {
  border-color: rgba(167, 139, 250, 0.6);
  box-shadow: 0 12px 48px rgba(99, 102, 241, 0.2);
}

.featured-icon {
  font-size: 2rem;
  color: #a78bfa;
}

.featured-title {
  font-size: 1.3rem;
  font-weight: 600;
  background: linear-gradient(135deg, #c4b5fd, #818cf8);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.rec-badge {
  font-size: 0.6rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #a78bfa;
  font-weight: 600;
}

/* ── Alt session buttons ── */
.alt-sessions {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.25rem;
  justify-content: center;
  flex-wrap: wrap;
}

.alt-session-btn {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.45rem 0.85rem;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 0.5rem;
  color: #94a3b8;
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.alt-session-btn:hover {
  background: rgba(99, 102, 241, 0.12);
  border-color: rgba(99, 102, 241, 0.35);
  color: #e2e8f0;
}

.alt-icon {
  font-size: 0.9rem;
}

/* ── Featured card glare ── */
.featured-card:hover .card-glare {
  opacity: 1;
}

/* ── Self-expression streak chip ── */
.streak-chip {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: fit-content;
  margin: 0 auto 1rem;
  padding: 0.4rem 0.85rem;
  background: rgba(249, 115, 22, 0.08);
  border: 1px solid rgba(249, 115, 22, 0.25);
  border-radius: 2rem;
}

.streak-flame {
  font-size: 0.95rem;
  line-height: 1;
}

.streak-count {
  font-size: 0.95rem;
  font-weight: 700;
  color: #fb923c;
}

.streak-label {
  font-size: 0.72rem;
  color: #94a3b8;
}

.streak-dots {
  display: flex;
  gap: 0.2rem;
  margin-left: 0.35rem;
}

.streak-dot {
  width: 0.4rem;
  height: 0.4rem;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
}

.streak-dot--active {
  background: #fb923c;
}

.streak-nudge {
  font-size: 0.75rem;
  color: #64748b;
  font-style: italic;
  letter-spacing: 0.02em;
  margin: -0.5rem auto 1rem;
  max-width: 22rem;
}

</style>
