<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { RouterLink } from 'vue-router'
import { useAuthStore } from '@/composables/useAuthStore'

const props = defineProps<{
  coherence: number
  syncCount: number
  sessionDuration: number
  dominantPhase: string
}>()

const emit = defineEmits<{ close: [] }>()

const { apiFetch, isAuthenticated } = useAuthStore()

const visible = ref(false)
const submitting = ref(false)
const finished = ref(false)
const showJournalBridge = ref(false)
const selectedValue = ref<number | null>(null)
const transitioning = ref(false)

interface NextItem {
  item_id: string
  instrument: string
  text: string
  scale: string
  options: string[] | null
  connector_affinity: string
  progress: { answered: number; core_total: number }
}

const items = ref<NextItem[]>([])
const currentIdx = ref(0)
const connectorData = ref<Record<string, unknown> | null>(null)
const pickedConnector = ref<string>('spotify')

const currentItem = computed(() => items.value[currentIdx.value] ?? null)
const totalItems = computed(() => items.value.length)

// ── Connector round-robin ────────────────────────────────────────
const CONNECTOR_KEY = 'cz-last-reflect-connector'
const CONNECTORS = ['spotify', 'strava']

function pickConnector(): string {
  const last = localStorage.getItem(CONNECTOR_KEY)
  const idx = last ? (CONNECTORS.indexOf(last) + 1) % CONNECTORS.length : 0
  const pick = CONNECTORS[idx]
  localStorage.setItem(CONNECTOR_KEY, pick)
  return pick
}

// ── Trance summary line ─────────────────────────────────────────
const tranceLine = computed(() => {
  const mins = Math.floor(props.sessionDuration / 60000)
  const secs = Math.floor((props.sessionDuration % 60000) / 1000)
  const time = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
  return `coherence ${Math.round(props.coherence)} · ${time} · ${props.dominantPhase}`
})

// ── Spotify data cards ──────────────────────────────────────────
const spotifyStats = computed(() => {
  if (!connectorData.value || pickedConnector.value !== 'spotify') return []
  const d = connectorData.value as any
  const stats: { label: string; value: string }[] = []

  if (d.genres?.length >= 2) {
    stats.push({ label: 'genres', value: `${d.genres[0]} · ${d.genres[1]}` })
  } else if (d.genres?.length === 1) {
    stats.push({ label: 'genre', value: d.genres[0] })
  }

  if (d.audio_avg?.valence != null) {
    const v = d.audio_avg.valence
    const mood = v < 0.3 ? 'melancholic' : v < 0.6 ? 'bittersweet' : 'luminous'
    stats.push({ label: 'valence', value: `${(v * 100).toFixed(0)}% — ${mood}` })
  }

  if (d.top_artists?.length) {
    stats.push({ label: 'top artist', value: d.top_artists[0] })
  }

  return stats.slice(0, 3)
})

// ── Strava data cards ───────────────────────────────────────────
const stravaStats = computed(() => {
  if (!connectorData.value || pickedConnector.value !== 'strava') return []
  const d = connectorData.value as any
  const stats: { label: string; value: string }[] = []

  if (d.activity_types) {
    const entries = Object.entries(d.activity_types) as [string, number][]
    if (entries.length) {
      const [type, count] = entries.sort((a, b) => (b[1] as number) - (a[1] as number))[0]
      stats.push({ label: 'dominant', value: `${count} ${type.toLowerCase()}s` })
    }
  }

  if (d.total_distance_km) {
    stats.push({ label: 'distance', value: `${Math.round(d.total_distance_km)} km` })
  }

  if (d.avg_heartrate) {
    stats.push({
      label: 'heartrate',
      value: `HR ${Math.round(d.avg_heartrate)} bpm · coherence ${Math.round(props.coherence)}`,
    })
  }

  return stats.slice(0, 3)
})

const connectorStats = computed(() =>
  pickedConnector.value === 'spotify' ? spotifyStats.value : stravaStats.value
)

const connectorLabel = computed(() =>
  pickedConnector.value === 'spotify' ? '♫ Spotify' : '⚡ Strava'
)

// ── Likert helpers ──────────────────────────────────────────────
const likertMax = computed(() => {
  if (!currentItem.value) return 5
  return currentItem.value.scale === 'likert_7' ? 7 : 5
})

