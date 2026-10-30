<template>
  <!-- Strava was retired 2026-10-30 (server/app/providers.py): no connect flow. -->
  <span
    class="flex items-center gap-2 border border-gray-800 text-gray-500 px-4 py-2 rounded-xl text-xs font-mono uppercase tracking-wide"
    :title="RETIRED_PROVIDERS.strava"
    data-testid="strava-retired-badge"
  >
    <svg viewBox="0 0 24 24" aria-hidden="true" class="w-4 h-4 fill-current text-gray-600">
      <path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169" />
    </svg>
    Retired
  </span>
</template>

<script setup lang="ts">
import { RETIRED_PROVIDERS } from '@/config/connectorConfig'
</script>
