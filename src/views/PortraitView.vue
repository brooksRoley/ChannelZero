<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useAuthStore } from '@/composables/useAuthStore'
import PortraitSection from '@/components/portrait/PortraitSection.vue'

interface PortraitSectionData {
  title: string
  body: string
  providers: string[]
}

interface Portrait {
  headline: string
  sections: PortraitSectionData[]
  throughline: string
}

type PortraitState = 'ready' | 'stale' | 'empty' | 'insufficient_providers' | 'no_llm'

interface PortraitStatus {
  status: PortraitState
  portrait: Portrait | null
  generated_at: string | null
  source_providers: string[]
  connected_providers: string[]
  llm_available: boolean
}

const { apiFetch } = useAuthStore()

const loading = ref(true)
const generating = ref(false)
const error = ref('')
const status = ref<PortraitStatus | null>(null)

const portrait = computed(() => status.value?.portrait ?? null)
const state = computed<PortraitState | null>(() => status.value?.status ?? null)
const connectedCount = computed(() => status.value?.connected_providers.length ?? 0)

const generatedAgo = computed(() => {
  const ts = status.value?.generated_at
  if (!ts) return ''
  const days = Math.floor((Date.now() - new Date(ts).getTime()) / 86_400_000)
  if (days <= 0) return 'today'
  return days === 1 ? 'yesterday' : `${days} days ago`
})

const staleReason = computed(() => {
  if (!status.value) return ''
  const src = new Set(status.value.source_providers)
  const now = new Set(status.value.connected_providers)
  const added = [...now].filter((p) => !src.has(p))
  const removed = [...src].filter((p) => !now.has(p))
  if (added.length) return `you connected ${added.join(', ')} since it was written`
  if (removed.length) return `you disconnected ${removed.join(', ')} since it was written`
  return `it was written ${generatedAgo.value}`
})

// Patience UI — generation runs 30-90s
const sittingPhrases = [
  'Sitting for your portrait…',
  'Reading across your streams…',
  'Finding the pattern beneath the patterns…',
  'Weaving the threads together…',
  'Almost — holding the likeness steady…',
]
const phraseIdx = ref(0)
let phraseTimer: ReturnType<typeof setInterval> | null = null

async function fetchStatus() {
  loading.value = true
  error.value = ''
  try {
    status.value = await apiFetch<PortraitStatus>('/api/portrait')
  } catch (e: any) {
    error.value = e.message || 'Could not reach the portrait engine.'
  } finally {
    loading.value = false
  }
}

async function generate() {
  if (generating.value) return
  generating.value = true
  error.value = ''
  phraseIdx.value = 0
  phraseTimer = setInterval(() => {
    phraseIdx.value = (phraseIdx.value + 1) % sittingPhrases.length
  }, 8000)
  try {
    const res = await apiFetch<{ portrait: Portrait; generated_at: string; source_providers: string[] }>(
      '/api/portrait/generate',
      { method: 'POST' },
    )
    status.value = {
      status: 'ready',
      portrait: res.portrait,
      generated_at: res.generated_at,
      source_providers: res.source_providers,
      connected_providers: status.value?.connected_providers ?? res.source_providers,
      llm_available: true,
    }
  } catch (e: any) {
    // A failed generation never clears an existing portrait
    error.value = e.message || 'Portrait generation failed — try again.'
  } finally {
    generating.value = false
    if (phraseTimer) clearInterval(phraseTimer)
    phraseTimer = null
  }
}

onMounted(fetchStatus)
onUnmounted(() => {
  if (phraseTimer) clearInterval(phraseTimer)
})
</script>

