<template>
  <div class="space-y-6">
    <PanelError :message="errors.events" />

    <!-- Instrumentation health -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div v-for="s in summary" :key="s.label" class="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div class="text-2xl font-bold" :class="s.color">{{ s.count }}</div>
        <div class="text-xs text-gray-500 mt-1">{{ s.label }}</div>
      </div>
    </div>

    <div v-if="rejected.length" role="alert" class="bg-red-900/30 border border-red-500/30 rounded-xl p-3 text-xs text-red-300">
      Sent by the client but rejected by the server (not in VALID_EVENTS): {{ rejected.join(', ') }}
    </div>
    <div v-if="unwired.length" class="bg-yellow-900/20 border border-yellow-500/20 rounded-xl p-3 text-xs text-yellow-300">
      Allowed server-side but no section sends them: {{ unwired.join(', ') }}
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] gap-6">
      <!-- Section list -->
      <div class="space-y-5">
        <div class="flex flex-wrap gap-1.5" role="group" aria-label="Filter by experiment">
          <button
            v-for="f in filters"
            :key="f.id"
            class="text-xs px-2.5 py-1 rounded-full border transition-colors"
            :class="filter === f.id ? 'border-purple-500 text-purple-300 bg-purple-900/30' : 'border-gray-800 text-gray-400 hover:text-white'"
            :aria-pressed="filter === f.id"
            @click="filter = f.id"
          >{{ f.label }}</button>
        </div>

        <div v-for="group in grouped" :key="group.pillar">
          <h3 class="text-[10px] font-semibold uppercase tracking-widest text-gray-500 mb-2">{{ PILLAR_LABELS[group.pillar] }}</h3>
          <ul class="space-y-1">
            <li v-for="s in group.sections" :key="s.id">
              <button
                class="w-full text-left rounded-lg px-3 py-2 border transition-colors flex items-center gap-3"
                :class="s.id === selected?.id ? 'border-purple-500/60 bg-gray-900' : 'border-transparent hover:bg-gray-900/60'"
                :aria-current="s.id === selected?.id"
                @click="select(s.id)"
              >
                <span class="w-2 h-2 rounded-full shrink-0" :class="STATUS_DOT[statusOf(s)]" :title="STATUS_LABEL[statusOf(s)]"></span>
                <span class="flex-1 min-w-0">
                  <span class="block text-sm text-white truncate">{{ s.name }}</span>
                  <span class="block text-[11px] text-gray-500 truncate">{{ s.route }}</span>
                </span>
                <span class="text-xs text-gray-400 tabular-nums">{{ sectionTotals(s).last_7d }}</span>
              </button>
            </li>
          </ul>
        </div>
      </div>

      <!-- Selected section -->
      <div v-if="selected" class="space-y-4 min-w-0">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold text-white">{{ selected.name }}</h2>
            <div class="flex flex-wrap items-center gap-2 mt-1 text-xs">
              <span class="text-gray-500">{{ selected.route }}</span>
              <span class="px-2 py-0.5 rounded-full bg-gray-800 text-gray-400">{{ selected.auth ? 'login required' : 'public' }}</span>
              <span v-for="e in selected.experiments" :key="e" class="px-2 py-0.5 rounded-full bg-purple-900/40 text-purple-300">
                {{ e }} · {{ EXPERIMENT_LABELS[e] }}
              </span>
              <span class="px-2 py-0.5 rounded-full" :class="STATUS_PILL[statusOf(selected)]">{{ STATUS_LABEL[statusOf(selected)] }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button class="admin-btn" :disabled="index <= 0" @click="step(-1)">← Prev</button>
            <span class="text-xs text-gray-500 tabular-nums">{{ index + 1 }} / {{ visible.length }}</span>
            <button class="admin-btn" :disabled="index >= visible.length - 1" @click="step(1)">Next →</button>
            <a :href="selected.preview" target="_blank" rel="noopener" class="admin-btn">Open ↗</a>
          </div>
        </div>

        <p v-if="selected.note" class="text-xs text-gray-400">{{ selected.note }}</p>
        <p v-if="!selected.auth" class="text-xs text-gray-500">
          Anonymous visits aren't tracked: logEvent is a no-op without a login, so this section only counts signed-in users.
        </p>

        <!-- Event table -->
        <div class="rounded-xl border border-gray-800 overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
                <th class="text-left px-4 py-2">Event</th>
                <th class="text-right px-4 py-2">Total</th>
                <th class="text-right px-4 py-2">Users</th>
                <th class="text-right px-4 py-2">7 days</th>
                <th class="text-right px-4 py-2">Last seen</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-800/50">
              <tr v-for="ev in selected.events" :key="ev">
                <td class="px-4 py-2 font-mono text-xs" :class="validSet.has(ev) || !validEvents.length ? 'text-gray-300' : 'text-red-400'">
                  {{ ev }}<span v-if="validEvents.length && !validSet.has(ev)"> (rejected)</span>
                </td>
                <td class="px-4 py-2 text-right tabular-nums text-gray-300">{{ stat(ev)?.total ?? 0 }}</td>
                <td class="px-4 py-2 text-right tabular-nums text-gray-300">{{ stat(ev)?.users ?? 0 }}</td>
                <td class="px-4 py-2 text-right tabular-nums text-gray-300">{{ stat(ev)?.last_7d ?? 0 }}</td>
                <td class="px-4 py-2 text-right text-gray-500 whitespace-nowrap">{{ formatAgo(stat(ev)?.last_at) }}</td>
              </tr>
              <tr v-if="!selected.events.length">
                <td colspan="5" class="px-4 py-4 text-center text-xs text-gray-500">
                  No analytics events. This section can't be measured yet.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Live preview -->
        <div class="flex items-center justify-between">
          <label class="flex items-center gap-2 text-xs text-gray-400">
            <input v-model="showPreview" type="checkbox" class="accent-purple-500" />
            Live preview
          </label>
          <span class="text-[11px] text-gray-600">Audio-reactive sections need a click inside the frame to start sound</span>
        </div>
        <div v-if="showPreview" class="rounded-xl border border-gray-800 overflow-hidden bg-black aspect-video">
          <iframe
            :key="selected.id"
            :src="selected.preview"
            :title="`Preview of ${selected.name}`"
            class="w-full h-full"
            allow="autoplay; fullscreen"
          ></iframe>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAdminStore, type EventStat } from '@/composables/useAdminStore'
