<template>
  <div class="relative group w-full">
    <div
      class="absolute -inset-0.5 bg-gradient-to-r from-indigo-600/40 to-purple-900/40 rounded-xl blur opacity-30 group-hover:opacity-70 transition duration-500"
    ></div>

    <button
      @click="showModal = true"
      :disabled="isConnecting || isConnected"
      class="relative flex items-center justify-between w-full bg-black border border-gray-800 text-gray-200 px-6 py-4 rounded-xl shadow-2xl transition-all overflow-hidden"
      :class="{ 'opacity-50 cursor-not-allowed': isConnecting, 'border-indigo-500/50': isConnected }"
    >
      <div class="flex items-center gap-4 z-10">
        <svg viewBox="0 0 24 24" aria-hidden="true" class="w-6 h-6">
          <circle cx="12" cy="12" r="3" fill="#a78bfa" />
          <circle cx="12" cy="12" r="7" stroke="#a78bfa" stroke-width="0.75" fill="none" opacity="0.6" />
          <circle cx="12" cy="12" r="11" stroke="#a78bfa" stroke-width="0.5" fill="none" opacity="0.3" />
          <line x1="12" y1="1" x2="12" y2="4" stroke="#a78bfa" stroke-width="0.75" opacity="0.5" />
          <line x1="12" y1="20" x2="12" y2="23" stroke="#a78bfa" stroke-width="0.75" opacity="0.5" />
          <line x1="1" y1="12" x2="4" y2="12" stroke="#a78bfa" stroke-width="0.75" opacity="0.5" />
          <line x1="20" y1="12" x2="23" y2="12" stroke="#a78bfa" stroke-width="0.75" opacity="0.5" />
        </svg>

        <div class="flex flex-col text-left">
          <span
            class="font-bold text-sm tracking-wide uppercase"
            :class="{ 'text-indigo-400': isConnected }"
          >
            {{ buttonText }}
          </span>
          <span v-if="!isConnected" class="text-xs text-gray-500 font-mono mt-0.5">
            Let us read your constellations.
          </span>
          <span v-else class="text-xs text-indigo-500/70 font-mono mt-0.5">
            Chart ingested.
          </span>
        </div>
      </div>

      <div
        v-if="isConnecting"
        class="z-10 animate-spin w-5 h-5 border-2 border-gray-500 border-t-white rounded-full"
      ></div>

      <svg
        v-if="isConnected"
        class="z-10 w-5 h-5 text-indigo-500"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M5 13l4 4L19 7"
        ></path>
      </svg>
    </button>

    <!-- Manual chart entry (Co-Star has no public API) -->
    <Teleport to="body">
      <div
        v-if="showModal"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
        @click.self="showModal = false"
      >
        <div
          class="bg-gray-900 border border-indigo-500/30 rounded-2xl p-8 w-full max-w-md shadow-2xl space-y-6"
          role="dialog"
          aria-modal="true"
          aria-labelledby="costar-modal-title"
        >
          <div class="text-center space-y-2">
            <h3 id="costar-modal-title" class="text-xl font-bold text-indigo-400">Your Natal Chart</h3>
            <p class="text-xs text-gray-500 font-mono">
              Copy your placements from the Co&#8239;&#8212;&#8239;Star app (Profile &rarr; Chart).
              Sun, Moon and Rising are enough.
            </p>
          </div>

          <form @submit.prevent="submitChart" class="space-y-3">
            <label
              v-for="field in FIELDS"
              :key="field.key"
              class="flex items-center justify-between gap-4 font-mono text-sm text-gray-300"
            >
              <span>{{ field.label }}<span v-if="!field.optional" class="text-indigo-400"> *</span></span>
              <select
                v-model="chart[field.key]"
                class="w-40 bg-black border border-gray-700 rounded-lg px-3 py-2 text-gray-200 focus:border-indigo-500 focus:outline-none"
              >
                <option value="">{{ field.optional ? '— skip —' : 'choose…' }}</option>
                <option v-for="sign in SIGNS" :key="sign" :value="sign">{{ sign }}</option>
              </select>
            </label>

            <p v-if="errorMessage" role="alert" class="text-xs text-rose-400 font-mono">{{ errorMessage }}</p>

            <div class="flex gap-3 pt-2">
              <button
                type="button"
                @click="showModal = false"
                class="flex-1 py-3 rounded-lg border border-gray-700 text-gray-400 hover:border-gray-500 transition-colors font-mono text-sm"
              >
                CANCEL
              </button>
              <button
                type="submit"
                :disabled="!canSubmit || isConnecting"
                class="flex-1 py-3 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold transition-colors font-mono text-sm"
              >
                {{ isConnecting ? 'SAVING...' : 'SAVE CHART' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useAuthStore } from '@/composables/useAuthStore'
import { useVibeStore } from '@/composables/useVibeStore'

const { token } = useAuthStore()
const { oauthState, markConnected } = useVibeStore()

const API = import.meta.env.VITE_API_URL || ''
const isConnecting = ref(false)
const showModal = ref(false)
const errorMessage = ref('')

const SIGNS = [
  'Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
  'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces',
]

type ChartKey = 'sun_sign' | 'moon_sign' | 'rising_sign' | 'venus_sign' | 'mars_sign'

const FIELDS: { key: ChartKey; label: string; optional: boolean }[] = [
  { key: 'sun_sign', label: 'Sun', optional: false },
  { key: 'moon_sign', label: 'Moon', optional: false },
  { key: 'rising_sign', label: 'Rising', optional: false },
  { key: 'venus_sign', label: 'Venus', optional: true },
  { key: 'mars_sign', label: 'Mars', optional: true },
]

const chart = reactive<Record<ChartKey, string>>({
  sun_sign: '', moon_sign: '', rising_sign: '', venus_sign: '', mars_sign: '',
})

const canSubmit = computed(() => !!(chart.sun_sign && chart.moon_sign && chart.rising_sign))

const isConnected = computed(() => oauthState.value.costar.connected)

const buttonText = computed(() => {
  if (isConnecting.value) return 'READING THE VOID...'
  if (isConnected.value) return 'CHART SAVED'
  return 'ADD CO—STAR CHART'
})

async function submitChart() {
  if (isConnected.value || !token.value || !canSubmit.value) return
  isConnecting.value = true
  errorMessage.value = ''

  try {
    const res = await fetch(`${API}/api/costar/manual`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token.value}`,
      },
      body: JSON.stringify(chart),
    })

    if (!res.ok) {
      const body = await res.json().catch(() => null)
      const detail = typeof body?.detail === 'string' ? body.detail : null
      errorMessage.value = detail ?? `Couldn't save your chart (error ${res.status}). Please try again.`
      return
    }
    markConnected('costar')
    showModal.value = false
  } catch {
    errorMessage.value = "Couldn't reach the server. Check your connection and try again."
  } finally {
    isConnecting.value = false
  }
}
</script>
