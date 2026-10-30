<template>
  <div v-if="show" class="ql" :style="accentBorderStyle">

    <!-- Header row -->
    <div class="ql-header">
      <span class="ql-phase-label">{{ currentStep.phase }}</span>
      <div class="ql-dots">
        <span
          v-for="(s, i) in steps"
          :key="s.key"
          class="ql-dot"
          :class="{
            'ql-dot--done':    s.done,
            'ql-dot--current': i === currentIdx && !s.done,
            'ql-dot--locked':  i > currentIdx && !s.done,
          }"
        ></span>
      </div>
      <span class="ql-fraction">{{ doneCount }} / {{ steps.length }}</span>
    </div>

    <!-- Progress bar -->
    <div class="ql-bar">
      <div class="ql-bar-fill" :style="{ width: `${(doneCount / steps.length) * 100}%`, background: currentStep.color }"></div>
    </div>

    <!-- Body -->
    <div class="ql-body">
      <!-- Completed steps (last 1 shown as context) -->
      <div v-if="prevStep" class="ql-prev">
        <span class="ql-check">✓</span>
        <span class="ql-prev-label">{{ prevStep.label }}</span>
      </div>

      <!-- Current step -->
      <div class="ql-current">
        <span class="ql-current-icon" :style="{ color: currentStep.color }">{{ currentStep.icon }}</span>
        <div class="ql-current-text">
          <span class="ql-current-label" :style="{ color: currentStep.color }">{{ currentStep.label }}</span>
          <span class="ql-current-desc">{{ currentStep.desc }}</span>
        </div>
      </div>

      <!-- Next locked step (fog of war) -->
      <div v-if="nextStep" class="ql-next">
        <span class="ql-lock" aria-hidden="true">░</span>
        <span class="ql-next-label">{{ nextStep.label }}</span>
      </div>
    </div>

    <!-- CTA -->
    <button
      class="ql-cta"
      :style="{ '--ql-color': currentStep.color }"
      @click="navigate"
    >
      {{ currentStep.action }}
      <svg viewBox="0 0 16 16" fill="none" class="ql-arrow">
        <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePollStore } from '@/composables/usePollStore'
import { useVibeStore } from '@/composables/useVibeStore'
import { useAuthStore } from '@/composables/useAuthStore'

const router = useRouter()
const { token: pollToken } = usePollStore()
const { oauthState } = useVibeStore()
const { isAuthenticated } = useAuthStore()

// ── Onboarding state (mirrors NavBar / OnboardingView) ───────────────────────

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

// Re-sync when poll completes mid-session
watch(pollToken, (t) => {
  if (t) {
    onboarding.value = { ...loadOnboarding(), poll: true }
  }
})

// ── Step definitions ─────────────────────────────────────────────────────────

interface Step {
  key:    string
  phase:  string       // "Phase 1 — Attunement"
  label:  string       // short name
  desc:   string       // body copy
  action: string       // CTA label
  icon:   string
  color:  string
  route:  string
  done:   boolean
}

const steps = computed<Step[]>(() => {
  const oauth = oauthState.value
  const connectedCount = Object.values(oauth).filter((p) => p.connected).length
  return [
    {
      key:    'attune',
      phase:  'Phase 1 — Attunement',
      label:  'Attunement',
      desc:   'Four questions map your experience archetype and set the palette for everything that follows.',
      action: 'Take the poll',
      icon:   '✦',
      color:  '#a78bfa',
      route:  '/',
      done:   !!pollToken.value,
    },
    {
      key:    'spotify',
      phase:  'Phase 2 — Signal Collection',
      label:  'Connect Spotify',
      desc:   'Your listening history becomes a sonic coordinate — valence, energy, genre fingerprint.',
      action: 'Connect Spotify',
      icon:   '♫',
      color:  '#1db954',
      route:  '/calibrate',
      done:   oauth.spotify.connected,
    },
    {
      key:    'twitter',
      phase:  'Phase 2 — Signal Collection',
      label:  'Connect X',
      desc:   'Your public signal reveals neurotic output patterns — what you say and when you say it.',
      action: 'Connect X',
      icon:   '✕',
      color:  '#1d9bf0',
      route:  '/calibrate',
      done:   oauth.twitter.connected,
    },
    {
      key:    'confess',
      phase:  'Phase 3 — Confession',
      label:  'Confession',
      desc:   'Speak to the Oracle. Your unfiltered thoughts are encrypted and analyzed — the rawest signal in your profile.',
      action: 'Open intake',
      icon:   '◈',
      color:  '#38bdf8',
      route:  '/intake',
      done:   onboarding.value.intake,
    },
    {
      key:    'portrait',
      phase:  'Phase 4 — Integration',
      label:  'Integrated Portrait',
      desc:   connectedCount >= 2
        ? 'Your streams are ready to be woven into a single portrait — one reading across everything you shared.'
        : 'Connect at least two sources and the portrait becomes possible.',
      action: 'Sit for your portrait',
      icon:   '◉',
      color:  '#818cf8',
      route:  '/portrait',
      done:   false,
    },
    {
      key:    'checkin',
      phase:  'Phase 5 — Daily Practice',
      label:  'Daily Check-In',
      desc:   'Return daily. A mood read and arc — your inner weather tracked over time.',
      action: 'Check in',
      icon:   '◐',
      color:  '#34d399',
      route:  '/checkin',
      done:   false,
    },
  ]
})