// ── Fetch & init ────────────────────────────────────────────────
onMounted(async () => {
  // Guest users: show acquisition card immediately, skip API calls
  if (!isAuthenticated.value) {
    setTimeout(() => { visible.value = true }, 100)
    return
  }

  pickedConnector.value = pickConnector()

  const [itemsRes, profileRes] = await Promise.allSettled([
    apiFetch<NextItem[]>(`/api/psychometrics/next-items?connector=${pickedConnector.value}&count=5`),
    apiFetch<Record<string, unknown> | null>(`/api/${pickedConnector.value}/profile`),
  ])

  if (itemsRes.status === 'fulfilled' && itemsRes.value?.length) {
    items.value = itemsRes.value
  }
  if (profileRes.status === 'fulfilled') connectorData.value = profileRes.value

  // If we have no data and no questions, don't show
  if (!items.value.length && !connectorData.value) {
    emit('close')
    return
  }

  // Fade in
  setTimeout(() => { visible.value = true }, 100)
})

// ── Submit ──────────────────────────────────────────────────────
async function submit(value: number) {
  if (!currentItem.value || submitting.value) return
  submitting.value = true
  selectedValue.value = value
  try {
    await apiFetch('/api/psychometrics/microdose', {
      method: 'POST',
      body: JSON.stringify({
        item_id: currentItem.value.item_id,
        value,
        connector_context: pickedConnector.value,
        trance_coherence: props.coherence,
        session_duration_ms: props.sessionDuration,
      }),
    })

    if (currentIdx.value < totalItems.value - 1) {
      // Transition to next question
      transitioning.value = true
      setTimeout(() => {
        currentIdx.value++
        selectedValue.value = null
        submitting.value = false
        transitioning.value = false
      }, 400)
    } else {
      // Final question — show journal bridge, then auto-close
      showJournalBridge.value = true
      setTimeout(() => {
        finished.value = true
        setTimeout(() => emit('close'), 1200)
      }, 3500)
    }
  } catch {
    submitting.value = false
  }
}

function submitCategorical(index: number) {
  submit(index)
}

function handleBackdropClick(e: MouseEvent) {
  if ((e.target as HTMLElement).classList.contains('overlay-backdrop')) {
    emit('close')
  }
}
</script>

