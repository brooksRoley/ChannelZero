<template>
  <div class="min-h-screen result-bg text-gray-100 relative">

    <!-- Section 1: Hero — full-viewport physics canvas + title -->
    <section
      ref="heroRef"
      class="relative h-screen w-full flex items-center justify-center overflow-hidden"
    >
      <canvas
        ref="canvasRef"
        class="absolute inset-0 w-full h-full transition-opacity duration-700 cursor-crosshair"
        :style="{ opacity: canvasOpacity }"
        @click="onCanvasClick"
      />
      <div class="relative z-10 text-center pointer-events-none select-none">
        <h1
          class="text-6xl sm:text-7xl md:text-8xl font-black tracking-tight mb-3"
          :style="{ color: cfg?.color }"
        >{{ cfg?.label }}</h1>
        <p class="text-lg sm:text-xl font-mono text-gray-400 tracking-widest uppercase">{{ cfg?.subtitle }}</p>
      </div>
      <!-- Scroll indicator -->
      <div class="absolute bottom-8 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center gap-2 opacity-60">
        <span class="text-xs text-gray-500 uppercase tracking-widest">Scroll</span>
        <div class="w-px h-8 bg-gradient-to-b from-gray-500 to-transparent animate-pulse" />
      </div>
    </section>

    <!-- Section 2: The Read — LLM Narrative -->
    <section class="relative max-w-3xl mx-auto px-6 py-24">
      <h2 class="text-xs uppercase tracking-[0.3em] text-gray-600 mb-10 font-mono">The Read</h2>
      <div v-if="narrativeLoading" class="space-y-4 animate-pulse">
        <div class="h-4 bg-gray-800 rounded w-full" />
        <div class="h-4 bg-gray-800 rounded w-5/6" />
        <div class="h-4 bg-gray-800 rounded w-4/5" />
        <div class="h-4 bg-gray-800 rounded w-full" />
        <div class="h-4 bg-gray-800 rounded w-3/4" />
      </div>
      <div v-else-if="narrativeError" class="text-gray-600 font-mono text-sm space-y-4">
        <p>{{ narrativeErrorMsg }}</p>
        <!-- Rate-limit: auto-retry countdown + manual retry -->
        <div v-if="narrativeIsRateLimited" class="flex items-center gap-3">
          <button
            @click="retryNarrative"
            class="text-xs font-mono px-4 py-2 rounded-full border transition-colors"
            :style="{ borderColor: cfg?.color + '60', color: cfg?.color }"
          >Retry now</button>
          <span v-if="narrativeRetryIn > 0" class="text-xs text-gray-700 font-mono">
            auto in {{ narrativeRetryIn }}s
          </span>
        </div>
        <button
          v-if="hasSyncEndpoint && narrativeErrorMsg.includes('No data')"
          :disabled="syncing"
          @click="syncProvider"
          class="text-xs font-mono px-4 py-2 rounded-full border border-gray-700 hover:border-gray-500 hover:text-gray-300 transition-colors disabled:opacity-40 disabled:cursor-wait"
          :style="syncing ? {} : { borderColor: cfg?.color + '60', color: cfg?.color }"
        >
          {{ syncing ? 'Syncing…' : 'Resync from ' + (cfg?.label ?? 'provider') }}
        </button>
      </div>
      <div v-else class="space-y-6">
        <p
          v-for="(para, i) in narrativeParagraphs"
          :key="i"
          ref="narrativeRefs"
          class="text-gray-400 font-mono text-sm sm:text-base leading-relaxed opacity-0 transition-opacity duration-1000"
          :class="{ 'opacity-100': visibleNarratives.has(i) }"
        >{{ para }}</p>
      </div>
    </section>

    <!-- Section 3: Signal Data — Structured Cards -->
    <section class="relative max-w-4xl mx-auto px-6 py-24">
      <h2 class="text-xs uppercase tracking-[0.3em] text-gray-600 mb-10 font-mono">Signal Data</h2>

      <div v-if="profileLoading" class="grid grid-cols-2 sm:grid-cols-3 gap-6">
        <div v-for="n in 4" :key="n" class="bg-gray-900 rounded-2xl p-6 animate-pulse">
          <div class="h-8 bg-gray-800 rounded w-1/2 mb-3" />
          <div class="h-4 bg-gray-800 rounded w-3/4" />
        </div>
      </div>

      <div v-else-if="!profile" class="text-gray-600 font-mono text-sm space-y-4">
        <p>No data captured yet. Reconnect this provider to fetch fresh signal.</p>
        <button
          v-if="hasSyncEndpoint"
          :disabled="syncing"
          @click="syncProvider"
          class="text-xs font-mono px-4 py-2 rounded-full border border-gray-700 hover:border-gray-500 hover:text-gray-300 transition-colors disabled:opacity-40 disabled:cursor-wait"
          :style="syncing ? {} : { borderColor: cfg?.color + '60', color: cfg?.color }"
        >
          {{ syncing ? 'Syncing…' : 'Resync from ' + (cfg?.label ?? 'provider') }}
        </button>
      </div>
      <div v-else class="space-y-12">
        <!-- Hero stats — large number cards -->
        <div v-if="cfg?.heroStats.length" class="grid grid-cols-2 sm:grid-cols-3 gap-6">
          <div
            v-for="(stat, i) in cfg.heroStats"
            :key="stat.field"
            ref="statCardRefs"
            class="bg-gray-900/80 border border-gray-800 rounded-2xl p-6 opacity-0 translate-y-4 transition-all duration-700"
            :class="{ 'opacity-100 translate-y-0': visibleStats.has(i) }"
          >
            <div
              class="text-3xl sm:text-4xl font-black tabular-nums"
              :style="{ color: cfg.color }"
            >{{ animatedStatValues[i] ?? formatStat(resolveField(profile, stat.field), stat.format) }}</div>
            <div class="text-xs text-gray-500 uppercase tracking-wider mt-2">{{ stat.label }}</div>
            <!-- Bar for 0-1 values -->
            <div
              v-if="stat.format === 'percent' && isNormalized(resolveField(profile, stat.field))"
              class="mt-3 w-full bg-gray-800 rounded-full h-1.5"
            >
              <div
                class="h-1.5 rounded-full transition-all duration-1000"
                :style="{ width: (Number(resolveField(profile, stat.field)) * 100) + '%', backgroundColor: cfg.color }"
              />
            </div>
          </div>
        </div>

        <!-- Tag fields — pill lists -->
        <div v-for="tf in cfg?.tagFields" :key="tf.field" class="space-y-3">
          <p class="text-xs text-gray-500 uppercase tracking-wider font-mono">{{ tf.label }}</p>
          <div class="flex flex-wrap gap-2">
            <template v-if="Array.isArray(resolveField(profile, tf.field))">
              <span
                v-for="tag in (resolveField(profile, tf.field) as string[]).slice(0, 12)"
                :key="String(tag)"
                class="text-xs px-3 py-1.5 rounded-full border font-mono"
                :style="{
                  borderColor: cfg!.color + '60',
                  backgroundColor: cfg!.color + '18',
                  color: cfg!.color,
                }"
              >{{ tag }}</span>
            </template>
            <template v-else-if="typeof resolveField(profile, tf.field) === 'object' && resolveField(profile, tf.field) != null">
              <span
                v-for="(val, key) in (resolveField(profile, tf.field) as Record<string, unknown>)"
                :key="String(key)"
                class="text-xs px-3 py-1.5 rounded-full border font-mono"
                :style="{
                  borderColor: cfg!.color + '60',
                  backgroundColor: cfg!.color + '18',
                  color: cfg!.color,
                }"
              >{{ key }}: {{ val }}</span>
            </template>
            <template v-else-if="resolveField(profile, tf.field) != null">
              <span
                class="text-sm font-mono"
                :style="{ color: cfg!.color }"
              >{{ resolveField(profile, tf.field) }}</span>
            </template>
          </div>
        </div>
      </div>
    </section>

    <!-- Section 4: Raw Signal — Pretty JSON -->
    <section class="relative max-w-4xl mx-auto px-6 py-16">
      <button
        @click="rawExpanded = !rawExpanded"
        :aria-expanded="rawExpanded"
        aria-controls="raw-signal-content"
        class="flex items-center gap-3 text-xs uppercase tracking-[0.3em] text-gray-600 font-mono hover:text-gray-400 transition-colors"
      >
        <span class="transform transition-transform duration-300" :class="rawExpanded ? 'rotate-90' : ''">&#9654;</span>
        Raw Signal
      </button>
      <div
        id="raw-signal-content"
        v-if="rawExpanded && profile"
        class="mt-6 bg-gray-900/60 border border-gray-800 rounded-2xl p-6 overflow-x-auto"
      >
        <pre class="text-xs font-mono leading-relaxed"><code v-html="syntaxHighlight(profile)" /></pre>
      </div>
    </section>

    <!-- Section 5: Cross-Signal Correlations -->
    <section class="relative max-w-4xl mx-auto px-6 py-24 pb-32">
      <h2 class="text-xs uppercase tracking-[0.3em] text-gray-600 mb-10 font-mono">Cross-Signal Correlations</h2>

      <div v-if="correlationsLoading" class="space-y-4 animate-pulse">
        <div class="h-20 bg-gray-900 rounded-2xl" />
        <div class="h-20 bg-gray-900 rounded-2xl" />
      </div>

      <div v-else-if="!correlations.length" class="text-center py-12">
        <p class="text-gray-600 font-mono text-sm">
          {{ !llmAvailable ? 'Cross-signal analysis requires an LLM key on the server.' : 'Connect more services to see correlations.' }}
        </p>
      </div>

      <div v-else class="space-y-4">
        <div
          v-for="(corr, i) in correlations"
          :key="i"
          class="bg-gray-900/60 border border-gray-800 rounded-2xl p-5 flex flex-col sm:flex-row sm:items-center gap-4"
        >
          <div class="flex items-center gap-2">
            <span
              class="text-xs font-bold px-2.5 py-1 rounded-full"
              :style="{ backgroundColor: providerColor(corr.source.provider) + '20', color: providerColor(corr.source.provider) }"
            >{{ corr.source.label || corr.source.provider }}</span>
            <span class="text-gray-600 text-xs font-mono">{{ corr.source.field }}: {{ corr.source.value }}</span>
          </div>

          <span class="text-gray-700 text-lg hidden sm:block">&#8596;</span>

          <div class="flex items-center gap-2">
            <span
              class="text-xs font-bold px-2.5 py-1 rounded-full"
              :style="{ backgroundColor: providerColor(corr.target.provider) + '20', color: providerColor(corr.target.provider) }"
            >{{ corr.target.label || corr.target.provider }}</span>
            <span class="text-gray-600 text-xs font-mono">{{ corr.target.field }}: {{ corr.target.value }}</span>
          </div>

          <p v-if="corr.explanation" class="text-xs text-gray-500 sm:ml-auto max-w-xs">{{ corr.explanation }}</p>
        </div>
      </div>
    </section>

    <!-- Section 6: Portrait CTA — shown when 2+ streams connected -->
    <section v-if="connectedCount >= 2" class="relative max-w-2xl mx-auto px-6 pb-32 text-center">
      <router-link
        to="/portrait"
        class="block rounded-2xl border border-indigo-400/40 bg-indigo-500/5 p-8 hover:bg-indigo-500/10 hover:border-indigo-400/60 transition-colors group"
      >
        <p class="text-xs uppercase tracking-[0.3em] text-indigo-400/60 font-mono mb-3">What it all means</p>
        <h3 class="text-2xl font-bold text-indigo-200 group-hover:text-white transition-colors mb-2">Your Portrait</h3>
        <p class="text-sm text-gray-500 font-mono">One synthesized reading across all your connected data. Your full self, in signal.</p>
        <p class="mt-4 text-xs font-mono text-indigo-400/50 group-hover:text-indigo-400 transition-colors">Read it &rarr;</p>
      </router-link>
    </section>

    <!-- Back to calibrate link -->
    <div class="fixed bottom-6 left-6 z-20">
      <router-link
        to="/calibrate"
        class="text-xs font-mono text-gray-600 hover:text-gray-400 transition-colors flex items-center gap-1"
      >
        &#8592; Calibrate
      </router-link>
    </div>

    <!-- Audio controls -->
    <div v-if="synthHandle" class="fixed bottom-6 right-6 z-20 flex items-center gap-3">
      <input
        type="range"
        min="0"
        max="1"
        step="0.05"
        :value="audioVolume"
        @input="(e) => { audioVolume = Number((e.target as HTMLInputElement).value); synthHandle?.setVolume(audioVolume) }"
        aria-label="Volume"
        class="w-20 h-1 appearance-none bg-gray-700 rounded-full cursor-pointer accent-gray-500 opacity-60 hover:opacity-100 transition-opacity"
      />
      <button
        @click="synthHandle?.toggle()"
        :aria-label="synthHandle?.isStarted.value ? 'Mute audio' : 'Unmute audio'"
        class="w-9 h-9 flex items-center justify-center rounded-full border border-gray-700 bg-gray-900/80 text-gray-400 hover:text-gray-200 hover:border-gray-500 transition-colors text-xs font-mono"
      >
        <span v-if="synthHandle?.isStarted.value">&#9834;</span>
        <span v-else>&#9835;</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/composables/useAuthStore'
