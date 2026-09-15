<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { RouterLink, useRouter, useRoute } from 'vue-router'
import { useStoryStore } from '@/composables/useStoryStore'
import { useTranceEngine } from '@/composables/useTranceEngine'
import { useAuthStore } from '@/composables/useAuthStore'
import { usePollStore } from '@/composables/usePollStore'

const router = useRouter()
const route = useRoute()
const {
  storyText,
  words,
  currentIndex,
  isPlaying,
  setStoryText,
  play,
  pause,
  reset,
  backgroundMedia,
  isBackgroundVideo,
  setBackgroundMedia,
  clearBackgroundMedia
} = useStoryStore()

const {
  sessionActive: tranceSessionActive,
  phase: trancePhase,
  coherenceScore: tranceCoherence,
  phaseAccent: tranceAccent,
  phaseDisplayName,
  activeLayerCount,
  totalLayers,
  startSession: tranceStart,
  stopSession: tranceStop,
  windDown: tranceWindDown,
  // Layer toggles
  baselineModulatorActive,
  ptosisInducerActive,
  avSyncActive,
  alphaWaveActive,
  thetaDreamActive,
  schumannActive,
  solfeggioActive,
  toggleBaselineModulator,
  togglePtosisInducer,
  toggleAVSync,
  toggleAlphaWave,
  toggleThetaDream,
  toggleSchumann,
  toggleSolfeggio,
} = useTranceEngine()

// Tone layer definitions for the panel UI
const toneLayers = computed(() => [
  {
    key: 'alpha', name: 'Alpha Flow', desc: '10 Hz · binaural',
    active: alphaWaveActive.value, toggle: toggleAlphaWave,
    tooltip: '195 Hz left / 205 Hz right → 10 Hz perceived beat.\nAlpha entrainment for relaxed focus and flow state.\nUse at session start or during coherence phase.\n⚠ Requires headphones.',
  },
  {
    key: 'theta', name: 'Deep Theta', desc: '6 Hz · binaural',
    active: thetaDreamActive.value, toggle: toggleThetaDream,
    tooltip: '177 Hz left / 183 Hz right → 6 Hz perceived beat.\nTheta band deepens meditation and invites hypnagogic imagery.\nBest activated during descent phase.\n⚠ Requires headphones.',
  },
  {
    key: 'schumann', name: 'Earth Tone', desc: '7.83 Hz · binaural',
    active: schumannActive.value, toggle: toggleSchumann,
    tooltip: '246 Hz left / 254 Hz right → 7.83 Hz perceived beat.\nEarth\'s Schumann resonance — grounding and coherence.\nLayer lightly under a dominant binaural beat.\n⚠ Requires headphones.',
  },
  {
    key: 'baseline', name: 'Nerve Pulse', desc: '2.4 Hz · isochronic',
    active: baselineModulatorActive.value, toggle: toggleBaselineModulator,
    tooltip: '432 Hz carrier · 2.4 Hz amplitude modulation.\nIsochronic delta pulse — no headphones required.\nPairs with Pulse Sync for audiovisual reinforcement.\nSlower than theta; most effective in deep descent.',
  },
  {
    key: 'ptosis', name: 'Drift', desc: '0.5 Hz · noise sweep',
    active: ptosisInducerActive.value, toggle: togglePtosisInducer,
    tooltip: 'Pink noise through a swept lowpass filter.\nCutoff oscillates 100–800 Hz at 0.5 Hz, slowly drifting\nto 0.42 Hz over 5 min to prevent neural adaptation.\nSupports eyelid heaviness and bodily surrender.',
  },
  {
    key: 'av', name: 'Pulse Sync', desc: '2.4 Hz · AV lock',
    active: avSyncActive.value, toggle: toggleAVSync,
    tooltip: '144 BPM synth pulse (2.4 beat/s).\nAudiovisual isochronic entrainment — aligns with\nNerve Pulse frequency for reinforced delta rhythm.\nVisual flash fires in lockstep with the audio pulse.',
  },
  {
    key: 'solfeg', name: 'Restore', desc: '528 Hz · solfeggio',
    active: solfeggioActive.value, toggle: toggleSolfeggio,
    tooltip: '528 Hz pure sine with 1 Hz tremolo.\nSolfeggio "miracle tone" associated with restoration\nand cellular coherence. Gentle, always-on presence —\nsafe to layer under any other module.',
  },
])

