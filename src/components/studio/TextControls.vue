<template>
  <div class="space-y-3">
    <!-- Layer list -->
    <div
      v-for="(layer, i) in layers"
      :key="layer.id"
      class="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 space-y-2.5"
    >
      <!-- Header -->
      <div class="flex items-center justify-between gap-2">
        <span class="text-[10px] uppercase tracking-[0.2em] text-white/40">Layer {{ i + 1 }}</span>
        <button
          class="text-[10px] text-white/30 hover:text-red-400/80 uppercase tracking-wider transition-colors"
          title="Remove layer"
          @click="removeLayer(i)"
        >
          Remove
        </button>
      </div>

      <!-- Content -->
      <textarea
        :value="layer.content.join('\n')"
        placeholder="One affirmation per line…"
        rows="2"
        class="w-full resize-y bg-transparent border border-white/10 focus:border-white/30 rounded text-white text-sm px-2 py-1.5 outline-none placeholder-slate-600 transition-colors font-light leading-relaxed"
        @input="setContent(layer, $event)"
      />

      <!-- Font row -->
      <div class="flex items-center gap-2 flex-wrap">
        <select v-model="layer.font.family" class="cz-input flex-1 min-w-[120px]">
          <option v-for="f in FONT_FAMILIES" :key="f.value" :value="f.value">{{ f.label }}</option>
        </select>
        <select v-model.number="layer.font.weight" class="cz-input w-[86px]">
          <option v-for="w in WEIGHTS" :key="w" :value="w">{{ w }}</option>
        </select>
        <button
          class="cz-chip"
          :class="layer.font.upper ? 'cz-chip-on' : 'cz-chip-off'"
          @click="layer.font.upper = !layer.font.upper"
        >
          AA
        </button>
      </div>

      <!-- Size + letter spacing -->
      <div class="flex items-center gap-3">
        <label class="cz-field">
          <span>Size {{ layer.font.sizeVw }}vw</span>
          <input v-model.number="layer.font.sizeVw" type="range" min="2" max="20" step="0.5" class="cz-range" />
        </label>
        <label class="cz-field">
          <span>Track {{ layer.font.letterSpacing }}</span>
          <input v-model.number="layer.font.letterSpacing" type="range" min="-0.1" max="0.4" step="0.01" class="cz-range" />
        </label>
      </div>

      <!-- Anchor grid + offsets -->
      <div class="flex items-center gap-3">
        <div class="grid grid-cols-3 gap-0.5 shrink-0">
          <button
            v-for="a in ANCHORS"
            :key="a"
            class="w-5 h-5 rounded-sm border transition-all"
            :class="layer.pos.anchor === a
              ? 'bg-white/70 border-white/70'
              : 'bg-white/[0.03] border-white/10 hover:border-white/30'"
            :title="a"
            @click="layer.pos.anchor = a"
          />
        </div>
        <label class="cz-field">
          <span>dx {{ layer.pos.dx }}%</span>
          <input v-model.number="layer.pos.dx" type="range" min="-50" max="50" step="1" class="cz-range" />
        </label>
        <label class="cz-field">
          <span>dy {{ layer.pos.dy }}%</span>
          <input v-model.number="layer.pos.dy" type="range" min="-50" max="50" step="1" class="cz-range" />
        </label>
      </div>

      <!-- Color / opacity / blend -->
      <div class="flex items-center gap-2 flex-wrap">
        <input v-model="layer.style.color" type="color" class="w-7 h-7 rounded bg-transparent border border-white/10 cursor-pointer p-0" />
        <label class="cz-field">
          <span>Opacity {{ Math.round(layer.style.opacity * 100) }}%</span>
          <input v-model.number="layer.style.opacity" type="range" min="0" max="1" step="0.05" class="cz-range" />
        </label>
        <select v-model="layer.style.blend" class="cz-input w-[104px]">
          <option v-for="b in BLEND_MODES" :key="b" :value="b">{{ b }}</option>
        </select>
      </div>

      <!-- Timing -->
      <div class="flex items-center gap-2 flex-wrap">
        <select v-model="layer.timing.mode" class="cz-input w-[112px]">
          <option value="persistent">persistent</option>
          <option value="sequence">sequence</option>
          <option value="subliminal">subliminal</option>
        </select>

        <label v-if="layer.timing.mode === 'sequence'" class="cz-field w-[92px]">
          <span>Hold {{ layer.timing.holdMs }}ms</span>
          <input v-model.number="layer.timing.holdMs" type="range" min="200" max="6000" step="100" class="cz-range" />
        </label>
        <label v-if="layer.timing.mode !== 'subliminal'" class="cz-field w-[92px]">
          <span>Fade {{ layer.timing.fadeMs }}ms</span>
          <input v-model.number="layer.timing.fadeMs" type="range" min="0" max="2000" step="50" class="cz-range" />
        </label>
        <label v-if="layer.timing.mode === 'subliminal'" class="cz-field w-[92px]">
          <span>Every {{ layer.timing.intervalMs }}ms</span>
          <input v-model.number="layer.timing.intervalMs" type="range" min="500" max="10000" step="100" class="cz-range" />
        </label>
        <label v-if="layer.timing.mode === 'subliminal'" class="cz-field w-[92px]">
          <span>Flash {{ layer.timing.flashMs }}ms</span>
          <input v-model.number="layer.timing.flashMs" type="range" min="33" max="1000" step="1" class="cz-range" />
        </label>
      </div>
      <p v-if="layer.timing.mode === 'subliminal'" class="text-[9px] text-white/25 leading-snug">
        Export is 30fps — flashes below ~33ms (one frame) can be dropped, so 33ms is the practical floor.
      </p>

      <!-- Motion -->
      <div class="flex items-center gap-2 flex-wrap">
        <select v-model="layer.motion.type" class="cz-input w-[96px]">
          <option v-for="m in MOTION_TYPES" :key="m" :value="m">{{ m }}</option>
        </select>
        <label v-if="layer.motion.type !== 'none'" class="cz-field w-[92px]">
          <span>Amount {{ Math.round(layer.motion.amount * 100) }}%</span>
          <input v-model.number="layer.motion.amount" type="range" min="0" max="1" step="0.05" class="cz-range" />
        </label>
        <button
          v-if="layer.motion.type !== 'none'"
          class="cz-chip"
          :class="layer.motion.syncToBeat ? 'cz-chip-on' : 'cz-chip-off'"
          title="Sync motion to the binaural beat"
          @click="layer.motion.syncToBeat = !layer.motion.syncToBeat"
        >
          ♪ beat
        </button>
      </div>
    </div>

    <!-- Add layer -->
    <button
      class="w-full py-2 rounded-lg border border-dashed border-white/10 hover:border-white/25 text-white/40 hover:text-white/70 text-[11px] uppercase tracking-[0.2em] transition-all"
      @click="addLayer"
    >
      + Add text layer
    </button>

    <p v-if="flashRate > 3" class="text-[10px] leading-relaxed text-amber-300/80" role="alert">
      Subliminal layers combine to ~{{ flashRate.toFixed(1) }} flashes/sec. More than 3/sec can trigger
      photosensitive seizures — lengthen an interval or remove a layer.
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { subliminalFlashRate } from '@/composables/useGlassComposer'
import {
  makeDefaultTextLayer,
  type Anchor,
  type BlendMode,
  type MotionType,
  type TextLayer,
} from '@/composables/studioTypes'

