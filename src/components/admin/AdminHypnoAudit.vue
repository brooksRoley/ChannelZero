<template>
  <div class="space-y-10">

    <!-- 1. Binaural spec audit -->
    <section>
      <h2 class="audit-h2">Binaural spec audit</h2>
      <p class="audit-p">
        Every stereo pair the app ships, checked against the band it claims and the carrier range where binaural beats are perceived.
        Read from the engines' exported specs (<code>BINAURAL_LAYERS</code>, <code>BANDS</code>), so it stays current.
      </p>
      <div class="rounded-xl border border-gray-800 overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
              <th class="text-left px-4 py-2">Layer</th>
              <th class="text-right px-4 py-2">L / R Hz</th>
              <th class="text-right px-4 py-2">Carrier</th>
              <th class="text-right px-4 py-2">Beat</th>
              <th class="text-left px-4 py-2">Band</th>
              <th class="text-left px-4 py-2">Checks</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-800/50">
            <tr v-for="a in specAudit" :key="a.source + a.label" class="align-top">
              <td class="px-4 py-2">
                <div class="text-white">{{ a.label }}</div>
                <div class="text-[11px] text-gray-500">{{ a.source }}</div>
              </td>
              <td class="px-4 py-2 text-right tabular-nums text-gray-300 whitespace-nowrap">{{ fmt(a.leftHz) }} / {{ fmt(a.rightHz) }}</td>
              <td class="px-4 py-2 text-right tabular-nums text-gray-300">{{ fmt(a.carrierHz) }}</td>
              <td class="px-4 py-2 text-right tabular-nums text-gray-300">{{ fmt(a.beatHz) }}</td>
              <td class="px-4 py-2 text-gray-300 capitalize">{{ a.band }}</td>
              <td class="px-4 py-2">
                <ul class="space-y-0.5">
                  <li v-for="c in a.checks" :key="c.message" class="text-xs" :class="LEVEL_TEXT[c.level]">
                    {{ LEVEL_ICON[c.level] }} {{ c.message }}
                  </li>
                </ul>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 2. Channel check -->
    <section>
      <h2 class="audit-h2">Headphone channel check</h2>
      <p class="audit-p">
        Binaural beats only exist if each ear gets its own tone. Play each side and confirm it comes out of the matching ear only.
      </p>
      <div class="flex gap-2">
        <button class="audit-btn" @click="playChannelCheck('left')">Play left ear</button>
        <button class="audit-btn" @click="playChannelCheck('right')">Play right ear</button>
      </div>
    </section>

    <!-- 3. Engine output measurement -->
    <section>
      <h2 class="audit-h2">Measure trance engine output</h2>
      <p class="audit-p">
        Turns one engine layer on, listens to the master output split into left and right, and measures the real tone in each channel,
        the resulting beat, and how well the channels are separated. Plays audio for about 2.5 s; lower your volume first.
      </p>
      <PanelError :message="measureError" />
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div v-for="layer in layers" :key="layer.id" class="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div class="flex items-center justify-between mb-2">
            <span class="font-medium text-white text-sm">{{ layer.label }}</span>
            <button class="audit-btn" :disabled="measuring !== null" @click="measure(layer.id)">
              {{ measuring === layer.id ? 'Listening…' : 'Measure' }}
            </button>
          </div>
          <div class="text-[11px] text-gray-500 mb-2">Spec {{ fmt(layer.leftHz) }} / {{ fmt(layer.rightHz) }} Hz</div>
          <template v-if="measurements[layer.id]">
            <div class="grid grid-cols-3 gap-2 text-xs mb-2">
              <div><span class="text-gray-500 block">Left</span><span class="text-white tabular-nums">{{ fmtPeak(measurements[layer.id]!.leftPeak?.hz) }}</span></div>
              <div><span class="text-gray-500 block">Right</span><span class="text-white tabular-nums">{{ fmtPeak(measurements[layer.id]!.rightPeak?.hz) }}</span></div>
              <div><span class="text-gray-500 block">Beat</span><span class="text-white tabular-nums">{{ fmtPeak(measurements[layer.id]!.measuredBeatHz) }}</span></div>
            </div>
            <ul class="space-y-0.5">
              <li v-for="c in measurements[layer.id]!.checks" :key="c.message" class="text-xs" :class="LEVEL_TEXT[c.level]">
                {{ LEVEL_ICON[c.level] }} {{ c.message }}
              </li>
            </ul>
          </template>
        </div>
      </div>
    </section>

    <!-- 4. Flash safety scan -->
    <section>
      <h2 class="audit-h2">Flash safety scan</h2>
      <p class="audit-p">
        Hypnotic visuals pulse on purpose, but more than 3 flashes per second can trigger photosensitive seizures (WCAG 2.3.1).
        Load a visual below, start it inside the frame, then scan. The browser will ask you to share this tab; the recording stays on this device.
        The scan averages the whole frame, so a small flashing area can still pass. Treat a pass as a first check, not a sign-off.
      </p>
      <PanelError :message="scanError" />
      <div class="flex flex-wrap items-center gap-2 mb-3">
        <select v-model="scanTarget" class="bg-gray-900 border border-gray-800 rounded-lg px-3 py-1.5 text-sm text-white" aria-label="Visual to scan">
          <option v-for="s in visualSections" :key="s.id" :value="s.id">{{ s.name }} ({{ s.preview }})</option>
        </select>
        <button class="audit-btn" :disabled="scanning" @click="runScan">{{ scanning ? 'Scanning…' : 'Scan 6 s' }}</button>
        <span v-if="scanResult" class="text-xs px-2 py-0.5 rounded-full" :class="LEVEL_PILL[scanResult.verdict]">
          {{ scanResult.maxPerSecond }} flashes/s peak · {{ scanResult.flashes }} total · {{ scanResult.verdict }}
        </span>
      </div>
      <div ref="scanFrameWrap" class="rounded-xl border border-gray-800 overflow-hidden bg-black aspect-video">
        <iframe
          :key="scanTarget"
          :src="scanSection?.preview"
          :title="`Flash scan target: ${scanSection?.name}`"
          class="w-full h-full"
          allow="autoplay; fullscreen"
        ></iframe>
      </div>
      <svg v-if="samples.length > 1" class="w-full h-16 mt-2" :viewBox="`0 0 ${SPARK_W} 64`" preserveAspectRatio="none" role="img" aria-label="Luminance over time">
        <polyline :points="sparkline" fill="none" stroke="#a78bfa" stroke-width="1.5" vector-effect="non-scaling-stroke" />
      </svg>
    </section>

  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { BINAURAL_LAYERS, type BinauralLayerSpec } from '@/composables/useTranceEngine'