const canWindDown = computed(() =>
  tranceSessionActive.value && (trancePhase.value === 'deepen' || trancePhase.value === 'joy')
)

const { isAuthenticated, user, logout } = useAuthStore()
const { token: pollToken } = usePollStore()

// ── Pipeline progress ─────────────────────────────────────────────
const ONBOARDING_KEY = 'channelzero-onboarding'

interface OnboardingState {
  poll: boolean
  calibrate: boolean
  psychoanalysis: boolean
  intake: boolean
  completed: boolean
}

function loadOnboarding(): OnboardingState {
  try {
    const raw = localStorage.getItem(ONBOARDING_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return { poll: false, calibrate: false, psychoanalysis: false, intake: false, completed: false }
}

const onboarding = ref<OnboardingState>(loadOnboarding())

// Keep in sync with poll completion detected from store
watch(pollToken, (t) => {
  if (t && !onboarding.value.poll) {
    onboarding.value.poll = true
    const s = loadOnboarding()
    s.poll = true
    localStorage.setItem(ONBOARDING_KEY, JSON.stringify(s))
  }
}, { immediate: true })

const pipelineSteps = computed(() => [
  { key: 'poll',           label: 'Profile',  route: '/',              done: onboarding.value.poll },
  { key: 'calibrate',      label: 'Signal',   route: '/calibrate',     done: onboarding.value.calibrate },
  { key: 'psychoanalysis', label: 'Analysis', route: '/psychoanalysis', done: onboarding.value.psychoanalysis },
  { key: 'intake',         label: 'Confess',  route: '/intake',        done: onboarding.value.intake },
])

const pipelineDone = computed(() => pipelineSteps.value.filter(s => s.done).length)
const pipelineComplete = computed(() => onboarding.value.completed)

function handleLogout() {
  logout()
  menuOpen.value = false
  router.push('/')
}

// Panel toggle
const menuOpen = ref(false)

// Fullbleed detection — auto-minimize on immersive routes
const isFullBleed = computed(() => {
  return ['reader', 'zeromind', 'studio', 'spiral', 'trance', 'webaudio', 'hypno', 'audio', 'liquidglass'].includes(
    route.name as string
  )
})

// Auto-hide navbar on fullbleed routes; show on mouse/touch activity
const navVisible = ref(true)
const isFullscreen = ref(false)
let hideNavTimer: ReturnType<typeof setTimeout> | null = null

function showNav() {
  if (!navVisible.value) navVisible.value = true
  if (!isFullBleed.value) return
  if (hideNavTimer) clearTimeout(hideNavTimer)
  if (menuOpen.value) return
  hideNavTimer = setTimeout(() => {
    navVisible.value = false
  }, 3000)
}

function toggleFullscreen() {
  const el = document.documentElement
  if (!document.fullscreenElement && !(document as any).webkitFullscreenElement) {
    if (el.requestFullscreen) el.requestFullscreen()
    else if ((el as any).webkitRequestFullscreen) (el as any).webkitRequestFullscreen()
  } else {
    if (document.exitFullscreen) document.exitFullscreen()
    else if ((document as any).webkitExitFullscreen) (document as any).webkitExitFullscreen()
  }
}

function handleFullscreenChange() {
  isFullscreen.value = !!(document.fullscreenElement || (document as any).webkitFullscreenElement)
}

// Close panel on route change
watch(
  () => route.path,
  () => {
    menuOpen.value = false
  }
)

// Start/stop auto-hide when entering/leaving fullbleed routes
watch(
  isFullBleed,
  (val) => {
    if (val) {
      showNav()
    } else {
      navVisible.value = true
      if (hideNavTimer) {
        clearTimeout(hideNavTimer)
        hideNavTimer = null
      }
    }
  },
  { immediate: true }
)

// While menu is open, keep nav visible; restart timer when closed
watch(menuOpen, (val) => {
  if (!isFullBleed.value) return
  if (val) {
    if (hideNavTimer) {
      clearTimeout(hideNavTimer)
      hideNavTimer = null
    }
    navVisible.value = true
  } else {
    showNav()
  }
})

// Text edit modal state
const showTextModal = ref(false)
const textInputValue = ref('')
const fileName = ref('')

// Background modal state
const showBgModal = ref(false)

// Primary nav links
const primaryLinks = [
  { name: 'home', path: '/', label: 'Home' },
  { name: 'learn', path: '/learn', label: 'Learn' },
  { name: 'sessions', path: '/sessions', label: 'Sessions' },
  { name: 'about', path: '/about', label: 'About' },
]

function togglePlayback() {
  if (isPlaying.value) {
    pause()
  } else {
    play()
  }
}

function openTextModal() {
  textInputValue.value = storyText.value
  fileName.value = ''
  showTextModal.value = true
  menuOpen.value = false
}

function handleFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  fileName.value = file.name
  const reader = new FileReader()
  reader.onload = (e) => {
    textInputValue.value = e.target?.result as string
  }
  reader.readAsText(file)
}

function handleBgUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  const url = URL.createObjectURL(file)
  setBackgroundMedia(url, file.type.startsWith('video/'))
  showBgModal.value = false
}

