<template>
  <div class="space-y-3">

    <!-- ── Binaural section ── -->
    <div class="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 space-y-3">
      <div class="flex items-center justify-between gap-2">
        <span class="text-[10px] uppercase tracking-[0.2em] text-white/40">Binaural entrainment</span>
        <button
          class="cz-chip"
          :class="binaural.enabled ? 'cz-chip-on' : 'cz-chip-off'"
          @click="toggleEnabled"
        >
          {{ binaural.enabled ? 'On' : 'Off' }}
        </button>
      </div>

      <p class="text-[9px] text-white/25 leading-snug">
        Two close tones, one per ear — the brain hears a third pulse. Use headphones; without
        them the beat does not form. Effects are real but modest and best treated as an anchor.
      </p>

      <template v-if="binaural.enabled">
        <!-- Mode switch -->
        <div class="flex gap-1.5">
          <button
            class="cz-chip flex-1"
            :class="binaural.mode === 'preset' ? 'cz-chip-on' : 'cz-chip-off'"
            @click="setMode('preset')"
          >
            Preset
          </button>
          <button
            class="cz-chip flex-1"
            :class="binaural.mode === 'journey' ? 'cz-chip-on' : 'cz-chip-off'"
            @click="setMode('journey')"
          >
            Journey
          </button>
        </div>

        <!-- ── Preset mode ── -->
        <template v-if="binaural.mode === 'preset'">
          <div class="flex gap-1.5 flex-wrap">
            <button
              v-for="(def, band) in BANDS"
              :key="band"
              class="cz-chip"
              :class="binaural.band === band ? 'cz-chip-on' : 'cz-chip-off'"
              @click="pickBand(band as Band)"
            >
              {{ def.label }}
              <span class="opacity-50 ml-0.5">{{ def.beatHz }}Hz</span>
            </button>
          </div>

          <!-- Explanation card for the selected band -->
          <div class="rounded-md border border-white/[0.06] bg-black/30 p-2.5 space-y-1.5">
            <div class="flex items-center gap-2">
              <span class="text-[11px] text-white/80 tracking-wide">{{ activeDef.label }}</span>
              <span class="text-[9px] text-white/30 font-mono">{{ activeDef.beatHz }} Hz @ {{ activeDef.carrierHz }} Hz</span>
            </div>
            <p class="text-[10px] text-white/45 leading-relaxed">{{ activeDef.blurb }}</p>
            <router-link
              :to="`/learn/${activeDef.learnSlug}`"
              class="inline-block text-[10px] text-emerald-400/70 hover:text-emerald-400 tracking-wider transition-colors"
            >
              Deep dive &rarr;
            </router-link>
          </div>
        </template>

        <!-- ── Journey mode ── -->
        <template v-else>
          <p class="text-[9px] text-white/25 leading-snug">
            An ordered sequence of bands, auto-fit to the media length. Each transition glides
            between beats.
          </p>

          <div v-if="binaural.journey.length === 0" class="text-[10px] text-white/30 italic py-1">
            No phases yet — add one below.
          </div>

          <div
            v-for="(phase, i) in binaural.journey"
            :key="i"
            class="flex items-center gap-2 rounded-md border border-white/[0.06] bg-black/20 p-2"
          >
            <span class="text-[9px] text-white/30 font-mono w-4 shrink-0">{{ i + 1 }}</span>
            <select
              :value="phase.band"
              class="cz-input flex-1 min-w-[80px]"
              @change="setPhaseBand(i, $event)"
            >
              <option v-for="(def, band) in BANDS" :key="band" :value="band">
                {{ def.label }} ({{ def.beatHz }}Hz)
              </option>
            </select>
            <label class="cz-field flex-1">
              <span>{{ phase.durationS }}s</span>
              <input
                :value="phase.durationS"
                type="range"
                min="5"
                max="600"
                step="5"
                class="cz-range"
                @input="setPhaseDuration(i, $event)"
              />
            </label>
            <div class="flex flex-col gap-0.5 shrink-0">
              <button class="cz-mini" title="Move up" :disabled="i === 0" @click="movePhase(i, -1)">▲</button>
              <button class="cz-mini" title="Move down" :disabled="i === binaural.journey.length - 1" @click="movePhase(i, 1)">▼</button>
            </div>
            <button class="text-[10px] text-white/30 hover:text-red-400/80 shrink-0" title="Remove phase" @click="removePhase(i)">✕</button>
          </div>

          <button
            class="w-full py-1.5 rounded-md border border-dashed border-white/10 hover:border-white/25 text-white/40 hover:text-white/70 text-[10px] uppercase tracking-[0.2em] transition-all"
            @click="addPhase"
          >
            + Add phase
          </button>
        </template>

        <!-- Volume -->
        <label class="cz-field w-full">
          <span>Volume {{ binaural.volume }}%</span>
          <input
            :value="binaural.volume"
            type="range"
            min="0"
            max="100"
            step="1"
            class="cz-range"
            @input="onVolume"
          />
        </label>

        <p v-if="activeBeatHz > 0" class="text-[9px] text-white/25 font-mono">
          Now playing: {{ activeBeatHz }} Hz beat<span v-if="isochronicDepth(activeBeatHz) > 0"> + isochronic pulse</span>
        </p>

        <!-- Texture bed -->
        <div class="space-y-1.5 pt-1 border-t border-white/[0.04]">
          <span class="text-[9px] uppercase tracking-[0.2em] text-white/30">Textures under the beat</span>
          <label v-for="t in TEXTURES" :key="t.id" class="cz-field w-full" :title="t.hint">
            <span>{{ t.label }} {{ Math.round(binaural.textures[t.id] * 100) }}%</span>
            <input
              :value="binaural.textures[t.id]"
              type="range"
              min="0"
              max="1"
              step="0.05"
              class="cz-range"
              @input="setTexture(t.id, $event)"
            />
          </label>
        </div>
      </template>
    </div>

    <!-- ── Session envelope ── -->
    <div class="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 space-y-2">
      <label class="cz-field w-full">
        <span>Session fade {{ fadeS > 0 ? `${fadeS}s` : 'off' }}</span>
        <input
          :value="fadeS"
          type="range"
          min="0"
          max="15"
          step="0.5"
          class="cz-range"
          @input="emit('update:fadeS', Number(($event.target as HTMLInputElement).value))"
        />
      </label>
      <p class="text-[9px] text-white/25 leading-snug">
        Sound and picture fade in from silence and black after the In point, and back out before Out.
      </p>
    </div>

    <!-- ── Tone synthesis presets (existing glass tones) ── -->
    <div class="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 space-y-2">
      <span class="text-[10px] uppercase tracking-[0.2em] text-white/40">Reactive tone layer</span>
      <p class="text-[9px] text-white/25 leading-snug">
        Tone.js synthesis that responds to the media's speech envelope — a separate voice from
        the binaural beat.
      </p>
      <div class="flex gap-1.5 flex-wrap">
        <button
          v-for="(label, key) in tonePresets"
          :key="key"
          class="cz-chip"
          :class="activeTonePreset === key ? 'cz-chip-on' : 'cz-chip-off'"
          @click="$emit('tone', key as string)"
        >
          {{ label }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Band, BinauralConfig } from '@/composables/studioTypes'