// The parent passes its reactive composition.textLayers array; we mutate it in place.
const props = defineProps<{ layers: TextLayer[] }>()

const flashRate = computed(() => subliminalFlashRate(props.layers))

// Curated, no-external-load font stacks (system / web-safe only).
const FONT_FAMILIES: { label: string; value: string }[] = [
  { label: 'System Sans', value: 'system-ui, -apple-system, sans-serif' },
  { label: 'Helvetica', value: '"Helvetica Neue", Helvetica, Arial, sans-serif' },
  { label: 'Georgia Serif', value: 'Georgia, "Times New Roman", serif' },
  { label: 'Slab / Times', value: '"Times New Roman", Times, serif' },
  { label: 'Mono', value: '"SF Mono", ui-monospace, Menlo, Consolas, monospace' },
  { label: 'Impact', value: 'Impact, "Arial Narrow Bold", sans-serif' },
  { label: 'Courier', value: '"Courier New", Courier, monospace' },
]

const WEIGHTS = [100, 300, 400, 500, 700, 900]
const BLEND_MODES: BlendMode[] = ['normal', 'exclusion', 'difference', 'screen', 'overlay', 'multiply']
const MOTION_TYPES: MotionType[] = ['none', 'pulse', 'drift', 'zoom', 'shake', 'waver']
// Row-major 9-grid so the button grid visually matches the anchor positions.
const ANCHORS: Anchor[] = ['tl', 'tc', 'tr', 'cl', 'cc', 'cr', 'bl', 'bc', 'br']

function setContent(layer: TextLayer, e: Event) {
  const val = (e.target as HTMLTextAreaElement).value
  layer.content = val.split('\n')
}

function addLayer() {
  // New layers default to a flashing affirmation pool alongside any title layer.
  const layer = makeDefaultTextLayer({ content: [''] })
  layer.timing.mode = 'subliminal'
  props.layers.push(layer)
}

function removeLayer(i: number) {
  props.layers.splice(i, 1)
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
  @apply px-2 py-1 rounded-full text-[10px] tracking-wider border transition-all shrink-0;
}
.cz-chip-on {
  @apply bg-white/10 border-white/20 text-white/90;
}
.cz-chip-off {
  @apply bg-transparent border-white/[0.08] text-white/30 hover:text-white/50;
}
</style>