function loadText() {
  if (!textInputValue.value.trim()) return
  setStoryText(textInputValue.value)
  showTextModal.value = false
  play()
}

function openBgModal() {
  showBgModal.value = true
  menuOpen.value = false
}

// Close panel on outside click
function handleOutsideClick(e: MouseEvent) {
  if (!menuOpen.value) return
  const nav = document.querySelector('.navbar')
  if (nav && !nav.contains(e.target as Node)) {
    menuOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
  window.addEventListener('mousemove', showNav)
  window.addEventListener('touchstart', showNav, { passive: true })
  document.addEventListener('fullscreenchange', handleFullscreenChange)
  document.addEventListener('webkitfullscreenchange', handleFullscreenChange)
})

onUnmounted(() => {
  document.removeEventListener('click', handleOutsideClick)
  window.removeEventListener('mousemove', showNav)
  window.removeEventListener('touchstart', showNav)
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
  document.removeEventListener('webkitfullscreenchange', handleFullscreenChange)
  if (hideNavTimer) clearTimeout(hideNavTimer)
})
</script>

<template>
  <nav
    :class="[
      'navbar',
      {
        'navbar--floating': isFullBleed,
        'navbar--open': menuOpen,
        'navbar--hidden': isFullBleed && !navVisible
      }
    ]"
  >
    <div class="navbar-top">
      <div v-if="!isFullBleed || menuOpen" class="nav-links">
        <RouterLink
          v-for="link in primaryLinks"
          :key="link.name"
          :to="link.path"
          class="nav-link"
          active-class="nav-link--active"
          :exact-active-class="link.path === '/' ? 'nav-link--active' : ''"
        >
          {{ link.label }}
        </RouterLink>
      </div>

      <button
        v-if="isFullBleed"
        :class="['fullscreen-btn', { 'fullscreen-btn--floating': !menuOpen }]"
        @click="toggleFullscreen"
        :aria-label="isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'"
      >
        <svg
          v-if="!isFullscreen"
          xmlns="http://www.w3.org/2000/svg"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="15 3 21 3 21 9"></polyline>
          <polyline points="9 21 3 21 3 15"></polyline>
          <line x1="21" y1="3" x2="14" y2="10"></line>
          <line x1="3" y1="21" x2="10" y2="14"></line>
        </svg>
        <svg
          v-else
          xmlns="http://www.w3.org/2000/svg"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="4 14 10 14 10 20"></polyline>
          <polyline points="20 10 14 10 14 4"></polyline>
          <line x1="10" y1="14" x2="3" y2="21"></line>
          <line x1="21" y1="3" x2="14" y2="10"></line>
        </svg>
      </button>

      <!-- Auth button -->
      <RouterLink
        v-if="!isAuthenticated"
        to="/login"
        class="auth-btn"
        aria-label="Login"
        @click="menuOpen = false"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4M10 17l5-5-5-5M15 12H3"/>
        </svg>
      </RouterLink>
      <button
        v-else
        class="auth-btn auth-btn--user"
        @click="handleLogout"
        :title="`Logout ${user?.display_name || user?.email || ''}`"
        aria-label="Logout"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>
        </svg>
      </button>

      <button
        :class="['menu-btn', { 'menu-btn--floating': isFullBleed && !menuOpen }]"
        @click="menuOpen = !menuOpen"
        aria-label="Toggle controls"
        :aria-expanded="menuOpen ? 'true' : 'false'"
      >
        <span class="hamburger-lines" :class="{ 'hamburger-lines--open': menuOpen }">
          <span class="hamburger-line"></span>
          <span class="hamburger-line"></span>
          <span class="hamburger-line"></span>
        </span>
      </button>
    </div>

    <transition name="panel">
      <div v-if="menuOpen" class="navbar-panel">
        <!-- Tools -->
        <div class="panel-section">
          <span class="section-label">Tools</span>
          <div class="section-row">
            <button class="panel-btn" @click="openTextModal">📝 Edit Text</button>
            <button class="panel-btn" @click="openBgModal">🖼️ Background</button>
          </div>
        </div>

        <!-- Trance Engine -->
        <div class="panel-section trance-section">
          <div class="trance-header">
            <span class="section-label" :style="tranceSessionActive ? { color: tranceAccent } : {}">Trance</span>
            <div v-if="activeLayerCount > 0" class="depth-meter">
              <span class="depth-label">depth</span>
              <span
                v-for="i in totalLayers"
                :key="i"
                class="depth-dot"
                :class="{ filled: i <= activeLayerCount }"
              />
            </div>
          </div>

          <!-- Session journey control -->
          <div class="section-row">
            <button
              class="panel-btn"
              :class="{ 'panel-btn--active': tranceSessionActive }"
              @click="tranceSessionActive ? tranceStop() : tranceStart()"
            >
              {{ tranceSessionActive ? '&#9632; End' : '&#9654; Journey' }}
            </button>
            <span v-if="tranceSessionActive && phaseDisplayName" class="phase-pill" :style="{ borderColor: tranceAccent, color: tranceAccent }">
              {{ phaseDisplayName }}
              <template v-if="trancePhase === 'coherence'"> &middot; {{ tranceCoherence }}%</template>
            </span>
            <button
              v-if="canWindDown"
              class="panel-btn"
              @click="tranceWindDown()"
            >
              Wind Down
            </button>
          </div>

          <!-- Tone layers -->
          <div class="tone-layers">
            <button
              v-for="layer in toneLayers"
              :key="layer.key"
              class="tone-chip"
              :class="{ 'tone-chip--active': layer.active }"
              @click="layer.toggle()"
            >
              <span class="tone-tip">{{ layer.tooltip }}</span>
              <span class="tone-name">{{ layer.name }}</span>
              <span class="tone-desc">{{ layer.desc }}</span>
            </button>
          </div>
        </div>

        <!-- Reader controls (conditional) -->
        <div v-if="storyText" class="panel-section">
          <span class="section-label">Reader</span>
          <div class="section-row">
            <button class="panel-btn" @click="togglePlayback">
              {{ isPlaying ? '⏸ Pause' : '▶ Play' }}
            </button>
            <button class="panel-btn" @click="reset">⏮ Reset</button>
            <span class="panel-stat">{{ currentIndex + 1 }} / {{ words.length }}</span>
          </div>
        </div>

      </div>
    </transition>
  </nav>

  <!-- Touch/click overlay: catches taps on iframe content when navbar is hidden -->
  <Teleport to="body">
    <div
      v-if="isFullBleed && !navVisible"
      class="nav-activity-overlay"
      @touchstart.passive="showNav"
      @click="showNav"
    ></div>
  </Teleport>

  <!-- Text edit modal -->
  <Teleport to="body">
    <div v-if="showTextModal" class="modal-overlay" @click.self="showTextModal = false">
      <div class="modal">
        <h2>Enter Text</h2>

        <label class="modal-file-upload">
          <input type="file" accept=".txt,.md" @change="handleFileUpload" />
          <span class="modal-upload-btn">Choose File</span>
          <span v-if="fileName" class="modal-file-name">{{ fileName }}</span>
        </label>

        <div class="modal-divider">or</div>

        <textarea
          v-model="textInputValue"
          placeholder="Paste your text here..."
          class="modal-textarea"
          rows="10"
        ></textarea>

        <div class="modal-actions">
          <button
            class="modal-btn modal-btn--primary"
            :disabled="!textInputValue.trim()"
            @click="loadText"
          >
            Start Reading
          </button>
          <button class="modal-btn" @click="showTextModal = false">Close</button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- Background upload modal -->
  <Teleport to="body">
    <div v-if="showBgModal" class="modal-overlay" @click.self="showBgModal = false">
      <div class="modal">
        <h2>Set Background</h2>

        <div v-if="backgroundMedia" class="bg-preview">
          <video
            v-if="isBackgroundVideo"
            :src="backgroundMedia"
            autoplay
            loop
            muted
            playsinline
            class="bg-preview-media"
          ></video>
          <img v-else :src="backgroundMedia" class="bg-preview-media" alt="background preview" />
        </div>

        <label class="modal-file-upload">
          <input type="file" accept="image/gif,video/mp4,video/webm" @change="handleBgUpload" />
          <span class="modal-upload-btn">{{
            backgroundMedia ? 'Change File' : 'Choose File'
          }}</span>
        </label>

        <div class="modal-actions">
          <button
            v-if="backgroundMedia"
            class="modal-btn modal-btn--danger"
            @click="clearBackgroundMedia(), (showBgModal = false)"
          >
            Clear Background
          </button>
          <button class="modal-btn" @click="showBgModal = false">Close</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* ── Default sticky bar ── */