<template>
  <div
    class="overlay-backdrop fixed inset-0 z-50 flex items-center justify-center p-4"
    :class="visible ? 'opacity-100' : 'opacity-0'"
    style="transition: opacity 1.5s ease; background: rgba(0, 0, 0, 0.4)"
    @click="handleBackdropClick"
  >
    <div
      class="overlay-card relative w-full max-w-[400px] rounded-2xl border border-white/10 p-6 space-y-5"
      :class="finished ? 'opacity-0 translate-y-2' : 'opacity-100 translate-y-0'"
      style="
        background: rgba(15, 10, 25, 0.75);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        transition: opacity 1s ease, transform 1s ease;
      "
    >
      <!-- Close -->
      <button
        class="absolute top-3 right-3 text-gray-600 hover:text-gray-400 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/60 rounded"
        aria-label="Close"
        @click="emit('close')"
      >✕</button>

      <!-- Guest acquisition card -->
      <template v-if="!isAuthenticated">
        <div class="text-center space-y-5">
          <div class="text-xs text-gray-500 uppercase tracking-widest">{{ tranceLine }}</div>
          <p class="text-sm text-gray-300 leading-relaxed">
            Track your coherence over time.<br>Hear what your own data sounds like.
          </p>
          <RouterLink
            to="/login"
            class="block w-full py-2.5 px-4 rounded-xl text-sm font-medium bg-indigo-600/80 hover:bg-indigo-600 text-white transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
            @click="emit('close')"
          >
            Begin your practice
          </RouterLink>
          <button
            class="text-xs text-gray-600 hover:text-gray-400 transition-colors"
            @click="emit('close')"
          >
            Continue exploring
          </button>
        </div>
      </template>

      <!-- Authenticated: connector data + psychometrics -->
      <template v-else>

      <!-- Connector data -->
      <div v-if="connectorStats.length" class="space-y-1.5">
        <div class="text-xs uppercase tracking-widest text-gray-500">{{ connectorLabel }}</div>
        <div v-for="stat in connectorStats" :key="stat.label" class="flex justify-between text-sm">
          <span class="text-gray-500">{{ stat.label }}</span>
          <span class="text-gray-300">{{ stat.value }}</span>
        </div>
      </div>

      <!-- Trance line -->
      <div class="text-xs text-gray-600 text-center">{{ tranceLine }}</div>

      <!-- Journal bridge (shown after final question, auto-closes in 3.5s) -->
      <div v-if="showJournalBridge" class="text-center space-y-3 py-2">
        <p class="text-xs text-gray-500 tracking-widest uppercase">session complete</p>
        <RouterLink
          to="/journal?from=trance"
          class="block text-sm text-purple-300 hover:text-purple-200 transition-colors"
          @click="emit('close')"
        >write what came up &nbsp;→</RouterLink>
        <button
          class="text-xs text-gray-600 hover:text-gray-500 transition-colors"
          @click="emit('close')"
        >close</button>
      </div>

      <!-- Psychometric item (with fade transition) -->
      <div v-else-if="currentItem" class="space-y-4">
        <div
          :key="currentItem.item_id"
          class="question-fade"
          :class="transitioning ? 'opacity-0 translate-y-1' : 'opacity-100 translate-y-0'"
        >
          <p class="text-sm text-gray-200 leading-relaxed mb-4">{{ currentItem.text }}</p>

          <!-- Likert scale -->
          <div v-if="currentItem.scale !== 'categorical'" class="flex justify-center gap-1.5">
            <button
              v-for="n in likertMax"
              :key="n"
              class="w-9 h-9 rounded-lg text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/60"
              :class="
                selectedValue === n
                  ? 'bg-purple-600 text-white scale-110'
                  : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-gray-200'
              "
              :aria-label="`${n} out of ${likertMax}`"
              :disabled="submitting"
              @click="submit(n)"
            >{{ n }}</button>
          </div>

          <!-- Categorical options -->
          <div v-else class="space-y-1.5">
            <button
              v-for="(opt, idx) in currentItem.options"
              :key="opt"
              class="w-full py-2 px-3 rounded-lg text-sm text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-400/60"
              :class="
                selectedValue === idx
                  ? 'bg-purple-600 text-white'
                  : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-gray-200'
              "
              :disabled="submitting"
              @click="submitCategorical(idx)"
            >{{ opt }}</button>
          </div>
        </div>

        <!-- Mini-session progress (dots + counter) -->
        <div class="flex items-center justify-center gap-3">
          <div class="flex gap-1.5">
            <span
              v-for="i in totalItems"
              :key="i"
              class="w-1.5 h-1.5 rounded-full transition-all duration-300"
              :class="i - 1 < currentIdx ? 'bg-purple-500' : i - 1 === currentIdx ? 'bg-purple-400 scale-125' : 'bg-gray-700'"
            />
          </div>
          <span class="text-xs text-gray-600 tabular-nums">{{ currentIdx + 1 }} / {{ totalItems }}</span>
        </div>

        <!-- Overall pool progress -->
        <div v-if="currentItem.progress" class="flex items-center gap-2">
          <div class="flex-1 h-0.5 bg-gray-800 rounded-full overflow-hidden">
            <div
              class="h-full bg-purple-600/50 rounded-full transition-all duration-500"
              :style="{ width: `${((currentItem.progress.answered + currentIdx) / currentItem.progress.core_total) * 100}%` }"
            />
          </div>
          <span class="text-xs text-gray-600 tabular-nums">
            {{ currentItem.progress.answered + currentIdx }} / {{ currentItem.progress.core_total }}
          </span>
        </div>
      </div>

      <!-- Data-only mode (connector stats, no psychometric items) -->
      <div v-else-if="connectorStats.length" class="space-y-3">
        <p class="text-xs text-gray-600 text-center">reflect on your signal</p>
        <RouterLink
          to="/journal?from=trance"
          class="block text-sm text-center text-purple-300/70 hover:text-purple-300 transition-colors"
          @click="emit('close')"
        >write what came up &nbsp;→</RouterLink>
      </div>

      </template><!-- end authenticated -->
    </div>
  </div>
</template>

<style scoped>
.question-fade {
  transition: opacity 0.35s ease, transform 0.35s ease;
}
</style>
