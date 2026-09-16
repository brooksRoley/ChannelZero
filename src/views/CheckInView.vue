<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useJournalStore } from '@/composables/useJournalStore'
import type { JournalSynthesis } from '@/composables/useJournalStore'
import { usePollStore } from '@/composables/usePollStore'
import { useTTS } from '@/composables/useTTS'
import { useAnalytics } from '@/composables/useAnalytics'

const router = useRouter()
const {
  todayEntries,
  sortedEntries,
  synthesizeToday,
  createEntry,
  setActiveEntry
} = useJournalStore()

const { token } = usePollStore()
const { speak, stop, isSpeaking, toggle, progress: ttsProgress } = useTTS()
const { logEvent } = useAnalytics()

// ── Funnel instrumentation ─────────────────────────────────────────
let completedFired = false
function markCheckinComplete(via: string) {
  if (completedFired) return
  completedFired = true
  logEvent('checkin_completed', { via })
}

// ── State ──────────────────────────────────────────────────────────

const synthesis = ref<JournalSynthesis | null>(null)
const greeting = ref('')
const intentionText = ref('')
const intentionSaved = ref(false)

// ── Greeting based on time of day ──────────────────────────────────

function buildGreeting(): string {
  const hour = new Date().getHours()
  if (hour < 5) return 'Late night, huh?'
  if (hour < 12) return 'Good morning.'
  if (hour < 17) return 'Good afternoon.'
  if (hour < 21) return 'Good evening.'
  return 'Winding down?'
}

// ── Today's mood arc ───────────────────────────────────────────────