.navbar {
  position: sticky;
  top: 0;
  z-index: 1000;
  background: rgba(10, 10, 20, 0.9);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  transition:
    opacity 0.4s ease,
    transform 0.4s ease;
}

.navbar--hidden {
  opacity: 0;
  transform: translateY(-100%);
  pointer-events: none;
}

/* ── Floating mode (fullbleed pages) ── */
.navbar--floating {
  position: fixed;
  top: 0;
  right: 0;
  left: auto;
  background: transparent;
  backdrop-filter: none;
  border-bottom: none;
  pointer-events: none;
}

.navbar--floating .navbar-top {
  justify-content: flex-end;
  padding: 0.75rem;
}

.navbar--floating .menu-btn,
.navbar--floating .fullscreen-btn,
.navbar--floating .nav-links,
.navbar--floating .navbar-panel,
.navbar--floating .auth-btn {
  pointer-events: auto;
}

/* When opened on fullbleed, give the menu a backdrop */
.navbar--floating.navbar--open {
  left: 0;
  background: rgba(10, 10, 20, 0.85);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.navbar--floating.navbar--open .navbar-top {
  justify-content: flex-start;
}

.navbar-top {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
}

/* ── Nav links spacer (links moved to sidebar) ── */
.nav-links-spacer { flex: 1; }

/* ── Nav links row ── */
.nav-links {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  flex: 1;
}

.nav-link {
  position: relative;
  display: inline-flex;
  align-items: center;
  padding: 0.4rem 0.75rem;
  color: #94a3b8;
  text-decoration: none;
  font-size: 0.85rem;
  letter-spacing: 0.01em;
  white-space: nowrap;
  transition: color 0.15s ease;
}

.nav-link::after {
  content: '';
  position: absolute;
  left: 0.75rem;
  right: 0.75rem;
  bottom: 0.15rem;
  height: 1px;
  background: currentColor;
  opacity: 0;
  transform: scaleX(0.6);
  transform-origin: center;
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.nav-link:hover {
  color: #e2e8f0;
}

.nav-link--active {
  color: #e2e8f0;
}

.nav-link--active::after {
  opacity: 1;
  transform: scaleX(1);
}

/* ── Pipeline widget ── */
.nav-pipeline {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.6rem;
  border-radius: 0.4rem;
  border: 1px solid rgba(99, 102, 241, 0.25);
  color: #6366f1;
  text-decoration: none;
  font-size: 0.75rem;
  white-space: nowrap;
  margin-left: 0.25rem;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
}

.nav-pipeline:hover {
  border-color: rgba(99, 102, 241, 0.5);
  background: rgba(99, 102, 241, 0.08);
  color: #818cf8;
}

.nav-pipeline--active {
  background: rgba(99, 102, 241, 0.12);
}

.pipeline-dots {
  display: flex;
  align-items: center;
  gap: 3px;
}

.pipeline-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}

.pipeline-dot--done {
  background: #6366f1;
}

.pipeline-dot--pending {
  background: rgba(99, 102, 241, 0.25);
  border: 1px solid rgba(99, 102, 241, 0.4);
}

.pipeline-label {
  font-size: 0.72rem;
  font-weight: 500;
  letter-spacing: 0.02em;
}

/* ── Hamburger button ── */
.menu-btn {
  flex-shrink: 0;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 0.4rem;
  color: #94a3b8;
  width: 2.25rem;
  height: 2.25rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    color 0.15s,
    border-color 0.15s,
    background 0.15s;
  padding: 0;
}

.menu-btn:hover {
  color: #e2e8f0;
  border-color: rgba(255, 255, 255, 0.25);
}

/* ── Auth button ── */
.auth-btn {
  flex-shrink: 0;
  margin-left: auto;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 0.4rem;
  color: #94a3b8;
  width: 2.25rem;
  height: 2.25rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  transition:
    color 0.15s,
    border-color 0.15s,
    background 0.15s;
  padding: 0;
}

.auth-btn svg {
  width: 16px;
  height: 16px;
}

.auth-btn:hover {
  color: #e2e8f0;
  border-color: rgba(255, 255, 255, 0.25);
}

.auth-btn--user:hover {
  color: #f87171;
  border-color: rgba(248, 113, 113, 0.4);
}

/* ── Fullscreen button ── */
.fullscreen-btn {
  flex-shrink: 0;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 0.4rem;
  color: #94a3b8;
  width: 2.25rem;
  height: 2.25rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    color 0.15s,
    border-color 0.15s,
    background 0.15s;
  padding: 0;
}

.fullscreen-btn:hover {
  color: #e2e8f0;
  border-color: rgba(255, 255, 255, 0.25);
}

.fullscreen-btn--floating {
  width: 2.75rem;
  height: 2.75rem;
  border: none;
  background: transparent;
  border-radius: 0.5rem;
  color: rgba(255, 255, 255, 0.6);
}

.fullscreen-btn--floating:hover {
  background: rgba(255, 255, 255, 0.08);
}

/* Floating hamburger — fully transparent, just the lines */
.menu-btn--floating {
  width: 2.75rem;
  height: 2.75rem;
  border: none;
  background: transparent;
  border-radius: 0.5rem;
}

.menu-btn--floating:hover {
  background: rgba(255, 255, 255, 0.08);
}

/* ── Hamburger lines (CSS, not emoji) ── */
.hamburger-lines {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 4px;
  width: 20px;
  height: 20px;
}

.menu-btn--floating .hamburger-lines {
  gap: 5px;
  width: 24px;
  height: 24px;
}

.hamburger-line {
  display: block;
  width: 100%;
  height: 2px;
  background: currentColor;
  border-radius: 1px;
  transition:
    transform 0.25s ease,
    opacity 0.25s ease;
  transform-origin: center;
}

/* X transform when open */
.hamburger-lines--open .hamburger-line:nth-child(1) {
  transform: translateY(6px) rotate(45deg);
}

.hamburger-lines--open .hamburger-line:nth-child(2) {
  opacity: 0;
}

.hamburger-lines--open .hamburger-line:nth-child(3) {
  transform: translateY(-6px) rotate(-45deg);
}

.menu-btn--floating .hamburger-line {
  height: 2px;
  background: rgba(255, 255, 255, 0.6);
  box-shadow: 0 0 6px rgba(255, 255, 255, 0.15);
}

/* ── Expandable panel ── */
.navbar-panel {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding: 0.5rem 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.panel-enter-active,
.panel-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}

.panel-enter-from,
.panel-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.panel-enter-to,
.panel-leave-from {
  opacity: 1;
  max-height: 300px;
}

.panel-section {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.section-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.section-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
}

.panel-btn {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #cbd5e1;
  padding: 0.3rem 0.6rem;
  border-radius: 0.35rem;
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition:
    background 0.15s,
    color 0.15s,
    border-color 0.15s;
}

.panel-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #e2e8f0;
}