import {
  useHypnoAudit, allBinauralPairs, auditBinauralPair,
  type CheckLevel, type LayerMeasurement, type FlashResult, type LumSample,
} from '@/composables/useHypnoAudit'
import { SITE_SECTIONS, VISUAL_SECTION_IDS } from '@/config/siteSections'
import PanelError from './PanelError.vue'

const { playChannelCheck, measureEngineLayer, scanFlashes } = useHypnoAudit()

const LEVEL_TEXT: Record<CheckLevel, string> = { pass: 'text-green-400', warn: 'text-yellow-400', fail: 'text-red-400' }
const LEVEL_ICON: Record<CheckLevel, string> = { pass: '✓', warn: '!', fail: '✕' }
const LEVEL_PILL: Record<CheckLevel, string> = {
  pass: 'bg-green-900/40 text-green-300',
  warn: 'bg-yellow-900/40 text-yellow-300',
  fail: 'bg-red-900/40 text-red-300',
}

const fmt = (hz: number) => (Number.isInteger(hz) ? String(hz) : hz.toFixed(2))
const fmtPeak = (hz?: number | null) => (hz == null ? '—' : `${hz.toFixed(2)} Hz`)

// 1. Spec audit
const specAudit = allBinauralPairs().map(auditBinauralPair)

// 3. Engine measurement
const layers = Object.values(BINAURAL_LAYERS)
const measurements = reactive<Partial<Record<BinauralLayerSpec['id'], LayerMeasurement>>>({})
const measuring = ref<BinauralLayerSpec['id'] | null>(null)
const measureError = ref('')

async function measure(id: BinauralLayerSpec['id']) {
  measureError.value = ''
  measuring.value = id
  try {
    measurements[id] = await measureEngineLayer(id)
  } catch (e: any) {
    measureError.value = e?.message || 'Measurement failed'
  } finally {
    measuring.value = null
  }
}

// 4. Flash scan
const visualSections = SITE_SECTIONS.filter(s => VISUAL_SECTION_IDS.includes(s.id))
const scanTarget = ref(visualSections[0]?.id)
const scanSection = computed(() => visualSections.find(s => s.id === scanTarget.value))
const scanFrameWrap = ref<HTMLElement | null>(null)
const scanning = ref(false)
const scanError = ref('')
const scanResult = ref<FlashResult | null>(null)
const samples = ref<LumSample[]>([])

const SPARK_W = 600
const sparkline = computed(() => {
  const s = samples.value
  const tMax = s[s.length - 1]?.t || 1
  return s.map(p => `${(p.t / tMax) * SPARK_W},${64 - p.lum * 60 - 2}`).join(' ')
})

async function runScan() {
  if (!scanFrameWrap.value) return
  scanError.value = ''
  scanResult.value = null
  samples.value = []
  scanning.value = true
  try {
    const { result } = await scanFlashes(scanFrameWrap.value, 6000, s => { samples.value = [...samples.value, s] })
    scanResult.value = result
  } catch (e: any) {
    scanError.value = e?.name === 'NotAllowedError' ? 'Screen share was declined; the scan needs to see this tab.' : (e?.message || 'Scan failed')
  } finally {
    scanning.value = false
  }
}
</script>

<style scoped>
.audit-h2 {
  @apply text-xs font-semibold uppercase tracking-widest text-gray-500 mb-2;
}
.audit-p {
  @apply text-xs text-gray-400 mb-4 max-w-3xl leading-relaxed;
}
.audit-btn {
  @apply text-xs px-3 py-1.5 rounded-lg border border-gray-700 text-gray-300 hover:text-white hover:border-purple-500 disabled:opacity-40 disabled:cursor-not-allowed;
}
</style>
