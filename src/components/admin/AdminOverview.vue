<template>
  <div class="space-y-8">
  <!-- Funnel with drop-off rates -->
  <section>
    <h2 class="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4">Conversion Funnel</h2>
    <PanelError :message="errors.funnel" />
    <div class="flex flex-wrap items-center gap-2">
      <template v-for="(step, i) in funnel" :key="step.step">
        <div class="bg-gray-900 border border-gray-800 rounded-xl p-4 text-center min-w-[100px]">
          <div class="text-2xl font-bold text-white">{{ step.count }}</div>
          <div class="text-xs text-purple-400 font-semibold mt-0.5">{{ step.pct }}%</div>
          <div class="text-xs text-gray-500 mt-1 leading-tight">{{ funnelLabel(step.step) }}</div>
        </div>
        <div v-if="i < funnel.length - 1" class="text-center px-1">
          <div class="text-gray-600 text-sm">→</div>
          <div
            class="text-xs font-medium"
            :class="dropOff(i) > 50 ? 'text-red-400' : dropOff(i) > 25 ? 'text-yellow-400' : 'text-green-400'"
          >-{{ dropOff(i) }}%</div>
        </div>
      </template>
    </div>
  </section>

  <!-- Connector Stats -->
  <section>
    <h2 class="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4">Connectors</h2>
    <PanelError :message="errors.connectors" />
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div
        v-for="c in connectors"
        :key="c.provider"
        class="bg-gray-900 border border-gray-800 rounded-xl p-5"
      >
        <div class="flex items-center justify-between mb-3">
          <span class="font-semibold capitalize">{{ c.provider }}</span>
          <span class="text-xs text-gray-500">{{ c.connection_rate_pct }}% connected</span>
        </div>

        <!-- Connection bar -->
        <div class="h-1.5 bg-gray-800 rounded-full mb-3">
          <div
            class="h-1.5 bg-purple-500 rounded-full transition-all"
            :style="{ width: `${Math.min(c.connection_rate_pct, 100)}%` }"
          ></div>
        </div>

        <div class="flex items-center justify-between text-sm">
          <span class="text-gray-400">{{ c.connected_count }} users</span>
          <span v-if="c.avg_rating !== null" class="flex items-center gap-1 text-yellow-400">
            <span class="text-xs">★</span>
            {{ c.avg_rating.toFixed(1) }}
            <span class="text-gray-600 text-xs">({{ c.feedback_count }})</span>
          </span>
          <span v-else class="text-gray-600 text-xs">No ratings yet</span>
        </div>

        <div v-if="c.top_tags?.length" class="flex flex-wrap gap-1 mt-3">
          <span
            v-for="tag in c.top_tags.slice(0, 3)"
            :key="tag"
            class="text-xs px-2 py-0.5 bg-gray-800 rounded-full text-gray-400"
          >{{ tag.replace(/_/g, ' ') }}</span>
        </div>
      </div>
    </div>
  </section>

  <!-- Insights -->
  <section>
    <h2 class="text-xs font-semibold uppercase tracking-widest text-gray-500 mb-4">Insights</h2>
    <PanelError :message="errors.archetypes || errors.attachment || errors.depth" />
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">

      <!-- Archetype Distribution -->
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <div class="text-xs text-gray-500 mb-3">Archetype Distribution</div>
        <div v-if="archetypes.length" class="space-y-2">
          <div v-for="a in archetypes" :key="a.archetype" class="flex items-center gap-2">
            <span class="text-xs text-purple-400 w-28 truncate font-medium">{{ a.archetype }}</span>
            <div class="flex-1 h-1.5 bg-gray-800 rounded-full">
              <div
                class="h-1.5 bg-purple-500 rounded-full"
                :style="{ width: `${archetypesTotal ? (a.count / archetypesTotal * 100) : 0}%` }"
              ></div>
            </div>
            <span class="text-xs text-gray-500 w-8 text-right">{{ a.count }}</span>
          </div>
        </div>
        <div v-else class="text-xs text-gray-600">No data yet</div>
      </div>

      <!-- Attachment Styles -->
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <div class="text-xs text-gray-500 mb-3">Attachment Styles</div>
        <div v-if="attachmentStyles.length" class="flex flex-wrap gap-2">
          <div
            v-for="s in attachmentStyles"
            :key="s.style"
            class="px-3 py-1.5 rounded-full text-xs font-medium"
            :class="{
              'bg-green-900/40 text-green-400': s.style === 'secure',
              'bg-yellow-900/40 text-yellow-400': s.style === 'anxious-preoccupied',
              'bg-blue-900/40 text-blue-400': s.style === 'dismissive-avoidant',
              'bg-red-900/40 text-red-400': s.style === 'fearful-avoidant',
            }"
          >
            {{ s.style }} · {{ attachmentTotal ? Math.round(s.count / attachmentTotal * 100) : 0 }}%
          </div>
        </div>
        <div v-else class="text-xs text-gray-600">No data yet</div>
      </div>

      <!-- Connector Depth -->
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <div class="text-xs text-gray-500 mb-3">Connector Depth</div>
        <div v-if="connectorDepth.length" class="space-y-2">
          <div v-for="b in connectorDepth" :key="b.connectors" class="flex items-center gap-2">
            <span class="text-xs text-gray-400 w-16">{{ b.connectors === 3 ? '3+' : b.connectors }} {{ b.connectors === 1 ? 'source' : 'sources' }}</span>
            <div class="flex-1 h-1.5 bg-gray-800 rounded-full">
              <div
                class="h-1.5 rounded-full"
                :class="{
                  'bg-gray-600': b.connectors === 0,
                  'bg-yellow-500': b.connectors === 1,
                  'bg-green-500': b.connectors === 2,
                  'bg-purple-500': b.connectors === 3,
                }"
                :style="{ width: `${Math.max(5, b.count / Math.max(...connectorDepth.map(d => d.count)) * 100)}%` }"
              ></div>
            </div>
            <span class="text-xs text-gray-500 w-8 text-right">{{ b.count }}</span>
          </div>
        </div>
        <div v-else class="text-xs text-gray-600">No data yet</div>
      </div>

    </div>
  </section>
  </div>
</template>

<script setup lang="ts">
import { useAdminStore } from '@/composables/useAdminStore'
import PanelError from './PanelError.vue'

const { funnel, connectors, archetypes, archetypesTotal, attachmentStyles, attachmentTotal,
        connectorDepth, errors } = useAdminStore()

function dropOff(i: number): number {
  const curr = funnel.value[i]?.count || 0
  const next = funnel.value[i + 1]?.count || 0
  if (curr === 0) return 0
  return Math.round((1 - next / curr) * 100)
}

function funnelLabel(step: string) {
  const labels: Record<string, string> = {
    registered:              'Registered',
    completed_poll:          'Completed Poll',
    connected_any:           'Connected 1+',
    connected_2plus:         'Connected 2+',
    has_vibe_vector:         'Synthesized',
    completed_psychometrics: 'Psychometrics',
    opened_self_expression_view: 'Opened Self-Expr',
    completed_session:           'Completed Session',
    returned_next_day:           'Returned Next Day',
  }
  return labels[step] ?? step
}
</script>