.panel-btn--active {
  background: rgba(99, 102, 241, 0.25);
  border-color: rgba(99, 102, 241, 0.4);
  color: #e2e8f0;
}

.panel-stat {
  font-size: 0.78rem;
  color: #64748b;
  padding: 0.3rem 0.5rem;
  font-variant-numeric: tabular-nums;
}

/* ── Session links ── */
.session-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.session-link {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.65rem;
  border-radius: 0.35rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: #94a3b8;
  font-size: 0.75rem;
  text-decoration: none;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
}

.session-link:hover {
  border-color: rgba(99, 102, 241, 0.4);
  background: rgba(99, 102, 241, 0.08);
  color: #e2e8f0;
}

.session-link-icon { font-size: 0.85rem; }
.session-link-label { font-weight: 500; }

/* ── Trance section ── */
.trance-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.depth-meter {
  display: flex;
  align-items: center;
  gap: 3px;
}

.depth-label {
  font-size: 0.55rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #475569;
  margin-right: 4px;
}

.depth-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  transition: background 0.3s, box-shadow 0.3s;
}

.depth-dot.filled {
  background: #6366f1;
  box-shadow: 0 0 6px rgba(99, 102, 241, 0.5);
}

.phase-pill {
  font-size: 0.7rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 0.2rem 0.6rem;
  border: 1px solid;
  border-radius: 1rem;
  font-variant-numeric: tabular-nums;
}

