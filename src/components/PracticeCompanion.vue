<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePracticeJourney } from '@/composables/usePracticeJourney'
import { useReflection, type Reading } from '@/composables/useReflection'
import { useTranceEngine } from '@/composables/useTranceEngine'
import { METHODS } from '@/data/practiceMethods'

/**
 * Follows a practice session into its tool. Shows a quiet pill (method + a way
 * back to reflect), and asks the method's "during" prompts: at phase changes in
 * Zeromind, or when the person taps "note" elsewhere. Answers are read for
 * sentiment and mirrored back in one line, then fade.
 */

const route = useRoute()
const router = useRouter()
const { pending, addDuring, markEnded } = usePracticeJourney()
const { reflect } = useReflection()
const { phase, sessionActive, tunnelPulseStrength } = useTranceEngine()

const method = computed(() => (pending.value ? METHODS[pending.value.method] : null))
const inTool = computed(() => !!method.value && route.path === method.value.route)
const ended = computed(() => !!pending.value?.sessionEndedAt)

// ── Prompt card ───────────────────────────────────────────────────
const prompt = ref<string | null>(null)
const answer = ref('')
const mirror = ref<Reading | null>(null)
let hideTimer: ReturnType<typeof setTimeout> | undefined
let promptIdx = 0

function clearTimer() {
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = undefined
}

function ask(text?: string) {
  if (!method.value) return
  const list = method.value.prompts.during
  prompt.value = text ?? list[promptIdx % list.length]
  promptIdx++
  answer.value = ''
  mirror.value = null
  clearTimer()
  // An unanswered prompt drifts away on its own — never a blocker.
  hideTimer = setTimeout(() => { prompt.value = null }, 25_000)
}

async function send() {
  const text = answer.value.trim()
  const p = prompt.value
  if (!text || !p || !pending.value) { prompt.value = null; return }
  prompt.value = null
  clearTimer()
  const reading = await reflect(
    { method: pending.value.method, moment: 'during', prompt: p, text },
    (local) => { mirror.value = local },
  )
  mirror.value = reading
  addDuring({ prompt: p, text, tone: reading.tone, valence: reading.valence })
  // A soft visual acknowledgement in the tunnel / zeromind visuals.
  tunnelPulseStrength.value = Math.max(tunnelPulseStrength.value, 0.6)
  hideTimer = setTimeout(() => { mirror.value = null }, reading.tone === 'unsafe' ? 30_000 : 9_000)
}

function skip() {
  prompt.value = null
  clearTimer()
}

// Zeromind: ask at the deeper phase changes, not at induction or wake.
watch(phase, (p) => {
  if (!inTool.value || !sessionActive.value) return
  if (p === 'coherence' || p === 'deepen' || p === 'joy') ask()
})

watch(inTool, (v) => { if (!v) { prompt.value = null; mirror.value = null } })

function goReflect() {
  markEnded()
  router.push('/practice')
}

onUnmounted(clearTimer)
</script>

<template>
  <div v-if="pending && method && route.path !== '/practice'" class="companion" aria-live="polite">
    <Transition name="drift">
      <form v-if="prompt" class="card" @submit.prevent="send">
        <p class="card-prompt">{{ prompt }}</p>
        <input
          v-model="answer"
          class="card-input"
          maxlength="300"
          placeholder="a word or two…"
          autocomplete="off"
          autofocus
        />
        <div class="card-row">
          <button type="button" class="link" @click="skip">let it pass</button>
          <button type="submit" class="link link--on" :disabled="!answer.trim()">offer</button>
        </div>
      </form>
    </Transition>

    <Transition name="drift">
      <p v-if="mirror && !prompt" class="mirror" :class="{ 'mirror--care': mirror.tone === 'unsafe' }">
        <span class="mirror-tone">{{ mirror.tone }}</span>
        {{ mirror.reflection }}
      </p>
    </Transition>

    <div class="pill">
      <span class="pill-dot" :class="{ 'pill-dot--done': ended }" aria-hidden="true" />
      <span class="pill-name">{{ method.name }}</span>
      <template v-if="inTool">
        <button v-if="!prompt" class="link" @click="ask()">note</button>
        <button class="link" :class="{ 'link--on': ended }" @click="goReflect">
          {{ ended ? 'reflect →' : 'done' }}
        </button>
      </template>
      <button v-else class="link" @click="router.push(method.route)">return</button>
    </div>
  </div>
</template>

<style scoped>
.companion {
  position: fixed;
  left: 16px;
  bottom: 16px;
  z-index: 60;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  max-width: min(340px, calc(100vw - 32px));
  pointer-events: none;
}
.companion > * { pointer-events: auto; }

.pill {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(10, 10, 14, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(12px);
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(226, 232, 240, 0.6);
}
.pill-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(167, 139, 250, 0.7);
  animation: breathe 6s ease-in-out infinite;
}
.pill-dot--done { background: rgba(52, 211, 153, 0.8); animation: none; }
.pill-name { text-transform: lowercase; }

.card, .mirror {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(10, 10, 14, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(14px);
  color: #e2e8f0;
}
.card { width: 100%; }
.card-prompt { font-size: 13px; font-weight: 300; margin-bottom: 8px; color: rgba(226, 232, 240, 0.85); }
.card-input {
  width: 100%;
  background: transparent;
  border: none;
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
  padding: 4px 0;
  font-size: 14px;
  color: #e2e8f0;
  outline: none;
}
.card-input:focus { border-bottom-color: rgba(167, 139, 250, 0.6); }
.card-row { display: flex; justify-content: space-between; margin-top: 8px; }

.mirror { font-size: 12.5px; line-height: 1.5; font-weight: 300; color: rgba(226, 232, 240, 0.8); }
.mirror--care { border-color: rgba(251, 191, 36, 0.4); }
.mirror-tone {
  display: block;
  font-size: 9px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: rgba(167, 139, 250, 0.8);
  margin-bottom: 4px;
}

.link {
  background: none;
  border: none;
  padding: 0;
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(226, 232, 240, 0.4);
  cursor: pointer;
}
.link:hover { color: rgba(226, 232, 240, 0.8); }
.link:disabled { opacity: 0.3; cursor: default; }
.link--on { color: rgba(167, 139, 250, 0.9); }

@keyframes breathe { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
.drift-enter-active, .drift-leave-active { transition: opacity 0.6s ease, transform 0.6s ease; }
.drift-enter-from, .drift-leave-to { opacity: 0; transform: translateY(6px); }
</style>