import { useVibeStore } from '@/composables/useVibeStore'
import { connectorConfigs, resolveField, profileEndpoint, analyzeEndpoint } from '@/config/connectorConfig'
import type { ProviderConfig } from '@/config/connectorConfig'
import type { OAuthState } from '@/composables/useVibeStore'
import { useDataDrivenPhysics } from '@/composables/useDataDrivenPhysics'
import { useSignalSynth, type AudioMetrics } from '@/composables/useSignalSynth'

const route = useRoute()
const router = useRouter()
const { apiFetch } = useAuthStore()
const { oauthState } = useVibeStore()

// ── Provider resolution ──────────────────────────────────────────────────────
const provider = computed(() => route.params.provider as string)
const cfg = computed<ProviderConfig | undefined>(() => connectorConfigs[provider.value])
const connectedCount = computed(() =>
  Object.values(oauthState.value).filter((v) => v?.connected).length
)

// ── Redirect guard ───────────────────────────────────────────────────────────
watch(provider, (p) => {
  if (!p || !connectorConfigs[p]) {
    router.replace('/calibrate')
    return
  }
  const state = oauthState.value[p as keyof OAuthState]
  if (!state?.connected) {
    router.replace('/calibrate')
  }
}, { immediate: true })

// ── Physics ──────────────────────────────────────────────────────────────────
const canvasRef = ref<HTMLCanvasElement>()
const heroRef = ref<HTMLElement>()
const canvasOpacity = ref(1)