<template>
  <div class="min-h-screen calibrate-bg text-gray-100">
    <div class="max-w-3xl mx-auto px-6 py-20 sm:py-24">
      <header class="mb-14">
        <h1 class="text-4xl sm:text-5xl font-black tracking-tight mb-3">Integrated Portrait</h1>
        <p class="text-sm font-mono text-gray-500 tracking-wide">
          One reading across everything you chose to share — a mirror earned from your own data.
        </p>
      </header>

      <!-- Initial load -->
      <div v-if="loading" class="space-y-4 animate-pulse" aria-busy="true">
        <div class="h-4 bg-gray-800 rounded w-full" />
        <div class="h-4 bg-gray-800 rounded w-5/6" />
        <div class="h-4 bg-gray-800 rounded w-4/5" />
      </div>

      <!-- Generating -->
      <div v-else-if="generating" class="py-16 text-center space-y-6" role="status" aria-busy="true">
        <div class="mx-auto w-10 h-10 rounded-full border-2 border-gray-700 border-t-indigo-400 animate-spin" />
        <p class="text-gray-400 font-mono text-sm">{{ sittingPhrases[phraseIdx] }}</p>
        <p class="text-gray-600 font-mono text-xs">This takes a minute — the whole of you is a lot to read.</p>
      </div>

      <template v-else>
        <!-- Not enough streams -->
        <div v-if="state === 'insufficient_providers'" class="py-12 space-y-6">
          <p class="text-gray-400 font-mono text-sm leading-relaxed">
            A portrait needs at least two connected streams to read across.
            {{ connectedCount === 1 ? 'You have one connected — one more and the weaving can begin.' : 'Connect a couple of sources and come back.' }}
          </p>
          <RouterLink
            to="/calibrate"
            class="inline-block text-xs font-mono px-5 py-2.5 rounded-full border border-indigo-400/50 text-indigo-300 hover:bg-indigo-400/10 transition-colors"
          >Connect your signal sources</RouterLink>
        </div>

        <!-- LLM offline -->
        <div v-else-if="state === 'no_llm' && !portrait" class="py-12">
          <p class="text-gray-500 font-mono text-sm leading-relaxed">
            The narrative engine is resting. Your streams are connected and waiting —
            the portrait will be available once the engine returns.
          </p>
        </div>

        <!-- Ready to generate -->
        <div v-else-if="state === 'empty'" class="py-12 space-y-6">
          <p class="text-gray-400 font-mono text-sm leading-relaxed">
            {{ connectedCount }} streams connected. Your portrait hasn't been written yet.
          </p>
          <button
            @click="generate"
            class="text-sm font-mono px-6 py-3 rounded-full border border-indigo-400/50 text-indigo-300 hover:bg-indigo-400/10 active:scale-95 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
          >Sit for your portrait</button>
        </div>

        <!-- Portrait (ready / stale / no_llm-with-stored) -->
        <div v-else-if="portrait" class="space-y-14">
          <div
            v-if="state === 'stale'"
            class="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 rounded-xl border border-amber-400/30 bg-amber-400/5"
          >
            <p class="text-amber-300/90 font-mono text-xs leading-relaxed flex-1 min-w-[12rem]">
              Your data has shifted since this was written — {{ staleReason }}.
            </p>
            <button
              @click="generate"
              class="text-xs font-mono px-4 py-2 rounded-full border border-amber-400/50 text-amber-300 hover:bg-amber-400/10 active:scale-95 transition-all shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/60"
            >Re-sit</button>
          </div>

          <blockquote class="text-2xl sm:text-3xl font-bold tracking-tight text-gray-100 leading-snug border-l-2 border-indigo-400/60 pl-5">
            {{ portrait.headline }}
          </blockquote>

          <PortraitSection
            v-for="(section, i) in portrait.sections"
            :key="i"
            :title="section.title"
            :body="section.body"
            :providers="section.providers"
          />

          <div class="pt-6 border-t border-gray-800 space-y-4">
            <p class="text-xs uppercase tracking-[0.3em] text-gray-600 font-mono">Throughline</p>
            <p class="text-gray-300 font-mono text-sm sm:text-base leading-relaxed italic whitespace-pre-line">
              {{ portrait.throughline }}
            </p>
          </div>

          <footer class="flex flex-wrap items-center gap-4 pt-2">
            <span class="text-xs font-mono text-gray-600">Written {{ generatedAgo }}</span>
            <button
              v-if="state === 'ready'"
              @click="generate"
              class="text-xs font-mono text-gray-600 hover:text-gray-400 underline underline-offset-4 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60 rounded"
            >re-sit for a new portrait</button>
          </footer>

          <!-- What's next — return hook at peak engagement; shown on ready and stale states -->
          <div v-if="state === 'ready' || state === 'stale'" class="pt-8 border-t border-gray-800 space-y-4">
            <p class="text-xs uppercase tracking-[0.3em] text-gray-600 font-mono">What's next</p>
            <div class="flex flex-wrap gap-3">
              <RouterLink
                to="/checkin"
                class="text-xs font-mono px-5 py-2.5 rounded-full border border-gray-700/60 text-gray-400 hover:border-indigo-400/50 hover:text-indigo-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
              >Daily check-in</RouterLink>
              <RouterLink
                to="/journal"
                class="text-xs font-mono px-5 py-2.5 rounded-full border border-gray-700/60 text-gray-400 hover:border-indigo-400/50 hover:text-indigo-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400/60"
              >Open journal</RouterLink>
              <RouterLink
                to="/studio"
                class="text-xs font-mono px-5 py-2.5 rounded-full border border-gray-700/60 text-gray-400 hover:border-emerald-400/50 hover:text-emerald-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60"
              >Glass Studio</RouterLink>
              <RouterLink
                to="/"
                class="text-xs font-mono px-5 py-2.5 rounded-full border border-gray-700/60 text-gray-400 hover:border-gray-500/60 hover:text-gray-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-500/60"
              >Return home</RouterLink>
            </div>
          </div>
        </div>
      </template>

      <p v-if="error" class="text-red-400 text-xs mt-8 font-mono italic">{{ error }}</p>
    </div>
  </div>
</template>
