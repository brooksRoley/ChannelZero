<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { RouterLink, useRouter, useRoute } from 'vue-router'
import { useStoryStore } from '@/composables/useStoryStore'
import { useAuthStore } from '@/composables/useAuthStore'
import { usePollStore } from '@/composables/usePollStore'
import NavBarTextModal from './NavBarTextModal.vue'
import NavBarBgModal from './NavBarBgModal.vue'
import NavTrancePanel from './NavTrancePanel.vue'

const router = useRouter()
const route = useRoute()
const {
  storyText,
  words,
  currentIndex,
  isPlaying,
  play,
  pause,
  reset,
} = useStoryStore()

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

// Modal visibility
const showTextModal = ref(false)
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
  showTextModal.value = true
  menuOpen.value = false
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
        <NavTrancePanel />

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

  <NavBarTextModal v-model="showTextModal" />
  <NavBarBgModal v-model="showBgModal" />
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

.menu-btn:focus-visible,
.auth-btn:focus-visible,
.fullscreen-btn:focus-visible {
  outline: 2px solid #6366f1;
  outline-offset: 2px;
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

  .section-label {
    font-size: 0.7rem;
  }

  .panel-section + .panel-section {
    padding-left: 1rem;
    border-left: 1px solid rgba(255, 255, 255, 0.06);
  }
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