const moodArc = computed(() => {
  return todayEntries.value
    .filter((e) => e.mood)
    .map((e) => ({
      mood: e.mood!,
      time: new Date(e.createdAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    }))
})

const todayStats = computed(() => ({
  entries: todayEntries.value.length,
  drawings: todayEntries.value.reduce((n, e) => n + e.drawings.length, 0),
  audioClips: todayEntries.value.reduce((n, e) => n + e.audioClips.length, 0),
  words: todayEntries.value.reduce((n, e) => n + e.text.split(/\s+/).filter(Boolean).length, 0)
}))

// ── Recent entries (last 7 days, excluding today) ──────────────────

const recentEntries = computed(() => {
  const todayStart = new Date()
  todayStart.setHours(0, 0, 0, 0)
  const weekAgo = todayStart.getTime() - 7 * 24 * 60 * 60 * 1000
  return sortedEntries.value.filter(
    (e) => e.createdAt < todayStart.getTime() && e.createdAt >= weekAgo
  )
})

// ── Streak calc ───────────────────────────────────────────────────

const streakDays = computed(() => {
  if (sortedEntries.value.length === 0) return 0
  let streak = 0
  const now = new Date()
  now.setHours(0, 0, 0, 0)

  // Check today first
  const todayMs = now.getTime()
  const hasToday = sortedEntries.value.some((e) => e.createdAt >= todayMs)
  if (!hasToday) {
    // Check if yesterday had entries (streak not yet broken)
    const yesterdayMs = todayMs - 86400000
    const hasYesterday = sortedEntries.value.some(
      (e) => e.createdAt >= yesterdayMs && e.createdAt < todayMs
    )
    if (!hasYesterday) return 0
  }

  // Walk backwards from today
  for (let d = 0; d < 365; d++) {
    const dayStart = todayMs - d * 86400000
    const dayEnd = dayStart + 86400000
    const hasEntry = sortedEntries.value.some(
      (e) => e.createdAt >= dayStart && e.createdAt < dayEnd
    )
    if (hasEntry) streak++
    else if (d > 0) break // gap found, stop counting
  }
  return streak
})

// ── Actions ────────────────────────────────────────────────────────

function runSynthesis() {
  synthesis.value = synthesizeToday()
  markCheckinComplete('synthesis')
}

function readSynthesisAloud() {
  if (!synthesis.value) return
  const text = synthesis.value.summary || 'No journal entries to read back today.'
  toggle(text)
}

function saveIntention() {
  if (!intentionText.value.trim()) return
  const entry = createEntry(intentionText.value.trim())
  entry.mood = 'intentional'
  intentionSaved.value = true
  setTimeout(() => {
    intentionSaved.value = false
  }, 2000)
  intentionText.value = ''
  markCheckinComplete('intention')
}

function goToJournal() {
  router.push('/journal')
}

function openEntry(id: string) {
  setActiveEntry(id)
  router.push('/journal')
}

// ── Lifecycle ──────────────────────────────────────────────────────

onMounted(() => {
  greeting.value = buildGreeting()
  logEvent('checkin_started')
  if (todayEntries.value.length > 0) {
    synthesis.value = synthesizeToday()
  }
})

// ── Helpers ────────────────────────────────────────────────────────

function formatDate(ms: number): string {
  return new Date(ms).toLocaleDateString([], {
    weekday: 'short',
    month: 'short',
    day: 'numeric'
  })
}

function truncate(text: string, len = 80): string {
  if (text.length <= len) return text
  return text.slice(0, len).trimEnd() + '…'
}

const accent = computed(() => token.value?.palette?.accent || '#a78bfa')
</script>

<template>
  <div class="checkin-wrap">
    <div class="checkin-card">
      <!-- Header -->
      <header class="checkin-header">
        <h1 class="greeting" :style="{ color: accent }">{{ greeting }}</h1>
        <p class="date-line">{{ new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }) }}</p>
      </header>

      <!-- Streak + Stats ribbon -->
      <div class="stats-ribbon">
        <div class="stat-pill">
          <span class="stat-icon">🔥</span>
          <span class="stat-num">{{ streakDays }}</span>
          <span class="stat-label">day streak</span>
        </div>
        <div class="stat-pill" v-if="todayStats.entries > 0">
          <span class="stat-num">{{ todayStats.entries }}</span>
          <span class="stat-label">entries</span>
        </div>
        <div class="stat-pill" v-if="todayStats.words > 0">
          <span class="stat-num">{{ todayStats.words }}</span>
          <span class="stat-label">words</span>
        </div>
        <div class="stat-pill" v-if="todayStats.drawings > 0">
          <span class="stat-num">{{ todayStats.drawings }}</span>
          <span class="stat-label">drawings</span>
        </div>
        <div class="stat-pill" v-if="todayStats.audioClips > 0">
          <span class="stat-num">{{ todayStats.audioClips }}</span>
          <span class="stat-label">clips</span>
        </div>
      </div>

      <!-- Today's Mood Arc -->
      <section v-if="moodArc.length > 0" class="section">
        <h2 class="section-heading">Mood Arc</h2>
        <div class="mood-timeline">
          <div v-for="(point, i) in moodArc" :key="i" class="mood-point">
            <span class="mood-time">{{ point.time }}</span>
            <span class="mood-chip" :style="{ borderColor: accent }">{{ point.mood }}</span>
          </div>
        </div>
      </section>

      <!-- Synthesis -->
      <section class="section">
        <div class="section-header-row">
          <h2 class="section-heading">Today's Synthesis</h2>
          <button
            v-if="todayEntries.length > 0"
            class="btn-small"
            @click="runSynthesis"
          >
            {{ synthesis ? 'Refresh' : 'Synthesize' }}
          </button>
        </div>

        <div v-if="synthesis" class="synthesis-block">
          <p class="synthesis-text">{{ synthesis.summary || 'Nothing written yet today.' }}</p>
          <div v-if="synthesis.keywords.length" class="keyword-row">
            <span
              v-for="kw in synthesis.keywords"
              :key="kw"
              class="kw-chip"
              :style="{ borderColor: accent + '44', color: accent }"
            >{{ kw }}</span>
          </div>
          <button class="btn-ghost" @click="readSynthesisAloud">
            {{ isSpeaking ? '■ Stop' : '▶ Read aloud' }}
          </button>
          <div v-if="isSpeaking" class="tts-bar">
            <div class="tts-fill" :style="{ width: ttsProgress + '%', background: accent }" />
          </div>
        </div>

        <p v-else class="empty-note">
          {{ todayEntries.length === 0 ? 'No entries yet today. Start journaling to see your synthesis here.' : 'Tap Synthesize to reflect on today\'s writing.' }}
        </p>
      </section>

      <!-- Set Intention -->
      <section class="section">
        <h2 class="section-heading">Set an Intention</h2>
        <div class="intention-row">
          <textarea
            v-model="intentionText"
            class="intention-input"
            rows="2"
            placeholder="What do you want to carry into today?"
            aria-label="Set your intention for today"
          />
          <button
            class="btn-accent"
            :style="{ background: accent + '22', borderColor: accent + '55', color: accent }"
            :disabled="!intentionText.trim()"
            @click="saveIntention"
          >
            {{ intentionSaved ? '✓ Saved' : 'Set' }}
          </button>
        </div>
      </section>

      <!-- Recent (last 7 days) -->
      <section v-if="recentEntries.length > 0" class="section">
        <h2 class="section-heading">This Week</h2>
        <div class="recent-list">
          <button
            v-for="entry in recentEntries.slice(0, 5)"
            :key="entry.id"
            class="recent-card"
            @click="openEntry(entry.id)"
          >
            <span class="recent-date">{{ formatDate(entry.createdAt) }}</span>
            <span class="recent-preview">{{ truncate(entry.text) || '(drawing / audio only)' }}</span>
            <span v-if="entry.mood" class="recent-mood">{{ entry.mood }}</span>
          </button>
        </div>
      </section>

      <!-- Quick actions -->
      <div class="actions-row">
        <button class="btn-primary" :style="{ background: accent }" @click="goToJournal">
          Open Journal
        </button>
      </div>

      <!-- Pipeline actions -->
      <section class="section pipeline-section">
        <h2 class="section-heading">The Pipeline</h2>
        <div class="pipeline-row">
          <button class="pipeline-btn" @click="router.push('/intake')">
            <span class="pipeline-step">1</span>
            <span class="pipeline-label">The Intake</span>
            <span class="pipeline-desc">Psychoanalytic confessional</span>
          </button>
          <button class="pipeline-btn" @click="router.push('/portrait')">
            <span class="pipeline-step">2</span>
            <span class="pipeline-label">Your Portrait</span>
            <span class="pipeline-desc">Cross-connector self-reading</span>
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.checkin-wrap {
  min-height: calc(100vh - 3rem);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 2rem 1rem 4rem;
}