import {
  SITE_SECTIONS, PILLAR_LABELS, EXPERIMENT_LABELS,
  type SiteSection, type Pillar, type ExperimentId,
} from '@/config/siteSections'
import PanelError from './PanelError.vue'

const { eventStats, validEvents, errors } = useAdminStore()
const route = useRoute()
const router = useRouter()

type Status = 'measured' | 'quiet' | 'dark'
const STATUS_LABEL: Record<Status, string> = { measured: 'measured', quiet: 'instrumented, no data', dark: 'not instrumented' }
const STATUS_DOT: Record<Status, string> = { measured: 'bg-green-500', quiet: 'bg-yellow-500', dark: 'bg-gray-600' }
const STATUS_PILL: Record<Status, string> = {
  measured: 'bg-green-900/40 text-green-300',
  quiet: 'bg-yellow-900/40 text-yellow-300',
  dark: 'bg-gray-800 text-gray-400',
}

const statsByEvent = computed(() => new Map(eventStats.value.map(e => [e.event, e])))
const validSet = computed(() => new Set(validEvents.value))
const stat = (ev: string): EventStat | undefined => statsByEvent.value.get(ev)

function sectionTotals(s: SiteSection) {
  return s.events.reduce(
    (acc, ev) => ({ total: acc.total + (stat(ev)?.total ?? 0), last_7d: acc.last_7d + (stat(ev)?.last_7d ?? 0) }),
    { total: 0, last_7d: 0 },
  )
}

function statusOf(s: SiteSection): Status {
  if (!s.events.length) return 'dark'
  return sectionTotals(s).total > 0 ? 'measured' : 'quiet'
}

// ── Filtering + grouping ──
type Filter = 'all' | ExperimentId
const filters: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  ...(Object.keys(EXPERIMENT_LABELS) as ExperimentId[]).map(id => ({ id, label: `${id} · ${EXPERIMENT_LABELS[id]}` })),
]
const filter = ref<Filter>('all')
const visible = computed(() =>
  filter.value === 'all' ? SITE_SECTIONS : SITE_SECTIONS.filter(s => s.experiments.includes(filter.value as ExperimentId)),
)
const grouped = computed(() => {
  const order = Object.keys(PILLAR_LABELS) as Pillar[]
  return order
    .map(pillar => ({ pillar, sections: visible.value.filter(s => s.pillar === pillar) }))
    .filter(g => g.sections.length)
})

// ── Selection (kept in ?section= so a section can be linked) ──
const selectedId = ref<string>((route.query.section as string) || SITE_SECTIONS[0].id)
const selected = computed(() => visible.value.find(s => s.id === selectedId.value) ?? visible.value[0])
const index = computed(() => visible.value.findIndex(s => s.id === selected.value?.id))
const showPreview = ref(false)

function select(id: string) {
  selectedId.value = id
  router.replace({ query: { ...route.query, section: id } })
}
function step(delta: number) {
  const next = visible.value[index.value + delta]
  if (next) select(next.id)
}
watch(filter, () => { if (selected.value) selectedId.value = selected.value.id })

// ── Summary ──
const summary = computed(() => {
  const counts = { measured: 0, quiet: 0, dark: 0 }
  SITE_SECTIONS.forEach(s => counts[statusOf(s)]++)
  const total7d = eventStats.value.reduce((n, e) => n + e.last_7d, 0)
  return [
    { label: 'Sections measured', count: counts.measured, color: 'text-green-400' },
    { label: 'Instrumented, no data', count: counts.quiet, color: 'text-yellow-400' },
    { label: 'Not instrumented', count: counts.dark, color: 'text-gray-400' },
    { label: 'Events, last 7 days', count: total7d, color: 'text-white' },
  ]
})

const emitted = computed(() => new Set(SITE_SECTIONS.flatMap(s => s.events)))
const rejected = computed(() =>
  validEvents.value.length ? [...emitted.value].filter(e => !validSet.value.has(e)) : [],
)
const unwired = computed(() => validEvents.value.filter(e => !emitted.value.has(e)))

function formatAgo(iso?: string | null) {
  if (!iso) return 'never'
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  return `${days}d ago`
}
</script>

<style scoped>
.admin-btn {
  @apply text-xs px-2.5 py-1 rounded-lg border border-gray-800 text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed;
}
</style>
