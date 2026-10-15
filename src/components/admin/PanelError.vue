<template>
  <div
    v-if="message"
    role="alert"
    class="bg-red-900/30 border border-red-500/30 rounded-xl p-3 mb-4 text-red-400 text-xs"
  >
    {{ message }}
  </div>
</template>

<script setup lang="ts">
defineProps<{ message?: string }>()
</script>