const cosmicHandle = shallowRef<ReturnType<typeof useDataDrivenPhysics> | null>(null)
const synthHandle = shallowRef<ReturnType<typeof useSignalSynth> | null>(null)

// ── Profile data ─────────────────────────────────────────────────────────────
const profile = ref<Record<string, unknown> | null>(null)
const profileLoading = ref(false)

// ── Narrative ────────────────────────────────────────────────────────────────
const narrative = ref('')
const narrativeLoading = ref(false)
const narrativeError = ref(false)
const narrativeErrorMsg = ref('Analysis not available yet.')
const narrativeIsRateLimited = ref(false)
const narrativeRetryIn = ref(0)
let _retryTimer: ReturnType<typeof setInterval> | null = null
const narrativeParagraphs = computed(() =>
  narrative.value.split(/\n\n+/).filter(p => p.trim())
)
const narrativeRefs = ref<HTMLElement[]>([])
const visibleNarratives = ref(new Set<number>())

// ── Stats animation ──────────────────────────────────────────────────────────
const statCardRefs = ref<HTMLElement[]>([])
const visibleStats = ref(new Set<number>())
const animatedStatValues = ref<Record<number, string>>({})

// ── Resync ───────────────────────────────────────────────────────────────────
const syncing = ref(false)
const syncEndpoints: Record<string, string> = { spotify: '/api/spotify/sync' }
const hasSyncEndpoint = computed(() => provider.value in syncEndpoints)