const currentIdx  = computed(() => steps.value.findIndex((s) => !s.done))
const currentStep = computed(() => steps.value[currentIdx.value] ?? steps.value[steps.value.length - 1])
const prevStep    = computed(() => currentIdx.value > 0 ? steps.value[currentIdx.value - 1] : null)
const nextStep    = computed(() => steps.value[currentIdx.value + 1] ?? null)
const doneCount   = computed(() => steps.value.filter((s) => s.done).length)

// Only show for authenticated users with incomplete pipeline
const show = computed(() =>
  isAuthenticated.value && currentIdx.value !== -1,
)

const accentBorderStyle = computed(() => ({
  '--ql-accent': currentStep.value.color,
}))

// ── Navigation ────────────────────────────────────────────────────────────────

const emit = defineEmits<{ (e: 'start-poll'): void }>()

function navigate() {
  if (currentStep.value.key === 'attune') {
    // Poll is inline on the homepage — bubble up to parent
    emit('start-poll')
  } else {
    router.push(currentStep.value.route)
  }
}
</script>

<style scoped>
.ql {
  --ql-accent: #a78bfa;
  margin: 0 0 1.25rem;
  padding: 1rem 1.25rem 1rem;
  background: rgba(15, 12, 28, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-left: 2px solid var(--ql-accent);
  border-radius: 0.75rem;
  backdrop-filter: blur(10px);
  transition: border-color 0.4s ease;
}

/* ── Header ── */
.ql-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 0.55rem;
}

.ql-phase-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #475569;
  font-weight: 600;
  flex: 1;
}

.ql-dots {
  display: flex;
  gap: 4px;
}

.ql-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  transition: background 0.3s, box-shadow 0.3s;
}

.ql-dot--done {
  background: #6366f1;
}

.ql-dot--current {
  background: var(--ql-accent);
  box-shadow: 0 0 6px var(--ql-accent);
}

.ql-dot--locked {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.ql-fraction {
  font-size: 0.65rem;
  color: #334155;
  font-variant-numeric: tabular-nums;
}

/* ── Progress bar ── */
.ql-bar {
  height: 1px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 1px;
  margin-bottom: 0.85rem;
  overflow: hidden;
}

.ql-bar-fill {
  height: 100%;
  border-radius: 1px;
  transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1), background 0.4s;
}

/* ── Body ── */
.ql-body {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-bottom: 0.9rem;
}

/* Prev step (completed context) */
.ql-prev {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  opacity: 0.35;
}

.ql-check {
  font-size: 0.7rem;
  color: #6366f1;
}

.ql-prev-label {
  font-size: 0.72rem;
  color: #64748b;
  text-decoration: line-through;
}

/* Current step */
.ql-current {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
}

.ql-current-icon {
  font-size: 1rem;
  line-height: 1.3;
  flex-shrink: 0;
  transition: color 0.4s;
}

.ql-current-text {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.ql-current-label {
  font-size: 0.82rem;
  font-weight: 600;
  transition: color 0.4s;
}

.ql-current-desc {
  font-size: 0.78rem;
  color: #64748b;
  line-height: 1.5;
}

/* Next locked step (fog of war) */
.ql-next {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  opacity: 0.22;
}

.ql-lock {
  font-size: 0.7rem;
  color: #334155;
  letter-spacing: -0.05em;
}

.ql-next-label {
  font-size: 0.72rem;
  color: #334155;
}

/* ── CTA ── */
.ql-cta {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.9rem;
  border-radius: 100px;
  border: 1px solid color-mix(in srgb, var(--ql-color) 40%, transparent);
  background: color-mix(in srgb, var(--ql-color) 10%, transparent);
  color: var(--ql-color);
  font-family: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.ql-cta:hover {
  border-color: color-mix(in srgb, var(--ql-color) 70%, transparent);
  background: color-mix(in srgb, var(--ql-color) 18%, transparent);
}

.ql-arrow {
  width: 12px;
  height: 12px;
}
</style>