import { BANDS } from '@/composables/useStudioBinaural'
import { isochronicDepth, type TextureId } from '@/composables/useBinauralEngine'

const TEXTURES: { id: TextureId; label: string; hint: string }[] = [
  { id: 'noise', label: 'Pink noise', hint: 'Soft filtered noise — masks the room and smooths the beat' },
  { id: 'pad', label: 'Sub pad', hint: 'Breathing drone an octave under the carrier' },
  { id: 'shimmer', label: 'Shimmer', hint: 'Quiet high partials with a slow tremolo' },
]

/**
 * The parent passes its reactive `composition.binaural`; we mutate it in place
 * (same contract as TextControls with `layers`). After any mutation that changes
 * the beat, emit `apply` so the parent re-syncs the running engine; volume and
 * tone-preset changes have their own dedicated emits to avoid re-ramping.
 */
const props = defineProps<{
  binaural: BinauralConfig
  activeBeatHz: number
  tonePresets: Record<string, string>
  activeTonePreset: string
  fadeS: number
}>()

const emit = defineEmits<{
  (e: 'apply'): void
  (e: 'volume', v: number): void
  (e: 'tone', key: string): void
  (e: 'textures'): void
  (e: 'update:fadeS', v: number): void
}>()

const activeDef = computed(() => BANDS[props.binaural.band])

function toggleEnabled() {
  props.binaural.enabled = !props.binaural.enabled
  emit('apply')
}

function setMode(mode: 'preset' | 'journey') {
  props.binaural.mode = mode
  emit('apply')
}

function pickBand(band: Band) {
  props.binaural.band = band
  emit('apply')
}

function setTexture(id: TextureId, e: Event) {
  props.binaural.textures[id] = Number((e.target as HTMLInputElement).value)
  emit('textures')
}

function onVolume(e: Event) {
  emit('volume', Number((e.target as HTMLInputElement).value))
}

// ── Journey editing ──
function addPhase() {
  props.binaural.journey.push({ band: 'alpha', durationS: 60 })
  emit('apply')
}

function removePhase(i: number) {
  props.binaural.journey.splice(i, 1)
  emit('apply')
}

function movePhase(i: number, dir: -1 | 1) {
  const j = i + dir
  const arr = props.binaural.journey
  if (j < 0 || j >= arr.length) return
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
  emit('apply')
}

function setPhaseBand(i: number, e: Event) {
  props.binaural.journey[i].band = (e.target as HTMLSelectElement).value as Band
  emit('apply')
}

function setPhaseDuration(i: number, e: Event) {
  props.binaural.journey[i].durationS = Number((e.target as HTMLInputElement).value)
  emit('apply')
}
</script>

<style scoped>
.cz-input {
  @apply bg-white/[0.04] border border-white/10 focus:border-white/30 rounded
         text-white/80 text-[11px] px-1.5 py-1 outline-none transition-colors;
}
.cz-input option {
  @apply bg-[#111] text-white/80;
}
.cz-field {
  @apply flex flex-col gap-1 flex-1 min-w-[80px] text-[9px] uppercase tracking-wider text-white/40;
}
.cz-range {
  @apply w-full h-1 accent-white/50 cursor-pointer;
}
.cz-chip {
  @apply px-2.5 py-1 rounded-full text-[10px] tracking-wider border transition-all shrink-0;
}
.cz-chip-on {
  @apply bg-white/10 border-white/20 text-white/90;
}
.cz-chip-off {
  @apply bg-transparent border-white/[0.08] text-white/30 hover:text-white/50;
}
.cz-mini {
  @apply w-4 h-3 flex items-center justify-center text-[7px] text-white/30
         hover:text-white/70 disabled:opacity-20 transition-colors leading-none;
}
</style>
