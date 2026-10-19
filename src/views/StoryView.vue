<template>
  <div class="min-h-screen bg-[#0a0a0a] text-slate-300 pt-20 pb-16 px-4">
    <div class="max-w-6xl mx-auto grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">

      <!-- ── Authoring ── -->
      <section class="space-y-4 min-w-0">
        <header>
          <h1 class="text-white/90 text-lg font-light tracking-[0.25em] uppercase">Story Studio</h1>
          <p class="text-slate-500 text-xs mt-1 leading-relaxed">
            Write a story in beats. Each beat is voiced, paced to its stage, and laid over your video with
            synced phrases and a binaural beat that glides as the story deepens.
          </p>
        </header>

        <div class="flex gap-2 flex-wrap">
          <button
            v-for="s in STORY_SAMPLES"
            :key="s.id"
            class="chip"
            :class="{ 'chip--on': text === s.text }"
            @click="text = s.text"
          >{{ s.title }}</button>
        </div>

        <label class="block">
          <span class="sr-only">Story text</span>
          <textarea
            v-model="text"
            rows="16"
            spellcheck="true"
            class="w-full bg-white/[0.03] border border-white/[0.06] rounded-lg p-3 text-sm leading-relaxed text-slate-200 font-mono focus:outline-none focus:border-white/20"
          />
        </label>
        <p class="text-[11px] text-slate-600 leading-relaxed">
          Blank lines separate beats. Marker lines set the stage:
          <code v-for="m in markers" :key="m" class="text-slate-400 mx-0.5">[{{ m }}]</code>
          and <code class="text-slate-400">[pause 6]</code> holds in silence. With no markers the arc is automatic.
        </p>

        <div class="grid grid-cols-2 gap-3 text-xs">
          <label class="field">
            <span>Background video</span>
            <span class="relative block truncate px-3 py-2 rounded-md bg-white/[0.04] border border-white/[0.06] cursor-pointer hover:bg-white/[0.07]">
              {{ videoName || 'None — breathing field' }}
              <input type="file" accept="video/*" class="absolute inset-0 opacity-0 cursor-pointer" @change="onVideoPick" />
            </span>
          </label>
          <label class="field">
            <span>Overlay</span>
            <select v-model="style" class="px-3 py-2 rounded-md bg-white/[0.04] border border-white/[0.06]">
              <option value="soft">Soft serif</option>
              <option value="glass">Glass (exclusion caps)</option>
            </select>
          </label>
          <label class="field">
            <span>Reading pace · {{ wpm }} wpm</span>
            <input v-model.number="wpm" type="range" min="90" max="220" step="5" />
          </label>
          <div class="field">
            <span>Voice</span>
            <button class="chip w-full" :class="{ 'chip--on': voiceOn }" :disabled="kokoroStatus === 'downloading'" @click="toggleVoice">
              {{ voiceLabel }}
            </button>
          </div>
        </div>
        <p v-if="kokoroStatus === 'error'" class="text-[11px] text-amber-400/80">
          The local voice couldn't load, so this build will be text and tones only.
        </p>

        <button
          class="w-full px-6 py-3 rounded-full border text-sm tracking-wider transition-all"
          :class="stale ? 'bg-white/10 border-white/20 text-white/90 hover:bg-white/15' : 'bg-white/[0.03] border-white/10 text-white/50'"
          :disabled="building || !parsed.length || player.state.value !== 'idle'"
          @click="build"
        >
          {{ building ? buildStep : timeline ? (stale ? 'Rebuild timeline' : 'Timeline is up to date') : 'Build timeline' }}
        </button>
        <p v-if="buildError" class="text-[11px] text-rose-400/80">{{ buildError }}</p>
      </section>

      <!-- ── Preview + timeline ── -->
      <section class="space-y-4 min-w-0">
        <div class="relative rounded-lg overflow-hidden bg-black border border-white/[0.05]">
          <canvas ref="canvasRef" class="block w-full h-auto" aria-hidden="true" />
          <div v-if="!timeline" class="absolute inset-0 flex items-center justify-center text-slate-600 text-xs tracking-[0.2em] uppercase">
            Build the timeline to preview
          </div>
          <div v-if="isRecording" class="absolute top-3 left-3 flex items-center gap-2 text-[10px] uppercase tracking-widest text-rose-300">
            <span class="w-2 h-2 rounded-full bg-rose-500 animate-pulse" /> Recording
          </div>
        </div>
        <video ref="videoRef" :src="videoUrl ?? undefined" class="absolute w-px h-px opacity-0 pointer-events-none" muted playsinline preload="auto" @loadedmetadata="onVideoLoaded" />

        <template v-if="timeline">
          <!-- Stage bar -->
          <div
            class="relative flex h-3 rounded-full overflow-hidden bg-white/[0.04] cursor-pointer"
            role="slider"
            tabindex="0"
            aria-label="Story position"
            :aria-valuenow="Math.round(cursorMs / 1000)"
            aria-valuemin="0"
            :aria-valuemax="Math.round(timeline.durationMs / 1000)"
            :aria-valuetext="formatClock(cursorMs)"
            @click="onBarClick"
            @keydown.left.prevent="seek(cursorMs - 5000)"
            @keydown.right.prevent="seek(cursorMs + 5000)"
          >
            <div :style="{ width: pct(timeline.leadInMs) }" />
            <div
              v-for="b in timeline.beats"
              :key="b.index"
              :class="`stage-${b.stage}`"
              class="h-full border-r border-black/40"
              :style="{ width: pct(b.endMs - b.startMs) }"
              :title="`${b.stage} · ${formatClock(b.startMs)}`"
            />
            <div class="absolute top-0 bottom-0 w-0.5 bg-white" :style="{ left: pct(cursorMs) }" />
          </div>

          <div class="flex items-center gap-3 text-xs">
            <button class="chip" :disabled="isRecording" @click="togglePlay">{{ isPlaying ? 'Pause' : 'Play' }}</button>
            <span class="font-mono text-slate-500">{{ formatClock(cursorMs) }} / {{ formatClock(timeline.durationMs) }}</span>
            <span class="text-slate-600">{{ beatHzLabel }}</span>
            <span class="flex-1" />
            <button v-if="!isRecording" class="chip chip--rec" :disabled="stale || isPlaying" @click="record">Export video</button>
            <button v-else class="chip" @click="player.stop()">Cancel export</button>
          </div>
          <p class="text-[11px] text-slate-600 leading-relaxed">
            Export records in real time ({{ formatClock(timeline.durationMs) }}) and saves an
            {{ exportExt }} file. Keep this tab in front while it runs. Headphones carry the binaural beat.
            <span v-if="stale" class="text-amber-400/70">The story changed — rebuild before exporting.</span>
          </p>

          <!-- Beat list -->
          <ol class="space-y-1 max-h-[40vh] overflow-y-auto pr-1">
            <li v-for="b in timeline.beats" :key="b.index">
              <button
                class="w-full text-left flex gap-3 items-baseline px-2 py-1.5 rounded-md hover:bg-white/[0.04]"
                :class="{ 'bg-white/[0.06]': currentBeat === b.index }"
                @click="seek(b.startMs)"
              >
                <span class="font-mono text-[10px] text-slate-600 w-9 shrink-0">{{ formatClock(b.startMs) }}</span>
                <span class="stage-chip shrink-0" :class="`stage-${b.stage}`">{{ b.stage }}</span>
                <span class="text-xs text-slate-400 truncate">{{ b.text || `— silence ${Math.round((b.pauseMs ?? 0) / 1000)}s —` }}</span>
                <span v-if="b.voiced" class="ml-auto text-[10px] text-slate-600 shrink-0" aria-label="voiced">♪</span>
              </button>
            </li>
          </ol>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, computed, watch, nextTick, onUnmounted } from 'vue'