async function syncProvider() {
  const endpoint = syncEndpoints[provider.value]
  if (!endpoint || syncing.value) return
  syncing.value = true
  try {
    await apiFetch(endpoint, { method: 'POST' })
    // Re-fetch everything after successful sync
    await fetchProfile()
    narrativeError.value = false
    narrativeErrorMsg.value = 'Analysis not available yet.'
    fetchNarrative()
    fetchCorrelations()
    observeElements()
  } catch (e: any) {
    const msg = String(e?.message || '')
    if (msg.includes('404')) {
      narrativeError.value = true
      narrativeErrorMsg.value = 'No tokens stored — please reconnect on /calibrate.'
    }
  }
  syncing.value = false
}

// ── Raw JSON ─────────────────────────────────────────────────────────────────
const rawExpanded = ref(false)

// ── Audio controls ──────────────────────────────────────────────────────────
const audioVolume = ref(0.7)

// ── Correlations ─────────────────────────────────────────────────────────────
interface CorrelationEndpoint {
  provider: string
  field: string
  value: unknown
  label: string
}
interface Correlation {
  source: CorrelationEndpoint
  target: CorrelationEndpoint
  explanation: string
}
const correlations = ref<Correlation[]>([])
const correlationsLoading = ref(false)
const llmAvailable = ref(true)