.tone-layers {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.tone-chip {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 0.5rem;
  padding: 0.35rem 0.6rem;
  cursor: pointer;
  transition: all 0.2s;
  min-width: 5rem;
  font-family: inherit;
  color: #94a3b8;
}

.tone-chip:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.15);
  color: #cbd5e1;
}

.tone-chip--active {
  background: rgba(99, 102, 241, 0.15);
  border-color: rgba(99, 102, 241, 0.4);
  color: #e2e8f0;
  box-shadow: 0 0 8px rgba(99, 102, 241, 0.15);
}

.tone-chip--active:hover {
  background: rgba(99, 102, 241, 0.25);
}

.tone-name {
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.2;
}

.tone-desc {
  font-size: 0.55rem;
  letter-spacing: 0.06em;
  color: #64748b;
  text-transform: lowercase;
}

.tone-chip--active .tone-desc {
  color: rgba(165, 180, 252, 0.6);
}

/* ── Tone chip tooltip ── */
.tone-tip {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  width: 220px;
  background: rgba(10, 8, 20, 0.97);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 0.55rem;
  padding: 0.55rem 0.7rem;
  font-size: 0.6rem;
  line-height: 1.65;
  color: #94a3b8;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.18s ease;
  z-index: 200;
  text-transform: none;
  text-align: left;
  white-space: pre-line;
  letter-spacing: 0.01em;
  font-weight: 400;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.5);
}