import { STORY_SAMPLES } from '@/data/storySamples'
import {
  parseStory, buildTimeline, beatIndexAt, entrainmentAt, formatClock, STAGES,
  type Timeline, type StoryStage,
} from '@/story/storyBeats'
import { renderSoundtrack, voiceBuffer } from '@/story/renderSoundtrack'
import { useStoryPlayer, drawStoryFrame, canvasSizeFor, STORY_FADE_S, type OverlayStyle } from '@/story/useStoryPlayer'
import { pickMime } from '@/composables/useGlassExport'
import { useVoice } from '@/composables/useVoice'

const markers = Object.keys(STAGES) as StoryStage[]

const text = ref(STORY_SAMPLES[0].text)
const wpm = ref(140)
const style = ref<OverlayStyle>('soft')
const voiceOn = ref(false)

const parsed = computed(() => parseStory(text.value))

// ── Voice (local Kokoro only — Web Speech can't be recorded) ──
const { synthesize, kokoroStatus, enableKokoro } = useVoice()

const voiceLabel = computed(() => {
  if (kokoroStatus.value === 'downloading') return 'Downloading voice (~90 MB)…'
  return voiceOn.value ? 'Local voice on' : 'Add local voice'
})

async function toggleVoice() {
  if (voiceOn.value) { voiceOn.value = false; return }
  voiceOn.value = kokoroStatus.value === 'ready' || (await enableKokoro())
}

// ── Background video ──
const videoRef = ref<HTMLVideoElement>()
const canvasRef = ref<HTMLCanvasElement>()
const videoUrl = ref<string | null>(null)
const videoName = ref('')

function onVideoPick(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  player.stop()
  if (videoUrl.value) URL.revokeObjectURL(videoUrl.value)
  videoUrl.value = URL.createObjectURL(file)
  videoName.value = file.name
}

function backgroundVideo(): HTMLVideoElement | null {
  const v = videoRef.value
  return v && videoUrl.value && v.videoWidth > 0 ? v : null
}

function onVideoLoaded() {
  sizeCanvas()
  // Seek a hair in so the first frame decodes for the still preview.
  const v = videoRef.value
  if (v) {
    v.currentTime = 0.01
    v.addEventListener('seeked', () => drawStill(), { once: true })
  }
}

function sizeCanvas() {
  const c = canvasRef.value
  if (!c) return
  const { w, h } = canvasSizeFor(backgroundVideo())
  c.width = w
  c.height = h
}