// ── Helpers ──────────────────────────────────────────────────────────────────
function isNormalized(val: unknown): boolean {
  return typeof val === 'number' && val >= 0 && val <= 1
}

function formatStat(val: unknown, format: 'decimal' | 'integer' | 'percent'): string {
  if (val == null) return '--'
  const n = Number(val)
  if (isNaN(n)) return String(val)
  if (format === 'percent') return isNormalized(val) ? (n * 100).toFixed(0) + '%' : n.toFixed(0) + '%'
  if (format === 'integer') return Math.round(n).toLocaleString()
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function providerColor(p: string): string {
  return connectorConfigs[p]?.color ?? '#888'
}

function syntaxHighlight(obj: unknown): string {
  const json = JSON.stringify(obj, null, 2)
  return json.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      let cls = 'text-amber-400' // number
      if (/^"/.test(match)) {
        cls = /:$/.test(match) ? 'text-purple-400' : 'text-green-400' // key : string
      } else if (/true|false/.test(match)) {
        cls = 'text-blue-400'
      } else if (/null/.test(match)) {
        cls = 'text-gray-600'
      }
      return `<span class="${cls}">${match}</span>`
    }
  )
}

// ── Animate count-up ─────────────────────────────────────────────────────────
function animateCountUp(index: number, targetVal: unknown, format: 'decimal' | 'integer' | 'percent') {
  const n = Number(targetVal)
  if (isNaN(n) || targetVal == null) {
    animatedStatValues.value[index] = formatStat(targetVal, format)
    return
  }
  const duration = 1200
  const start = performance.now()
  function tick(now: number) {
    const elapsed = now - start
    const progress = Math.min(elapsed / duration, 1)
    const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic
    const current = n * eased
    if (format === 'percent' && isNormalized(targetVal)) {
      animatedStatValues.value[index] = (current * 100).toFixed(0) + '%'
    } else if (format === 'integer') {
      animatedStatValues.value[index] = Math.round(current).toLocaleString()
    } else {
      animatedStatValues.value[index] = current.toLocaleString(undefined, { maximumFractionDigits: 2 })
    }
    if (progress < 1) requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}

// ── Intersection observers ───────────────────────────────────────────────────
let narrativeObserver: IntersectionObserver | null = null
let statObserver: IntersectionObserver | null = null

function setupObservers() {
  // Narrative paragraphs
  narrativeObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          const idx = narrativeRefs.value.indexOf(entry.target as HTMLElement)
          if (idx >= 0) visibleNarratives.value.add(idx)
        }
      }
    },
    { threshold: 0.2 }
  )

  // Stat cards
  statObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          const idx = statCardRefs.value.indexOf(entry.target as HTMLElement)
          if (idx >= 0 && !visibleStats.value.has(idx)) {
            visibleStats.value.add(idx)
            // Trigger count-up animation
            const c = cfg.value
            if (c && profile.value) {
              const stat = c.heroStats[idx]
              if (stat) animateCountUp(idx, resolveField(profile.value, stat.field), stat.format)
            }
          }
        }
      }
    },
    { threshold: 0.3 }
  )
}

