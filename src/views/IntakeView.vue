<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/composables/useAuthStore'
import { usePollStore } from '@/composables/usePollStore'
import { useJournalStore } from '@/composables/useJournalStore'

const router = useRouter()
const { apiFetch, isAuthenticated } = useAuthStore()
const { token: pollToken } = usePollStore()
const { getAllTodayText } = useJournalStore()

if (!isAuthenticated.value) {
  router.replace('/login')
}

// ── Chat State ────────────────────────────────────────────────────

interface Message {
  id: number
  role: 'user' | 'oracle'
  text: string
}

const messages = ref<Message[]>([
  {
    id: 1,
    role: 'oracle',
    text: 'Since you always carry the weight of the conversation, let me carry it for you today. Your sonic footprint suggests a sudden drop in valence. Who hurt you this week?',
  },
])

const userInput = ref('')
const sending = ref(false)
const confessed = ref(false)
const showCalendarHook = ref(false)
const analysisResult = ref<{
  attachment_style: string
  defense_mechanism: string
  readiness_score: number
  insight: string
} | null>(null)

const chatEl = ref<HTMLElement | null>(null)
const accent = computed(() => pollToken.value?.palette?.accent || '#a78bfa')

// ── Vibe marker extraction (ported from vibeUtils) ────────────────

interface VibeMarkers {
  valence: 'low' | 'mid' | 'high'
  dominance: 'passive' | 'assertive'
  arousal: 'flat' | 'activated'
}

function extractVibeMarkers(text: string): VibeMarkers {
  const lower = text.toLowerCase()
  const valence: VibeMarkers['valence'] =
    lower.match(/exhaust|tired|drain|hurt|disappoint|empty|numb|sad|angry/) ? 'low' :
    lower.match(/okay|fine|alright|manage|coping/) ? 'mid' : 'high'
  const dominance: VibeMarkers['dominance'] =
    lower.match(/can't|didn't|they made|had to|no choice|forced/) ? 'passive' : 'assertive'
  const arousal: VibeMarkers['arousal'] =
    lower.match(/whatever|numb|blank|flat|nothing/) ? 'flat' : 'activated'
  return { valence, dominance, arousal }
}

function generateOracleResponse(markers: VibeMarkers, exchangeCount: number): string {
  if (markers.valence === 'low' && markers.dominance === 'passive') {
    return exchangeCount < 3
      ? "You're describing a pattern where other people set the terms. When was the last time you chose the terms yourself?"
      : "Your syntax indicates high executive fatigue. You've been performing for someone who isn't watching. Say more about that."
  }
  if (markers.valence === 'low' && markers.arousal === 'flat') {
    return "That flatness you're describing — it's not peace. It's the sound of a system shutting down to protect itself. What would happen if you let yourself feel it instead?"
  }
  if (markers.dominance === 'assertive') {
    return "There's heat in that. You're not numb — you're angry and pretending you're not. Who are you really angry at?"
  }
  const fallbacks = [
    "I hear you. And what about the patterns — the ones you keep repeating even though you know better?",
    "That's honest. Now tell me: when you imagine someone really seeing you, what's the first feeling that comes up?",
    "We're getting somewhere. One more thing — what are you actually afraid will happen if you let someone in?",
    "Keep going. I'm listening.",
  ]
  return fallbacks[Math.min(exchangeCount, fallbacks.length - 1)]
}

// ── Actions ────────────────────────────────────────────────────────

async function sendMessage() {
  const text = userInput.value.trim()
  if (!text || sending.value) return

  messages.value.push({ id: Date.now(), role: 'user', text })
  userInput.value = ''
  sending.value = true
  await scrollToBottom()

  const userMessages = messages.value.filter((m) => m.role === 'user')
  const markers = extractVibeMarkers(text)

  // After 3+ exchanges, trigger confess endpoint
  if (userMessages.length >= 3 && !confessed.value) {
    await confess(userMessages.map((m) => m.text))
    return
  }

  // Oracle follow-up with vibe-marker-aware responses
  await fakePause()
  messages.value.push({
    id: Date.now() + 1,
    role: 'oracle',
    text: generateOracleResponse(markers, userMessages.length),
  })

  // Show calendar hook after 2+ exchanges
  if (userMessages.length >= 2 && markers.valence === 'low') {
    showCalendarHook.value = true
  }

  sending.value = false
  await scrollToBottom()
}

