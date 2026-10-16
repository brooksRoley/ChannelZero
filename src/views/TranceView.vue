<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import TranceCanvas from '@/components/TranceCanvas.vue'
import PostTranceOverlay from '@/components/PostTranceOverlay.vue'
import { useTranceEngine } from '@/composables/useTranceEngine'
import { logPublicEvent } from '@/composables/useAnalytics'

const { completedSession, clearCompletedSession } = useTranceEngine()
const showOverlay = ref(false)

watch(completedSession, (data) => {
  if (data) {
    showOverlay.value = true
    logPublicEvent('public_session_completed', 'trance', data.sessionDurationMs)
  }
})

onMounted(() => logPublicEvent('public_visit', 'trance'))

function handleOverlayClose() {
  showOverlay.value = false
  clearCompletedSession()
}
</script>

<template>
  <div class="trance-view">
    <TranceCanvas />

    <PostTranceOverlay
      v-if="showOverlay && completedSession"
      :coherence="completedSession.coherence"
      :sync-count="completedSession.syncCount"
      :session-duration="completedSession.sessionDurationMs"
      :dominant-phase="completedSession.dominantPhase"
      @close="handleOverlayClose"
    />
  </div>
</template>

<style scoped>
.trance-view {
  position: absolute;
  inset: 0;
  overflow: hidden;
}
</style>