.tone-tip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: rgba(10, 8, 20, 0.97);
}

.tone-chip:hover .tone-tip {
  opacity: 1;
}

.tone-chip--active .tone-tip {
  border-color: rgba(99, 102, 241, 0.25);
  color: #a5b4fc;
}

/* ── Desktop tweaks ── */
@media (min-width: 769px) {
  .navbar-panel {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 1rem;
  }

  .panel-section {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
  }

  /* Trance section stays columnar on desktop for the layer grid */
  .panel-section.trance-section {
    flex-direction: column;
    align-items: stretch;
  }

  .section-label {
    font-size: 0.7rem;
  }

  .panel-section + .panel-section {
    padding-left: 1rem;
    border-left: 1px solid rgba(255, 255, 255, 0.06);
  }
}

/* ── Modals (shared) ── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}

.modal {
  background: rgba(20, 20, 40, 0.95);
  padding: 2rem;
  border-radius: 1rem;
  border: 1px solid rgba(100, 100, 255, 0.3);
  max-width: 600px;
  width: 90%;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.modal h2 {
  color: #e2e8f0;
  font-size: 1.25rem;
  margin: 0;
}

.modal-file-upload {
  display: flex;
  align-items: center;
  gap: 1rem;
  cursor: pointer;
}

.modal-file-upload input {
  display: none;
}

.modal-upload-btn {
  background-color: #374151;
  color: #e2e8f0;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  transition: background-color 0.2s;
}

.modal-upload-btn:hover {
  background-color: #4b5563;
}

.modal-file-name {
  color: #94a3b8;
  font-size: 0.875rem;
}

.modal-divider {
  color: #64748b;
  font-size: 0.875rem;
  text-align: center;
}

.modal-textarea {
  width: 100%;
  padding: 1rem;
  background: rgba(30, 30, 50, 0.9);
  border: 1px solid rgba(100, 100, 255, 0.3);
  color: #e2e8f0;
  border-radius: 0.5rem;
  font-family: inherit;
  font-size: 1rem;
  resize: vertical;
}

.modal-textarea::placeholder {
  color: #64748b;
}

.modal-textarea:focus {
  border-color: #6366f1;
}
.modal-textarea:focus:not(:focus-visible) {
  outline: none;
}

.modal-actions {
  display: flex;
  gap: 0.75rem;
}

.modal-btn {
  background: #374151;
  border: none;
  color: #e2e8f0;
  padding: 0.75rem 1.5rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-family: inherit;
  font-size: 0.9rem;
  transition: background-color 0.2s;
}

.modal-btn:hover {
  background: #4b5563;
}

.modal-btn--primary {
  background: #6366f1;
}

.modal-btn--primary:hover:not(:disabled) {
  background: #4f46e5;
}

.modal-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modal-btn--danger {
  background: #991b1b;
  color: #fecaca;
}

.modal-btn--danger:hover {
  background: #b91c1c;
}

.bg-preview {
  border-radius: 0.5rem;
  overflow: hidden;
  max-height: 200px;
}

.bg-preview-media {
  width: 100%;
  max-height: 200px;
  object-fit: contain;
}
</style>

<style>
/* Non-scoped: this element is teleported to <body> */
.nav-activity-overlay {
  position: fixed;
  inset: 0;
  z-index: 999;
  background: transparent;
}
</style>