function observeElements() {
  nextTick(() => {
    if (narrativeObserver) {
      for (const el of narrativeRefs.value) {
        if (el) narrativeObserver.observe(el)
      }
    }
    if (statObserver) {
      for (const el of statCardRefs.value) {
        if (el) statObserver.observe(el)
      }
    }
  })
}

// ── Scroll parallax ──────────────────────────────────────────────────────────
function onScroll() {
  if (!heroRef.value) return
  const rect = heroRef.value.getBoundingClientRect()
  const scrolled = -rect.top / rect.height
  canvasOpacity.value = Math.max(0.15, 1 - scrolled * 1.2)

  // Fade audio volume with scroll
  if (synthHandle.value?.isStarted.value) {
    const volumeFade = Math.max(0.05, 1 - scrolled * 0.8)
    synthHandle.value.setVolume(audioVolume.value * volumeFade)
  }
}

// ── Mouse → audio coupling ──────────────────────────────────────────────────
let lastMouseX = 0
let lastMouseY = 0
let lastMouseTime = 0

function onMouseMoveAudio(e: MouseEvent) {
  if (!synthHandle.value?.isStarted.value) return

  const now = performance.now()
  const W = window.innerWidth

  // Pan based on X position
  synthHandle.value.setPan(((e.clientX / W) * 2 - 1) * 0.6)

  // Velocity → resonance spike
  if (lastMouseTime > 0) {
    const dt = Math.max(1, now - lastMouseTime)
    const dx = e.clientX - lastMouseX
    const dy = e.clientY - lastMouseY
    const velocity = Math.sqrt(dx * dx + dy * dy) / dt
    if (velocity > 1.5) {
      synthHandle.value.spikeResonance(Math.min(1, velocity / 5))
    }
  }

  lastMouseX = e.clientX
  lastMouseY = e.clientY
  lastMouseTime = now
}

function onCanvasClick(e: MouseEvent) {
  synthHandle.value?.triggerHit()
  if (canvasRef.value) {
    const rect = canvasRef.value.getBoundingClientRect()
    cosmicHandle.value?.clickImpulse(e.clientX - rect.left, e.clientY - rect.top)
  }
}

// ── Data fetching ────────────────────────────────────────────────────────────
async function fetchProfile() {
  if (!provider.value || !cfg.value) return
  profileLoading.value = true
  try {
    profile.value = await apiFetch<Record<string, unknown>>(profileEndpoint(provider.value))
  } catch {
    profile.value = null
  }
  profileLoading.value = false
}

function retryNarrative() {
  if (_retryTimer) { clearInterval(_retryTimer); _retryTimer = null }
  fetchNarrative()
}

function startRetryCountdown(seconds = 15) {
  narrativeRetryIn.value = seconds
  if (_retryTimer) clearInterval(_retryTimer)
  _retryTimer = setInterval(() => {
    narrativeRetryIn.value -= 1
    if (narrativeRetryIn.value <= 0) {
      if (_retryTimer) clearInterval(_retryTimer)
      _retryTimer = null
      fetchNarrative()
    }
  }, 1000)
}