.checkin-card {
  width: 100%;
  max-width: 640px;
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

/* ── Header ── */
.checkin-header {
  text-align: center;
}

.greeting {
  font-size: 1.6rem;
  font-weight: 700;
  margin: 0 0 0.25rem;
  letter-spacing: 0.01em;
}

.date-line {
  font-size: 0.8rem;
  color: #64748b;
  margin: 0;
}

/* ── Stats ribbon ── */
.stats-ribbon {
  display: flex;
  gap: 0.75rem;
  justify-content: center;
  flex-wrap: wrap;
}

.stat-pill {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.4rem 0.75rem;
  border-radius: 2rem;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 0.78rem;
  color: #94a3b8;
}

.stat-icon {
  font-size: 0.85rem;
}

.stat-num {
  font-weight: 600;
  color: #e2e8f0;
}

.stat-label {
  color: #64748b;
}

/* ── Sections ── */
.section {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  background: rgba(20, 20, 40, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0.75rem;
  padding: 1.25rem;
}

.section-heading {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: #64748b;
  margin: 0;
  font-weight: 600;
}

.section-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* ── Mood timeline ── */
.mood-timeline {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.mood-point {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
}

.mood-time {
  font-size: 0.65rem;
  color: #475569;
}

.mood-chip {
  font-size: 0.72rem;
  padding: 0.2rem 0.5rem;
  border-radius: 1rem;
  border: 1px solid rgba(167, 139, 250, 0.35);
  color: #cbd5e1;
  background: rgba(255, 255, 255, 0.04);
}

/* ── Synthesis ── */
.synthesis-block {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.synthesis-text {
  font-size: 0.88rem;
  color: #cbd5e1;
  line-height: 1.65;
  margin: 0;
}

.keyword-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.kw-chip {
  font-size: 0.7rem;
  padding: 0.15rem 0.5rem;
  border-radius: 0.3rem;
  border: 1px solid;
  background: rgba(255, 255, 255, 0.03);
}

.tts-bar {
  height: 2px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 1px;
  overflow: hidden;
}

.tts-fill {
  height: 100%;
  border-radius: 1px;
  transition: width 0.3s ease;
}

.empty-note {
  font-size: 0.82rem;
  color: #475569;
  margin: 0;
  font-style: italic;
}

/* ── Intention ── */
.intention-row {
  display: flex;
  gap: 0.5rem;
  align-items: flex-end;
}

.intention-input {
  flex: 1;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 0.5rem;
  padding: 0.6rem 0.75rem;
  font-family: inherit;
  font-size: 0.85rem;
  color: #e2e8f0;
  resize: none;
  transition: border-color 0.15s;
}

.intention-input:focus {
  outline: none;
  border-color: rgba(167, 139, 250, 0.4);
}

.intention-input::placeholder {
  color: #475569;
}

/* ── Recent entries ── */
.recent-list {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.recent-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 0.75rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0.5rem;
  cursor: pointer;
  font-family: inherit;
  text-align: left;
  color: #cbd5e1;
  transition: background 0.15s, border-color 0.15s;
  width: 100%;
}

.recent-card:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.12);
}

.recent-date {
  font-size: 0.7rem;
  color: #64748b;
  flex-shrink: 0;
  min-width: 5rem;
}

.recent-preview {
  font-size: 0.8rem;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-mood {
  font-size: 0.65rem;
  padding: 0.1rem 0.4rem;
  border-radius: 1rem;
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
  flex-shrink: 0;
}

/* ── Buttons ── */
.btn-small {
  font-size: 0.7rem;
  padding: 0.25rem 0.6rem;
  border-radius: 0.3rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: #94a3b8;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s, color 0.15s;
}

.btn-small:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #e2e8f0;
}

.btn-small:focus-visible {
  outline: 2px solid rgba(167, 139, 250, 0.7);
  outline-offset: 2px;
}

.btn-ghost {
  background: none;
  border: none;
  color: #64748b;
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
  padding: 0.3rem 0;
  transition: color 0.15s;
  text-align: left;
  width: fit-content;
}

.btn-ghost:hover {
  color: #94a3b8;
}

.btn-ghost:focus-visible {
  outline: 2px solid rgba(167, 139, 250, 0.7);
  outline-offset: 2px;
  border-radius: 0.2rem;
}

.btn-accent {
  font-size: 0.8rem;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  border: 1px solid;
  cursor: pointer;
  font-family: inherit;
  font-weight: 500;
  transition: opacity 0.15s;
  flex-shrink: 0;
}

.btn-accent:disabled {
  opacity: 0.3;
  cursor: default;
}

.btn-accent:focus-visible {
  outline: 2px solid rgba(167, 139, 250, 0.7);
  outline-offset: 2px;
}

.actions-row {
  display: flex;
  justify-content: center;
  gap: 0.75rem;
}

.btn-primary {
  font-size: 0.88rem;
  padding: 0.65rem 1.5rem;
  border-radius: 0.5rem;
  border: none;
  color: #0f0f1a;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
}

.btn-primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

.btn-primary:focus-visible {
  outline: 2px solid rgba(167, 139, 250, 0.7);
  outline-offset: 2px;
}

/* ── Pipeline ── */
.pipeline-section {
  border-color: rgba(99, 102, 241, 0.15);
}

.pipeline-row {
  display: flex;
  gap: 0.6rem;
}

.pipeline-btn {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 0.85rem 0.75rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0.5rem;
  cursor: pointer;
  font-family: inherit;
  color: #cbd5e1;
  transition: background 0.15s, border-color 0.15s;
}

.pipeline-btn:hover {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.3);
}

.pipeline-step {
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.3);
  color: #a5b4fc;
  font-size: 0.7rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pipeline-label {
  font-size: 0.85rem;
  font-weight: 500;
}

.pipeline-desc {
  font-size: 0.68rem;
  color: #64748b;
}

/* ── Mobile ── */
@media (max-width: 480px) {
  .checkin-wrap {
    padding: 1.5rem 0.75rem 3rem;
  }

  .greeting {
    font-size: 1.3rem;
  }

  .section {
    padding: 1rem;
  }

  .intention-row {
    flex-direction: column;
  }

  .btn-accent {
    width: 100%;
  }

  .recent-card {
    flex-wrap: wrap;
  }
}
</style>
