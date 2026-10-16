<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import NavBar from '@/components/NavBar.vue'
import SideBar from '@/components/SideBar.vue'
import PracticeCompanion from '@/components/PracticeCompanion.vue'
import { useZenMode } from '@/composables/useZenMode'
import { useVibeStore } from '@/composables/useVibeStore'

const route = useRoute()
const { syncConnectors } = useVibeStore()
const mainRef = ref<HTMLElement | null>(null)
const { zenMode } = useZenMode()

const isFullBleed = computed(() => {
  return ['reader', 'zeromind', 'fractionation', 'studio', 'liquidglass', 'spiral', 'trance', 'webaudio'].includes(
    route.name as string
  )
})

// Hide sidebar on immersive/fullbleed routes, login/universe, or zen mode
const hideSidebar = computed(() => {
  return zenMode.value || isFullBleed.value || ['login', 'universe', 'hypno'].includes(route.name as string)
})

function toggleFullscreen() {
  const el = document.documentElement
  if (document.fullscreenElement || (document as any).webkitFullscreenElement) {
    if (document.exitFullscreen) document.exitFullscreen()
    else if ((document as any).webkitExitFullscreen) (document as any).webkitExitFullscreen()
  } else {
    if (el.requestFullscreen) el.requestFullscreen()
    else if ((el as any).webkitRequestFullscreen) (el as any).webkitRequestFullscreen()
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'f' || e.key === 'F') {
    const tag = (e.target as HTMLElement)?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA') return
    if (isFullBleed.value) {
      e.preventDefault()
      toggleFullscreen()
    }
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  syncConnectors()
})
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div :class="['app-container', { 'app-container--with-sidebar': !hideSidebar }]">
    <SideBar v-if="!hideSidebar" />
    <NavBar v-if="!zenMode" />
    <PracticeCompanion />

    <main ref="mainRef" :class="['app-main', { 'app-main--fullbleed': isFullBleed }]">
      <RouterView v-slot="{ Component }">
        <Transition :name="isFullBleed ? 'dissolve' : 'page'" mode="out-in">
          <component :is="Component" :key="route.name" />
        </Transition>
      </RouterView>
    </main>
  </div>
</template>

<style scoped>
.app-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: #1a1a1a;
  color: #e2e8f0;
}

/* When sidebar is present, offset all content */
.app-container--with-sidebar {
  padding-left: 240px;
}

.app-main {
  flex: 1;
  padding: 1.5rem 2rem 4rem;
  max-width: 900px;
  width: 100%;
  margin: 0 auto;
}

.app-main--fullbleed {
  padding: 0;
  max-width: none;
  position: relative;
}

@media (max-width: 768px) {
  .app-container--with-sidebar {
    padding-left: 0;
  }

  .app-main {
    padding: 3.5rem 1rem 4rem; /* extra top padding for mobile toggle button */
  }
}

/* ── Route transitions ── */

/* Standard pages: short fade + slight upward drift */
.page-enter-active,
.page-leave-active {
  transition:
    opacity 0.22s ease,
    transform 0.22s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* Fullbleed / immersive: slower pure dissolve */
.dissolve-enter-active,
.dissolve-leave-active {
  transition: opacity 0.55s ease;
}
.dissolve-enter-from,
.dissolve-leave-to {
  opacity: 0;
}
</style>