async function fetchNarrative() {
  if (!provider.value || !cfg.value) return
  if (!llmAvailable.value) {
    narrativeError.value = true
    narrativeErrorMsg.value = 'Narrative engine offline — LLM not configured on the server.'
    return
  }
  narrativeLoading.value = true
  narrativeError.value = false
  narrativeIsRateLimited.value = false
  if (_retryTimer) { clearInterval(_retryTimer); _retryTimer = null }
  try {
    const data = await apiFetch<{ narrative: string }>(analyzeEndpoint(provider.value))
    narrative.value = data.narrative || ''
  } catch (e: any) {
    narrativeError.value = true
    const msg = String(e?.message || '')
    if (msg.includes('429')) {
      narrativeIsRateLimited.value = true
      narrativeErrorMsg.value = 'The analysis engine is busy — auto-retrying shortly.'
      startRetryCountdown(15)
    } else if (msg.includes('404')) {
      narrativeErrorMsg.value = 'No data captured yet — try reconnecting this provider.'
    } else if (msg.includes('503')) {
      narrativeErrorMsg.value = 'Narrative engine offline — LLM unavailable or not configured.'
    } else if (msg.includes('502')) {
      narrativeErrorMsg.value = 'Narrative engine returned an error. Try again in a moment.'
    } else {
      narrativeErrorMsg.value = 'Analysis not available yet.'
    }
  }
  narrativeLoading.value = false
}

async function fetchCorrelations() {
  if (!provider.value) return
  if (!llmAvailable.value) {
    correlations.value = []
    return
  }
  correlationsLoading.value = true
  try {
    const data = await apiFetch<Correlation[]>(
      `/api/connectors/correlations?provider=${provider.value}`
    )
    correlations.value = Array.isArray(data) ? data : []
  } catch {
    correlations.value = []
  }
  correlationsLoading.value = false
}

// ── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(async () => {
  window.addEventListener('scroll', onScroll, { passive: true })
  setupObservers()

  // Init physics canvas with placeholder colors
  if (canvasRef.value && cfg.value) {
    cosmicHandle.value = useDataDrivenPhysics(canvasRef, null, cfg.value.physics, cfg.value.color)
    await cosmicHandle.value.init()
  }

  // Check LLM availability
  try {
    const avail = await apiFetch<{ providers: Record<string, boolean>; llm: boolean }>('/api/connectors/available')
    llmAvailable.value = avail.llm
  } catch { /* assume available */ }

  // Fetch profile, then re-init physics + synth with real data
  await fetchProfile()

  if (profile.value && canvasRef.value && cfg.value) {
    cosmicHandle.value?.destroy()
    cosmicHandle.value = useDataDrivenPhysics(canvasRef, profile.value, cfg.value.physics, cfg.value.color)
    await cosmicHandle.value.init()

    // Init audio synth from profile
    const audio = profile.value.audio_avg as Record<string, number> | undefined
    if (audio) {
      synthHandle.value = useSignalSynth({
        tempo: audio.tempo ?? 120,
        energy: audio.energy ?? 0.5,
        valence: audio.valence ?? 0.5,
        danceability: audio.danceability ?? 0.5,
        acousticness: audio.acousticness ?? 0.5,
      })
    }
  }

  window.addEventListener('mousemove', onMouseMoveAudio)

  fetchNarrative()
  fetchCorrelations()

  // After profile loads, observe stat cards and narrative paragraphs
  observeElements()
})

// Re-observe when narrativeParagraphs change
watch(narrativeParagraphs, () => {
  nextTick(() => observeElements())
})

watch(profile, () => {
  nextTick(() => observeElements())
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('mousemove', onMouseMoveAudio)
  synthHandle.value?.dispose()
  cosmicHandle.value?.destroy()
  narrativeObserver?.disconnect()
  statObserver?.disconnect()
  if (_retryTimer) clearInterval(_retryTimer)
})
</script>

<style scoped>
.result-bg { background: #08060e; }

button:focus-visible,
input[type="range"]:focus-visible {
  outline: 2px solid rgba(99, 102, 241, 0.8);
  outline-offset: 2px;
  border-radius: 4px;
}
</style>
