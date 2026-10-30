<template>
  <div class="relative group w-full">
    <div
      class="absolute -inset-0.5 bg-gradient-to-r from-gray-700 to-gray-900 rounded-xl blur opacity-30 group-hover:opacity-70 transition duration-500"
    ></div>

    <button
      @click="initiateXAuth"
      :disabled="isConnecting || isConnected"
      class="relative flex items-center justify-between w-full bg-black border border-gray-800 text-gray-200 px-6 py-4 rounded-xl shadow-2xl transition-all overflow-hidden"
      :class="{ 'opacity-50 cursor-not-allowed': isConnecting, 'border-green-500/50': isConnected }"
    >
      <div class="flex items-center gap-4 z-10">
        <svg viewBox="0 0 24 24" aria-hidden="true" class="w-6 h-6 fill-current text-white">
          <path
            d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 22.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"
          ></path>
        </svg>

        <div class="flex flex-col text-left">
          <span
            class="font-bold text-sm tracking-wide uppercase"
            :class="{ 'text-green-400': isConnected }"
          >
            {{ buttonText }}
          </span>
          <span v-if="!isConnected" class="text-xs text-gray-500 font-mono mt-0.5">
            Inject your neurotic footprint.
          </span>
          <span v-else class="text-xs text-green-500/70 font-mono mt-0.5">Vector armed.</span>
        </div>
      </div>

      <div
        v-if="isConnecting"
        class="z-10 animate-spin w-5 h-5 border-2 border-gray-500 border-t-white rounded-full"
      ></div>

      <svg
        v-if="isConnected"
        class="z-10 w-5 h-5 text-green-500"
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
  </div>
  <p v-if="connectError" class="mt-2 text-xs text-red-400 font-mono text-center">{{ connectError }}</p>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAuthStore } from '@/composables/useAuthStore'
import { useVibeStore } from '@/composables/useVibeStore'

const { token, logout } = useAuthStore()
const { oauthState } = useVibeStore()

const API = import.meta.env.VITE_API_URL || ''
const isConnecting = ref(false)
const connectError = ref<string | null>(null)
const isConnected = computed(() => oauthState.value.twitter.connected)

const buttonText = computed(() => {
  if (isConnecting.value) return 'ESTABLISHING HANDSHAKE...'
  if (isConnected.value) return 'X VECTOR SYNCED'
  return 'CONNECT X (TWITTER)'
})

async function initiateXAuth() {
  if (isConnected.value || !token.value) return
  isConnecting.value = true
  connectError.value = null

  try {
    const response = await fetch(`${API}/api/twitter/connect`, {
      headers: { Authorization: `Bearer ${token.value}` },
    })
    if (response.status === 401) {
      logout()
      window.location.href = '/login'
      return
    }
    const data = await response.json()

    if (!response.ok) {
      // Connectors answer {detail: {code, message}}; older routes, a string.
      const d = data.detail
      connectError.value = (d && typeof d === 'object' ? d.message : d) || `Error ${response.status}`
      return
    }

    if (data.auth_url) {
      window.location.href = data.auth_url
    } else {
      connectError.value = 'No auth URL returned from server'
    }
  } catch (error) {
    connectError.value = 'Could not reach the server'
  } finally {
    isConnecting.value = false
  }
}
</script>
