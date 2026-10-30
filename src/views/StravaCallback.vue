<template>
  <div class="min-h-screen bg-gray-900 flex items-center justify-center">
    <div class="text-center space-y-4">
      <div v-if="!errorMsg" class="animate-spin w-8 h-8 border-2 border-gray-500 border-t-orange-400 rounded-full mx-auto"></div>
      <p class="text-gray-400 text-sm font-mono">
        {{ errorMsg || 'Mapping somatic ledger...' }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useVibeStore } from '@/composables/useVibeStore'

const route = useRoute()
const router = useRouter()
const { markConnected } = useVibeStore()
const errorMsg = ref<string | null>(null)

const API = import.meta.env.VITE_API_URL || ''

onMounted(async () => {
  const code = route.query.code as string | undefined
  const state = route.query.state as string | undefined
  const scope = route.query.scope as string | undefined

  if (route.query.error) {
    errorMsg.value = "Strava wasn't connected: access was declined."
    return
  }

  if (!code || !state) {
    errorMsg.value = 'Missing authorization code or state.'
    return
  }

  try {
    // scope = what the user actually granted; the server refuses a connection
    // without activity access rather than storing an empty profile.
    const scopeParam = scope !== undefined ? `&scope=${encodeURIComponent(scope)}` : ''
    const res = await fetch(`${API}/api/strava/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}${scopeParam}`)

    if (res.ok) {
      markConnected('strava')
      router.replace('/peripheral')
    } else {
      const data = await res.json().catch(() => ({}))
      const d = data.detail
      throw new Error((d && typeof d === 'object' ? d.message : d) || 'Strava callback failed')
    }
  } catch (e: any) {
    errorMsg.value = e.message || 'Strava sync failed.'
  }
})
</script>
