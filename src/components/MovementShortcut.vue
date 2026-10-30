<template>
  <div class="ccard-idle border rounded-2xl p-6 shadow-xl" data-testid="movement-card">
    <div class="flex justify-between items-start mb-4">
      <div>
        <h2 class="text-2xl font-bold text-rose-300">Movement</h2>
        <h3 class="text-sm font-medium text-gray-500 uppercase tracking-wider mt-1">Apple Health, via a Shortcut</h3>
      </div>
    </div>

    <p class="text-sm text-gray-400">
      A Shortcut on your iPhone sends each workout's start, end and type. Nothing else:
      no heart rate, distance or location. It never reaches the Oracle or any AI.
    </p>

    <!-- The token: shown once, right after it's made -->
    <div v-if="token" class="mt-4 space-y-2" data-testid="movement-token">
      <p class="text-xs text-gray-500 uppercase tracking-wider">Paste into the Shortcut (shown once)</p>
      <div class="flex gap-2">
        <code class="flex-1 truncate text-xs bg-black/40 border border-gray-800 rounded px-2 py-1">{{ token }}</code>
        <button class="text-xs text-rose-300 hover:underline" @click="copy(token)">{{ copied ? 'Copied' : 'Copy' }}</button>
      </div>
      <p class="text-xs text-gray-500">Endpoint: <code>{{ endpoint }}</code></p>
    </div>

    <p v-if="status" class="mt-4 text-xs text-gray-500" data-testid="movement-status">{{ statusLine }}</p>

    <ul v-if="days.length" class="mt-3 space-y-1 text-sm text-gray-300" data-testid="movement-days">
      <li v-for="d in days" :key="d.date">
        <span class="text-gray-500">{{ dayLabel(d.date) }}</span> · {{ d.minutes }} min
        <span class="text-gray-500">({{ d.kinds.map((k) => k.kind).join(', ') }})</span>
      </li>
    </ul>

    <p v-if="error" class="mt-3 text-xs text-red-400">{{ error }}</p>

    <div class="mt-4 flex gap-4 text-xs">
      <button class="text-rose-300 hover:underline" :disabled="busy" @click="makeToken">
        {{ status?.has_token ? 'Replace token' : 'Make a token' }}
      </button>
      <a class="text-gray-400 hover:underline" :href="guide" target="_blank" rel="noopener">How to build the Shortcut</a>
      <button v-if="status?.has_token || days.length" class="text-gray-500 hover:underline" :disabled="busy" @click="wipe">
        Delete my movement data
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '@/composables/useAuthStore'

interface Status { has_token: boolean; last_received_at: string | null }
interface Day { date: string; minutes: number; kinds: { kind: string; minutes: number }[] }

const { apiFetch } = useAuthStore()
const API = import.meta.env.VITE_API_URL || window.location.origin
const endpoint = `${API}/api/movement/workouts`
const guide = 'https://github.com/brooksRoley/ChannelZero/blob/main/docs/APPLE_HEALTH_SHORTCUT.md'

const status = ref<Status | null>(null)
const days = ref<Day[]>([])
const token = ref('')
const copied = ref(false)
const busy = ref(false)
const error = ref('')

const statusLine = computed(() => {
  const s = status.value
  if (!s?.has_token) return 'No Shortcut set up yet.'
  if (!s.last_received_at) return 'Token made. Nothing received yet.'
  const d = new Date(s.last_received_at)
  return `Last received ${d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}, ${d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`
})

function dayLabel(iso: string): string {
  // A bare date is local; don't let Date() read it as UTC midnight.
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

async function load() {
  try {
    status.value = await apiFetch<Status>('/api/movement/status')
    days.value = (await apiFetch<{ days: Day[] }>('/api/movement/days?days=14')).days
  } catch (e: any) {
    error.value = e?.message || "Couldn't load movement."
  }
}

async function makeToken() {
  busy.value = true
  error.value = ''
  try {
    token.value = (await apiFetch<{ token: string }>('/api/movement/token', { method: 'POST' })).token
    copied.value = false
    await load()
  } catch (e: any) {
    error.value = e?.message || "Couldn't make a token."
  }
  busy.value = false
}

async function wipe() {
  busy.value = true
  error.value = ''
  try {
    await apiFetch('/api/movement', { method: 'DELETE' })
    token.value = ''
    await load()
  } catch (e: any) {
    error.value = e?.message || "Couldn't delete."
  }
  busy.value = false
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = true
  } catch { /* the token is still on screen to select */ }
}

onMounted(load)
</script>