async function confess(confessions: string[]) {
  confessed.value = true

  messages.value.push({
    id: Date.now() + 1,
    role: 'oracle',
    text: 'Processing... I see the shape of it now.',
  })
  await scrollToBottom()

  try {
    const journalText = getAllTodayText()
    const result = await apiFetch<{
      attachment_style: string
      defense_mechanism: string
      readiness_score: number
      insight: string
    }>('/api/intake/confess', {
      method: 'POST',
      body: JSON.stringify({
        confessions,
        journal_context: journalText || null,
        poll_theme: pollToken.value?.theme || null,
      }),
    })

    analysisResult.value = result
    messages.value.push({ id: Date.now() + 2, role: 'oracle', text: result.insight })
  } catch {
    const fallback = localAnalysis(confessions)
    analysisResult.value = fallback
    messages.value.push({ id: Date.now() + 2, role: 'oracle', text: fallback.insight })
  }

  // Always show calendar hook after confession
  showCalendarHook.value = true
  sending.value = false
  await scrollToBottom()
}

function localAnalysis(confessions: string[]) {
  const text = confessions.join(' ').toLowerCase()

  let attachment_style = 'secure'
  if (text.match(/afraid|abandon|cling|need|anxious|worry/)) attachment_style = 'anxious-preoccupied'
  else if (text.match(/alone|independent|don't need|walls|distance|space/)) attachment_style = 'dismissive-avoidant'
  else if (text.match(/push.*pull|want.*afraid|close.*away|hot.*cold/)) attachment_style = 'fearful-avoidant'

  let defense_mechanism = 'rationalization'
  if (text.match(/joke|laugh|funny|humor/)) defense_mechanism = 'humor'
  else if (text.match(/project|blame|their fault|they always/)) defense_mechanism = 'projection'
  else if (text.match(/fine|whatever|doesn't matter|don't care/)) defense_mechanism = 'denial'
  else if (text.match(/think|analyze|figure out|understand why/)) defense_mechanism = 'intellectualization'

  const readiness_score = Math.min(100, Math.max(20, 40 + confessions.length * 15 + (text.length > 200 ? 20 : 0)))

  return {
    attachment_style,
    defense_mechanism,
    readiness_score,
    insight: buildInsight(attachment_style, defense_mechanism, readiness_score),
  }
}

function buildInsight(attachment: string, defense: string, score: number): string {
  const a: Record<string, string> = {
    'secure': 'You form connections with relative ease — grounded and open.',
    'anxious-preoccupied': 'You crave closeness but fear it will vanish. The wanting is the wound.',
    'dismissive-avoidant': 'You built walls so well you forgot there was something inside worth protecting.',
    'fearful-avoidant': 'You want to be seen but flinch when someone actually looks. Push and pull — the oldest dance.',
  }
  const d: Record<string, string> = {
    'humor': 'You deflect with wit — the joke is the armor.',
    'projection': 'You see your shadows in others before you see them in the mirror.',
    'denial': "\"I'm fine\" is doing a lot of heavy lifting.",
    'intellectualization': 'You analyze the feeling instead of feeling it.',
    'rationalization': 'You find reasons. There are always reasons.',
  }
  return `${a[attachment] || ''} ${d[defense] || ''} Readiness: ${score}/100. ${score >= 70 ? "You're ready to play." : "Almost there. Keep journaling."}`
}

function triggerCalendarSync() {
  // Phase 2: redirect to /api/oauth/google/calendar
  // For now, mark as synced and surface the game button
  showCalendarHook.value = false
  if (!analysisResult.value) {
    // Force analysis if they sync before 3 exchanges
    const userMessages = messages.value.filter((m) => m.role === 'user')
    if (userMessages.length > 0) {
      const fallback = localAnalysis(userMessages.map((m) => m.text))
      analysisResult.value = fallback
      confessed.value = true
      messages.value.push({
        id: Date.now(),
        role: 'oracle',
        text: 'Calendar synced. Recovery windows identified. ' + fallback.insight,
      })
    }
  } else {
    messages.value.push({
      id: Date.now(),
      role: 'oracle',
      text: 'Calendar synced. Your optimal deployment windows have been mapped. Thursday and Saturday nights are clear.',
    })
  }
  scrollToBottom()
}

function enterTheGame() {
  router.push('/portrait')
}

function goBack() {
  router.push('/checkin')
}

function fakePause() {
  return new Promise<void>((r) => setTimeout(r, 800 + Math.random() * 700))
}

async function scrollToBottom() {
  await nextTick()
  if (chatEl.value) chatEl.value.scrollTop = chatEl.value.scrollHeight
}
</script>

<template>
  <div class="intake-wrap">
    <div class="intake-card">
      <header class="intake-header">
        <button class="back-btn" @click="goBack">← Back</button>
        <h1 class="intake-title">The Oracle is listening.</h1>
        <p class="intake-subtitle">Since you carry the weight of the day, let us hold it for a moment.</p>
      </header>

      <!-- Chat thread -->
      <div ref="chatEl" class="chat-thread" aria-live="polite" aria-label="Oracle conversation">
        <TransitionGroup name="msg">
          <div
            v-for="msg in messages"
            :key="msg.id"
            :class="['msg', `msg--${msg.role}`]"
          >
            <div class="msg-bubble">{{ msg.text }}</div>
          </div>
        </TransitionGroup>

        <div v-if="sending" class="typing-indicator" role="status" aria-label="Oracle is responding">
          <span class="dot" /><span class="dot" /><span class="dot" />
        </div>
      </div>

      <!-- Calendar sync hook -->
      <Transition name="slide-up">
        <div v-if="showCalendarHook && !analysisResult" class="calendar-hook">
          <h3 class="hook-title">Protect Your Solitude</h3>
          <p class="hook-desc">
            Your syntax indicates high executive fatigue. Sync your calendar, and the Oracle will automatically block your recovery windows.
          </p>
          <button class="hook-btn" @click="triggerCalendarSync">
            Sync Calendar & Guard My Time
          </button>
        </div>
      </Transition>

      <!-- Analysis result card -->
      <Transition name="slide-up">
        <div v-if="analysisResult" class="analysis-card">
          <div class="analysis-grid">
            <div class="analysis-item">
              <span class="analysis-label">Attachment Style</span>
              <span class="analysis-value" :style="{ color: accent }">{{ analysisResult.attachment_style }}</span>
            </div>
            <div class="analysis-item">
              <span class="analysis-label">Defense Mechanism</span>
              <span class="analysis-value">{{ analysisResult.defense_mechanism }}</span>
            </div>
            <div class="analysis-item analysis-item--wide">
              <span class="analysis-label">Readiness</span>
              <div class="readiness-bar">
                <div class="readiness-fill" :style="{ width: `${analysisResult.readiness_score}%`, background: accent }" />
              </div>
              <span class="readiness-num">{{ analysisResult.readiness_score }}/100</span>
            </div>
          </div>

          <!-- Calendar sync (post-analysis) -->
          <button v-if="showCalendarHook" class="hook-btn hook-btn--inline" @click="triggerCalendarSync">
            Sync Calendar & Guard My Time
          </button>

          <button
            v-if="analysisResult.readiness_score >= 60"
            class="game-btn"
            :style="{ background: accent }"
            @click="enterTheGame"
          >
            Enter the Game
          </button>
          <p v-else class="not-ready">Keep journaling. The game will wait.</p>
        </div>
      </Transition>

      <!-- Input -->
      <div v-if="!confessed" class="input-row">
        <label for="oracle-input" class="sr-only">Tell the Oracle what's on your mind</label>
        <input
          id="oracle-input"
          v-model="userInput"
          type="text"
          class="chat-input"
          placeholder="Tell me what exhausted you today..."
          :disabled="sending"
          @keyup.enter="sendMessage"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.intake-wrap {
  min-height: calc(100vh - 3rem);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 2rem 1rem 4rem;
  position: relative;
}

.intake-card {
  width: 100%;
  max-width: 640px;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

/* ── Header ── */
.intake-header {
  text-align: center;
  position: relative;
  padding: 0 2rem;
}

.back-btn {
  position: absolute;
  left: 0;
  top: 0.25rem;
  background: none;
  border: none;
  color: #64748b;
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
  padding: 0.3rem 0;
  transition: color 0.15s;
}

.back-btn:hover { color: #94a3b8; }
.back-btn:focus-visible {
  outline: 2px solid rgba(99, 102, 241, 0.7);
  outline-offset: 3px;
  border-radius: 3px;
}

.intake-title {
  font-size: 1.25rem;
  font-weight: 600;
  font-style: italic;
  color: #e2e8f0;
  margin: 0;
}

.intake-subtitle {
  font-size: 0.78rem;
  color: #475569;
  margin: 0.35rem 0 0;
}

/* ── Chat thread ── */
.chat-thread {
  height: 380px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding: 1rem;
  background: rgba(10, 10, 25, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 0.75rem;
  backdrop-filter: blur(8px);
}

.chat-thread::-webkit-scrollbar { width: 4px; }
.chat-thread::-webkit-scrollbar-track { background: transparent; }
.chat-thread::-webkit-scrollbar-thumb { background: #374151; border-radius: 4px; }

.msg { max-width: 82%; }
.msg--user { align-self: flex-end; }
.msg--oracle { align-self: flex-start; }

.msg-bubble {
  font-size: 0.85rem;
  line-height: 1.6;
  padding: 0.7rem 0.9rem;
  border-radius: 0.75rem;
}

.msg--user .msg-bubble {
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.25);
  color: #e2e8f0;
  border-top-right-radius: 0.2rem;
}

.msg--oracle .msg-bubble {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: #94a3b8;
  border-top-left-radius: 0.2rem;
}

/* ── Typing indicator ── */
.typing-indicator {
  display: flex;
  gap: 0.25rem;
  padding: 0.5rem 0.85rem;
  align-self: flex-start;
}

.dot {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: #475569;
  animation: pulse-dot 1.2s ease-in-out infinite;
}
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse-dot {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

/* ── Message transitions ── */
.msg-enter-active { transition: all 0.3s ease; }
.msg-enter-from { opacity: 0; transform: translateY(8px); }

/* ── Calendar hook ── */
.calendar-hook {
  background: rgba(10, 10, 25, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 0.75rem;
  padding: 1.25rem;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6rem;
}

.hook-title {
  font-size: 1rem;
  font-weight: 600;
  color: #e2e8f0;
  margin: 0;
}

.hook-desc {
  font-size: 0.75rem;
  color: #64748b;
  max-width: 420px;
  margin: 0;
  line-height: 1.5;
}

.hook-btn {
  padding: 0.6rem 1.5rem;
  border-radius: 2rem;
  border: none;
  background: #e2e8f0;
  color: #0f0f1a;
  font-size: 0.82rem;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s, transform 0.1s;
  letter-spacing: -0.01em;
}

.hook-btn:hover {
  background: #fff;
  transform: translateY(-1px);
}
.hook-btn:focus-visible {
  outline: 2px solid rgba(99, 102, 241, 0.7);
  outline-offset: 3px;
}

.hook-btn--inline {
  align-self: center;
  background: rgba(255, 255, 255, 0.08);
  color: #94a3b8;
  border: 1px solid rgba(255, 255, 255, 0.12);
  font-weight: 500;
  border-radius: 0.4rem;
  padding: 0.5rem 1rem;
  font-size: 0.75rem;
}

.hook-btn--inline:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #e2e8f0;
}

/* ── Input ── */
.input-row {
  position: relative;
}

.chat-input {
  width: 100%;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 0.6rem;
  padding: 0.75rem 1rem;
  font-family: monospace;
  font-size: 0.85rem;
  color: #e2e8f0;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}

.chat-input:focus-visible {
  border-color: rgba(99, 102, 241, 0.4);
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

.chat-input::placeholder { color: #475569; }
.chat-input:disabled { opacity: 0.5; }

/* ── Analysis ── */
.analysis-card {
  background: rgba(20, 20, 40, 0.8);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 0.75rem;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.analysis-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.analysis-item {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.analysis-item--wide {
  grid-column: 1 / -1;
}

.analysis-label {
  font-size: 0.6rem;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: #475569;
}

.analysis-value {
  font-size: 0.88rem;
  color: #cbd5e1;
  text-transform: capitalize;
}

.readiness-bar {
  height: 4px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 0.25rem;
}

.readiness-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.8s ease;
}

.readiness-num {
  font-size: 0.72rem;
  color: #64748b;
}

.game-btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 0.5rem;
  color: #0f0f1a;
  font-size: 0.9rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
  align-self: center;
}

.game-btn:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}
.game-btn:focus-visible {
  outline: 2px solid rgba(99, 102, 241, 0.7);
  outline-offset: 3px;
}

.not-ready {
  font-size: 0.82rem;
  color: #475569;
  margin: 0;
  text-align: center;
  font-style: italic;
}

/* ── Slide-up transition ── */
.slide-up-enter-active { transition: all 0.6s ease-out; }
.slide-up-leave-active { transition: all 0.3s ease-in; }
.slide-up-enter-from { opacity: 0; transform: translateY(20px); }
.slide-up-leave-to { opacity: 0; transform: translateY(10px); }

/* ── Mobile ── */
@media (max-width: 480px) {
  .intake-wrap { padding: 1.5rem 0.75rem 3rem; }
  .chat-thread { height: 300px; }
  .analysis-grid { grid-template-columns: 1fr; }
}
</style>
