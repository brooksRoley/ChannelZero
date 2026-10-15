<template>
  <div class="min-h-screen bg-gray-950 text-gray-100 p-6">
    <div class="max-w-7xl mx-auto space-y-8">

      <!-- Header -->
      <div class="flex flex-wrap items-center justify-between gap-4">
        <h1 class="text-2xl font-bold tracking-tight">Admin</h1>
        <div class="flex items-center gap-4">
          <span v-if="failedCount" class="text-xs text-red-400">{{ failedCount }} panel{{ failedCount === 1 ? '' : 's' }} failed to load</span>
          <button @click="refresh" class="text-sm text-gray-400 hover:text-white transition-colors">
            Refresh
          </button>
        </div>
      </div>

      <!-- Tabs -->
      <div role="tablist" aria-label="Admin sections" class="flex gap-1 border-b border-gray-800 overflow-x-auto">
        <button
          v-for="t in TABS"
          :key="t.id"
          role="tab"
          :aria-selected="tab === t.id"
          class="px-4 py-2 text-sm whitespace-nowrap border-b-2 -mb-px transition-colors"
          :class="tab === t.id ? 'border-purple-500 text-white' : 'border-transparent text-gray-500 hover:text-gray-300'"
          @click="setTab(t.id)"
        >{{ t.label }}</button>
      </div>

      <div role="tabpanel">
        <AdminOverview v-if="tab === 'overview'" />
        <AdminUsers v-else-if="tab === 'users'" />
        <AdminSections v-else-if="tab === 'sections'" />
        <AdminHypnoAudit v-else-if="tab === 'audit'" />
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/composables/useAuthStore'
import { useAdminStore } from '@/composables/useAdminStore'
import AdminOverview from '@/components/admin/AdminOverview.vue'
import AdminUsers from '@/components/admin/AdminUsers.vue'
import AdminSections from '@/components/admin/AdminSections.vue'
import AdminHypnoAudit from '@/components/admin/AdminHypnoAudit.vue'

type Tab = 'overview' | 'users' | 'sections' | 'audit'
const TABS: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'users',    label: 'Users' },
  { id: 'sections', label: 'Sections' },
  { id: 'audit',    label: 'Hypno audit' },
]

const route = useRoute()
const router = useRouter()
const { user } = useAuthStore()
const {
  errors,
  fetchUsers, fetchFunnel, fetchConnectors,
  fetchSpotifyProfiles, fetchPsychProfiles,
  fetchArchetypes, fetchAttachmentStyles, fetchConnectorDepth,
  fetchEventStats,
} = useAdminStore()

const tab = computed<Tab>(() => {
  const q = route.query.tab as Tab
  return TABS.some(t => t.id === q) ? q : 'overview'
})

function setTab(id: Tab) {
  router.replace({ query: id === 'overview' ? {} : { tab: id } })
}

const failedCount = computed(() => Object.keys(errors).length)

// Guard — redirect non-admins
onMounted(async () => {
  if (!user.value?.is_admin) {
    router.replace('/')
    return
  }
  await refresh()
})

async function refresh() {
  // Each fetch records its own panel error, so one failure never blanks the rest.
  await Promise.allSettled([
    fetchFunnel(), fetchConnectors(), fetchUsers(1, 50),
    fetchSpotifyProfiles(1, 12), fetchPsychProfiles(1, 12),
    fetchArchetypes(), fetchAttachmentStyles(), fetchConnectorDepth(),
    fetchEventStats(),
  ])
}
</script>