// ── Build: parse → voice → timeline → offline soundtrack ──
const timeline = shallowRef<Timeline | null>(null)
const soundtrack = shallowRef<AudioBuffer | null>(null)
const building = ref(false)
const buildStep = ref('')
const buildError = ref('')
const builtKey = ref('')
const inputKey = computed(() => JSON.stringify([text.value, wpm.value, voiceOn.value]))
const stale = computed(() => !timeline.value || builtKey.value !== inputKey.value)

async function build() {
  building.value = true
  buildError.value = ''
  const key = inputKey.value
  try {
    const beats = parseStory(text.value)
    const voices: (AudioBuffer | null)[] = beats.map(() => null)
    if (voiceOn.value && kokoroStatus.value === 'ready') {
      for (let i = 0; i < beats.length; i++) {
        if (!beats[i].text) continue
        buildStep.value = `Voicing beat ${i + 1} of ${beats.length}…`
        const raw = await synthesize(beats[i].text)
        if (raw) voices[i] = voiceBuffer(raw.audio, raw.sampling_rate)
      }
    }
    const tl = buildTimeline(beats, { wpm: wpm.value, voiceMs: voices.map((v) => (v ? v.duration * 1000 : null)) })
    buildStep.value = 'Rendering soundtrack…'
    soundtrack.value = await renderSoundtrack(tl, voices, { fadeS: STORY_FADE_S })
    timeline.value = tl
    builtKey.value = key
    cursorMs.value = Math.min(cursorMs.value, tl.durationMs)
    await nextTick()
    sizeCanvas()
    drawStill()
  } catch (err) {
    console.error('[story] build failed', err)
    buildError.value = 'Building the timeline failed. Try a shorter story, or turn the voice off.'
  } finally {
    building.value = false
  }
}

// ── Playback ──
const player = useStoryPlayer()
const isPlaying = computed(() => player.state.value === 'playing')
const isRecording = computed(() => player.state.value === 'recording')
const cursorMs = ref(0)

watch(player.clockMs, (t) => { if (player.state.value !== 'idle') cursorMs.value = t })
watch(style, () => drawStill())

function drawStill() {
  const c = canvasRef.value
  const tl = timeline.value
  const ctx = c?.getContext('2d')
  if (!ctx || !tl || player.state.value !== 'idle') return
  drawStoryFrame(ctx, tl, cursorMs.value, backgroundVideo(), style.value)
}

function start(opts: { record: boolean }) {
  if (!timeline.value || !soundtrack.value || !canvasRef.value) return
  void player.play({
    canvas: canvasRef.value,
    video: backgroundVideo(),
    soundtrack: soundtrack.value,
    timeline: timeline.value,
    style: style.value,
    record: opts.record,
    fromMs: cursorMs.value >= timeline.value.durationMs - 500 ? 0 : cursorMs.value,
  })
}

function togglePlay() {
  if (isPlaying.value) { player.stop(); drawStill() }
  else start({ record: false })
}

function record() {
  cursorMs.value = 0
  start({ record: true })
}

function seek(ms: number) {
  if (!timeline.value || isRecording.value) return
  cursorMs.value = Math.max(0, Math.min(ms, timeline.value.durationMs))
  if (isPlaying.value) start({ record: false })
  else drawStill()
}

function onBarClick(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement
  const r = el.getBoundingClientRect()
  seek(((e.clientX - r.left) / r.width) * (timeline.value?.durationMs ?? 0))
}

const currentBeat = computed(() => (timeline.value ? beatIndexAt(timeline.value, cursorMs.value) : -1))
const beatHzLabel = computed(() => {
  if (!timeline.value) return ''
  return `${entrainmentAt(timeline.value, cursorMs.value).beatHz.toFixed(1)} Hz beat`
})

const pct = (ms: number) => `${(ms / (timeline.value?.durationMs || 1)) * 100}%`
const exportExt = typeof MediaRecorder !== 'undefined' && pickMime().startsWith('video/mp4') ? 'MP4' : 'WebM'

onUnmounted(() => {
  player.stop()
  if (videoUrl.value) URL.revokeObjectURL(videoUrl.value)
})
</script>

<style scoped>
.chip {
  @apply px-3 py-1.5 rounded-full border border-white/10 bg-white/[0.03] text-slate-400 text-xs tracking-wide transition-colors;
}
.chip:hover:not(:disabled) { @apply bg-white/[0.08] text-slate-200; }
.chip:disabled { @apply opacity-40 cursor-not-allowed; }
.chip--on { @apply bg-white/10 border-white/25 text-white/90; }
.chip--rec { @apply border-rose-400/30 text-rose-200/80; }

.field { @apply flex flex-col gap-1.5 text-slate-500; }

.stage-chip { @apply text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded text-black/80; }
.stage-induce   { background: #7dd3fc; }
.stage-deepen   { background: #818cf8; }
.stage-emerge   { background: #fcd34d; }
.stage-reinduce { background: #a78bfa; }
.stage-final    { background: #4c1d95; color: #e9d5ff; }
.stage-wake     { background: #86efac; }
</style>
