<template>
  <div class="relative group w-full">
    <div
      class="absolute -inset-0.5 rounded-xl blur opacity-30 group-hover:opacity-70 transition duration-500"
      :class="glowClass"
    ></div>

    <button
      @click="handleClick"
      :disabled="connecting || connected"
      class="relative flex items-center justify-between w-full bg-black border border-gray-800 text-gray-200 px-6 py-4 rounded-xl shadow-2xl transition-all overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/30 focus-visible:border-white/40"
      :class="{
        'opacity-50 cursor-not-allowed': connecting,
        [connectedBorderClass]: connected,
      }"
    >
      <div class="flex items-center gap-4 z-10">
        <slot name="icon">
          <div class="w-6 h-6 rounded-full bg-gray-700"></div>
        </slot>

        <div class="flex flex-col text-left">
          <span
            class="font-bold text-sm tracking-wide uppercase"
            :class="{ [connectedTextClass]: connected }"
          >
            {{ buttonText }}
          </span>
          <span v-if="!connected" class="text-xs text-gray-500 font-mono mt-0.5">
            {{ subtitle }}
          </span>
          <span v-else class="text-xs font-mono mt-0.5" :class="connectedSubtitleClass">
            {{ connectedSubtitle }}
          </span>
        </div>
      </div>

      <div
        v-if="connecting"
        class="z-10 animate-spin w-5 h-5 border-2 border-gray-500 border-t-white rounded-full"
      ></div>

      <svg
        v-if="connected && !connecting"
        class="z-10 w-5 h-5"
        :class="connectedTextClass"
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
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  provider: string
  label: string
  connected: boolean
  connecting?: boolean
  subtitle?: string
  connectedSubtitle?: string
  color?: string
}>(), {
  connecting: false,
  subtitle: 'Connect to sharpen the signal.',
  connectedSubtitle: 'Signal locked.',
  color: 'green',
})

const emit = defineEmits<{
  connect: []
}>()

const COLOR_MAP: Record<string, { glow: string; border: string; text: string; subtitle: string }> = {
  green:  { glow: 'bg-gradient-to-r from-green-600/40 to-emerald-500/40', border: 'border-green-500/50', text: 'text-green-400', subtitle: 'text-green-500/70' },
  blue:   { glow: 'bg-gradient-to-r from-blue-600/40 to-sky-500/40',     border: 'border-blue-500/50',  text: 'text-blue-400',  subtitle: 'text-blue-500/70' },
  orange: { glow: 'bg-gradient-to-r from-orange-600/40 to-amber-500/40', border: 'border-orange-500/50', text: 'text-orange-400', subtitle: 'text-orange-500/70' },
  red:    { glow: 'bg-gradient-to-r from-red-600/40 to-rose-500/40',     border: 'border-red-500/50',   text: 'text-red-400',   subtitle: 'text-red-500/70' },
  purple: { glow: 'bg-gradient-to-r from-purple-600/40 to-violet-500/40', border: 'border-purple-500/50', text: 'text-purple-400', subtitle: 'text-purple-500/70' },
  indigo: { glow: 'bg-gradient-to-r from-indigo-600/40 to-blue-500/40',  border: 'border-indigo-500/50', text: 'text-indigo-400', subtitle: 'text-indigo-500/70' },
  emerald: { glow: 'bg-gradient-to-r from-emerald-600/40 to-teal-500/40', border: 'border-emerald-500/50', text: 'text-emerald-400', subtitle: 'text-emerald-500/70' },
  cyan:   { glow: 'bg-gradient-to-r from-cyan-600/40 to-teal-500/40',    border: 'border-cyan-500/50',  text: 'text-cyan-400',  subtitle: 'text-cyan-500/70' },
  pink:   { glow: 'bg-gradient-to-r from-pink-600/40 to-rose-500/40',    border: 'border-pink-500/50',  text: 'text-pink-400',  subtitle: 'text-pink-500/70' },
  gray:   { glow: 'bg-gradient-to-r from-gray-800/40 to-slate-600/40',   border: 'border-[#f0f6fc]/50', text: 'text-[#f0f6fc]', subtitle: 'text-[#f0f6fc]/70' },
}

const colors = computed(() => COLOR_MAP[props.color] || COLOR_MAP.green)

const glowClass = computed(() => colors.value.glow)
const connectedBorderClass = computed(() => colors.value.border)
const connectedTextClass = computed(() => colors.value.text)
const connectedSubtitleClass = computed(() => colors.value.subtitle)

const buttonText = computed(() => {
  if (props.connecting) return `CONNECTING ${props.label.toUpperCase()}...`
  if (props.connected) return `${props.label.toUpperCase()} SYNCED`
  return `CONNECT ${props.label.toUpperCase()}`
})

function handleClick() {
  if (props.connected || props.connecting) return
  emit('connect')
}
</script>
