<template>
  <div class="min-h-screen bg-[#0a0a0a] text-slate-300 pt-20 pb-16 px-4">
    <div class="max-w-6xl mx-auto grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">

      <!-- ── Authoring ── -->
      <section class="space-y-4 min-w-0">
        <header>
          <h1 class="text-white/90 text-lg font-light tracking-[0.25em] uppercase">Story Studio</h1>
          <p class="text-slate-500 text-xs mt-1 leading-relaxed">
            The story is read aloud; its key phrases land on screen as they're spoken — flashed, slammed,
            whispered, typed — with subliminals underneath and a binaural beat that deepens with the story.
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
        <details class="text-[11px] text-slate-500 leading-relaxed">
          <summary class="cursor-pointer text-slate-400">Markup</summary>
          <ul class="mt-2 space-y-1">
            <li>Blank lines separate beats.</li>
            <li><code>*key phrase*</code> shows a phrase as it's spoken; <code>*flash:let go*</code> picks the effect —
              <code v-for="e in effectNames" :key="e" class="mx-0.5">{{ e }}</code>.</li>
            <li>Stage lines: <code v-for="m in markers" :key="m" class="mx-0.5">[{{ m }}]</code>. Without any, the arc is automatic.</li>
            <li><code>[subliminal calm, safe, deeper]</code> flashes those words for a frame or two from then on; <code>[subliminal off]</code> stops.</li>
            <li><code>[pause 6]</code> holds in silence.</li>
          </ul>
        </details>

        <div class="grid grid-cols-2 gap-3 text-xs">
          <label class="field">
            <span>Background video</span>
            <span class="relative block truncate px-3 py-2 rounded-md bg-white/[0.04] border border-white/[0.06] cursor-pointer hover:bg-white/[0.07]">
              {{ videoName || 'None — breathing field' }}
              <input type="file" accept="video/*" class="absolute inset-0 opacity-0 cursor-pointer" @change="onVideoPick" />
            </span>
          </label>
          <label class="field">
            <span>Reading pace (unvoiced beats) · {{ wpm }} wpm</span>
            <input v-model.number="wpm" type="range" min="90" max="220" step="5" />
          </label>
          <label class="flex items-center gap-2 text-slate-400">
            <input v-model="captions" type="checkbox" /> Subtitles under the effects
          </label>
        </div>

        <!-- Voice -->
        <fieldset class="space-y-3 rounded-lg border border-white/[0.06] p-3">
          <legend class="px-1 text-xs text-slate-400">Voice</legend>
          <div class="flex gap-2 flex-wrap" role="radiogroup" aria-label="Voice source">
            <button v-for="v in voiceModes" :key="v.id" class="chip" role="radio" :aria-checked="voiceMode === v.id" :class="{ 'chip--on': voiceMode === v.id }" @click="setVoiceMode(v.id)">
              {{ v.label }}
            </button>
          </div>

          <template v-if="voiceMode === 'pack'">
            <ol class="text-[11px] text-slate-500 leading-relaxed list-decimal pl-4 space-y-1">
              <li><button class="link" @click="downloadVoiceScript">Download the voice script</button> ({{ scriptChars }} characters ≈ {{ scriptChars }} credits on Multilingual v2, half on Flash).</li>
              <li>Run <code class="text-slate-400">node tools/voice/elevenlabs.mjs {{ scriptFileName }} --voice &lt;id&gt;</code> with <code>ELEVENLABS_API_KEY</code> set.</li>
              <li>
                <label class="link relative cursor-pointer">Load the pack folder
                  <input type="file" multiple webkitdirectory class="absolute inset-0 opacity-0 cursor-pointer w-full" @change="onPackPick" />
                </label>
                — or attach an mp3 to any beat in the list.
              </li>
            </ol>
            <p class="text-[11px]" :class="voicedCount === voiceableCount ? 'text-emerald-400/80' : 'text-slate-400'">
              {{ voicedCount }} of {{ voiceableCount }} beats have audio · {{ alignedCount }} with exact word timing
              <span v-if="packMeta?.voice_name" class="text-slate-600">· {{ packMeta.voice_name }}</span>
            </p>
            <p v-if="packSkipped.length" class="text-[11px] text-amber-400/70">Skipped {{ packSkipped.length }} file(s) that aren't beat audio: {{ packSkipped.slice(0, 3).join(', ') }}</p>
            <label class="flex items-center gap-2 text-[11px] text-slate-400">
              <input v-model="credit" type="checkbox" /> Credit “Voice: ElevenLabs” at the end (required on the free plan)
            </label>
          </template>

          <p v-else-if="voiceMode === 'local'" class="text-[11px] text-slate-500">
            {{ kokoroStatus === 'downloading' ? 'Downloading the on-device voice (~90 MB, once)…' : kokoroStatus === 'error' ? "The on-device voice couldn't load — beats will be silent." : 'On-device neural voice. No account needed; less expressive than ElevenLabs.' }}
          </p>
          <p v-else class="text-[11px] text-slate-500">Silent: key phrases are paced by reading speed.</p>
        </fieldset>

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
          <!-- Stage bar with key-phrase ticks -->
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
              class="h-full border-r border-black/40 opacity-70"
              :style="{ width: pct(b.endMs - b.startMs) }"
              :title="`${b.stage} · ${formatClock(b.startMs)}`"
            />
            <div v-for="(k, i) in timeline.keys" :key="`k${i}`" class="absolute top-0 bottom-0 w-px bg-white/70" :style="{ left: pct(k.spokenStartMs) }" />
            <div class="absolute top-0 bottom-0 w-0.5 bg-white" :style="{ left: pct(cursorMs) }" />
          </div>

          <div class="flex items-center gap-3 text-xs flex-wrap">
            <button class="chip" :disabled="isRecording" @click="togglePlay">{{ isPlaying ? 'Pause' : 'Play' }}</button>
            <span class="font-mono text-slate-500">{{ formatClock(cursorMs) }} / {{ formatClock(timeline.durationMs) }}</span>
            <span class="text-slate-600">{{ beatHzLabel }}</span>
            <span class="text-slate-600" :title="'Most flashes in any one second (WCAG 2.3.1 limit is 3)'">peak {{ flashRate }} flash/s</span>
            <span class="flex-1" />
            <button v-if="!isRecording" class="chip chip--rec" :disabled="stale || isPlaying" @click="record">Export video</button>
            <button v-else class="chip" @click="player.stop()">Cancel export</button>
          </div>
          <p class="text-[11px] text-slate-600 leading-relaxed">
            Export records in real time ({{ formatClock(timeline.durationMs) }}) and saves an {{ exportExt }} file.
            Keep this tab in front while it runs. Headphones carry the binaural beat.
            <span v-if="stale" class="text-amber-400/70">The story or voice changed — rebuild before exporting.</span>
          </p>

          <!-- Beat list -->
          <ol class="space-y-1 max-h-[44vh] overflow-y-auto pr-1">
            <li v-for="b in timeline.beats" :key="b.index" class="rounded-md" :class="{ 'bg-white/[0.06]': currentBeat === b.index }">
              <div class="flex gap-3 items-baseline px-2 pt-1.5">
                <button class="font-mono text-[10px] text-slate-600 w-9 shrink-0 hover:text-slate-300" @click="seek(b.startMs)">{{ formatClock(b.startMs) }}</button>
                <span class="stage-chip shrink-0" :class="`stage-${b.stage}`">{{ b.stage }}</span>
                <button class="text-xs text-slate-400 text-left truncate flex-1 hover:text-slate-200" @click="seek(b.startMs)">
                  {{ b.text || `— silence ${Math.round((b.pauseMs ?? 0) / 1000)}s —` }}
                </button>
                <template v-if="b.text && voiceMode === 'pack'">
                  <span v-if="clips.get(b.id)" class="text-[10px] shrink-0" :class="clips.get(b.id)!.alignment ? 'text-emerald-400/70' : 'text-slate-500'" :title="clips.get(b.id)!.name">
                    ♪{{ clips.get(b.id)!.alignment ? ' timed' : '' }}
                  </span>
                  <button class="text-[10px] text-slate-600 hover:text-slate-300 shrink-0" title="Copy the line to paste into ElevenLabs" @click="copyLine(b.text)">copy</button>
                  <label class="relative text-[10px] text-slate-600 hover:text-slate-300 shrink-0 cursor-pointer" :title="`Attach an mp3 for this beat (${b.id})`">
                    {{ clips.get(b.id) ? 'replace' : 'attach' }}
                    <input type="file" accept="audio/*" class="absolute inset-0 opacity-0 cursor-pointer w-full" @change="onBeatAudio(b.id, $event)" />
                  </label>
                </template>
                <span v-else-if="b.voiced" class="text-[10px] text-slate-600 shrink-0">♪</span>
              </div>
              <div v-if="keysByBeat.get(b.index)?.length" class="flex gap-1.5 flex-wrap pl-14 pb-1.5 pt-1">
                <button
                  v-for="(k, i) in keysByBeat.get(b.index)"
                  :key="i"
                  class="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.05] text-slate-400 hover:bg-white/10"
                  @click="seek(k.startMs)"
                >
                  <span class="text-slate-600">{{ k.effect }}</span> {{ k.text }}
                </button>
              </div>
              <div v-else class="pb-1.5" />
            </li>
          </ol>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, shallowRef, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { STORY_SAMPLES } from '@/data/storySamples'
import {
  parseStory, buildTimeline, beatIndexAt, entrainmentAt, formatClock, STAGES,
  type Timeline, type TimedKey, type StoryStage, type Alignment,
} from '@/story/storyBeats'
import { EFFECTS, maxFlashesPerSecond } from '@/story/effects'
import { loadEffectFonts } from '@/story/drawEffects'
import { renderSoundtrack, voiceBuffer } from '@/story/renderSoundtrack'
import { readPack, decodeAudioFile, voiceScript, type VoiceClip, type PackMeta } from '@/story/voicePack'
import { useStoryPlayer, drawStoryFrame, canvasSizeFor, STORY_FADE_S, type FrameOptions } from '@/story/useStoryPlayer'
import { pickMime } from '@/composables/useGlassExport'
import { useVoice } from '@/composables/useVoice'

const markers = Object.keys(STAGES) as StoryStage[]
const effectNames = Object.keys(EFFECTS)

const text = ref(STORY_SAMPLES[0].text)
const wpm = ref(140)
const captions = ref(false)
const credit = ref(true)

const parsed = computed(() => parseStory(text.value))

// ── Voice source ──
type VoiceMode = 'none' | 'local' | 'pack'
const voiceModes: { id: VoiceMode; label: string }[] = [
  { id: 'none', label: 'Silent' },
  { id: 'local', label: 'On-device voice' },
  { id: 'pack', label: 'ElevenLabs pack' },
]
const voiceMode = ref<VoiceMode>('pack')
const { synthesize, kokoroStatus, enableKokoro } = useVoice()

async function setVoiceMode(mode: VoiceMode) {
  voiceMode.value = mode
  if (mode === 'local' && kokoroStatus.value !== 'ready') await enableKokoro()
}

/** Pack audio by beat id. Survives story edits — unchanged lines keep their audio. */
const clips = shallowRef(new Map<string, VoiceClip>())
const packMeta = ref<PackMeta | null>(null)
const packSkipped = ref<string[]>([])
/** Bumped whenever clips change, so the timeline goes stale. */
const clipsVersion = ref(0)

const voiceable = computed(() => [...new Set(parsed.value.filter((b) => b.text).map((b) => b.id))])
const voiceableCount = computed(() => voiceable.value.length)
const voicedCount = computed(() => (clipsVersion.value, voiceable.value.filter((id) => clips.value.has(id)).length))
const alignedCount = computed(() => (clipsVersion.value, voiceable.value.filter((id) => clips.value.get(id)?.alignment).length))
const scriptChars = computed(() => voiceScript(parsed.value).beats.reduce((n, b) => n + b.text.length, 0))
const scriptFileName = 'story-voice-script.json'

function downloadVoiceScript() {
  const blob = new Blob([JSON.stringify(voiceScript(parsed.value), null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = scriptFileName
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

async function onPackPick(e: Event) {
  const files = [...((e.target as HTMLInputElement).files ?? [])]
  if (!files.length) return
  const { clips: loaded, meta, skipped } = await readPack(files)
  const next = new Map(clips.value)
  loaded.forEach((c, id) => next.set(id, c))
  clips.value = next
  packMeta.value = meta ?? packMeta.value
  packSkipped.value = skipped
  clipsVersion.value++
}

async function onBeatAudio(id: string, e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const next = new Map(clips.value)
    next.set(id, { buffer: await decodeAudioFile(file), alignment: null, name: file.name })
    clips.value = next
    clipsVersion.value++
  } catch {
    buildError.value = `Couldn't decode ${file.name}.`
  }
}

function copyLine(line: string) {
  void navigator.clipboard?.writeText(line).catch(() => { /* clipboard blocked */ })
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
const inputKey = computed(() => JSON.stringify([text.value, wpm.value, voiceMode.value, clipsVersion.value, kokoroStatus.value]))
const stale = computed(() => !timeline.value || builtKey.value !== inputKey.value)

async function build() {
  building.value = true
  buildError.value = ''
  const key = inputKey.value
  try {
    await loadEffectFonts()
    const beats = parseStory(text.value)
    const voices: (AudioBuffer | null)[] = beats.map(() => null)
    const alignments: (Alignment | null)[] = beats.map(() => null)
    if (voiceMode.value === 'pack') {
      beats.forEach((b, i) => {
        const clip = b.text ? clips.value.get(b.id) : undefined
        if (clip) { voices[i] = clip.buffer; alignments[i] = clip.alignment }
      })
    } else if (voiceMode.value === 'local' && kokoroStatus.value === 'ready') {
      for (let i = 0; i < beats.length; i++) {
        if (!beats[i].text) continue
        buildStep.value = `Voicing beat ${i + 1} of ${beats.length}…`
        const raw = await synthesize(beats[i].text)
        if (raw) voices[i] = voiceBuffer(raw.audio, raw.sampling_rate)
      }
    }
    const tl = buildTimeline(beats, {
      wpm: wpm.value,
      voiceMs: voices.map((v) => (v ? v.duration * 1000 : null)),
      alignments,
    })
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
    buildError.value = 'Building the timeline failed. Try a shorter story, or a different voice source.'
  } finally {
    building.value = false
  }
}

// ── Playback ──
const player = useStoryPlayer()
const isPlaying = computed(() => player.state.value === 'playing')
const isRecording = computed(() => player.state.value === 'recording')
const cursorMs = ref(0)

const frameOptions = computed<FrameOptions>(() => ({
  captions: captions.value,
  credit: voiceMode.value === 'pack' && credit.value && voicedCount.value > 0 ? 'Voice: ElevenLabs' : undefined,
}))

watch(player.clockMs, (t) => { if (player.state.value !== 'idle') cursorMs.value = t })
watch(frameOptions, () => drawStill())

function drawStill() {
  const c = canvasRef.value
  const tl = timeline.value
  const ctx = c?.getContext('2d')
  if (!ctx || !tl || player.state.value !== 'idle') return
  drawStoryFrame(ctx, tl, cursorMs.value, backgroundVideo(), frameOptions.value)
}

function start(opts: { record: boolean }) {
  if (!timeline.value || !soundtrack.value || !canvasRef.value) return
  void player.play({
    canvas: canvasRef.value,
    video: backgroundVideo(),
    soundtrack: soundtrack.value,
    timeline: timeline.value,
    frame: frameOptions.value,
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
const keysByBeat = computed(() => {
  const m = new Map<number, TimedKey[]>()
  for (const k of timeline.value?.keys ?? []) m.set(k.beat, [...(m.get(k.beat) ?? []), k])
  return m
})
const flashRate = computed(() => (timeline.value ? maxFlashesPerSecond(timeline.value.keys, timeline.value.subliminals) : 0))

const pct = (ms: number) => `${(ms / (timeline.value?.durationMs || 1)) * 100}%`
const exportExt = typeof MediaRecorder !== 'undefined' && pickMime().startsWith('video/mp4') ? 'MP4' : 'WebM'

onMounted(() => { void loadEffectFonts() })
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

.link { @apply text-slate-300 underline decoration-white/20 underline-offset-2 hover:decoration-white/60; }

.field { @apply flex flex-col gap-1.5 text-slate-500; }

.stage-chip { @apply text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded text-black/80; }
.stage-induce   { background: #7dd3fc; }
.stage-deepen   { background: #818cf8; }
.stage-emerge   { background: #fcd34d; }
.stage-reinduce { background: #a78bfa; }
.stage-final    { background: #4c1d95; color: #e9d5ff; }
.stage-wake     { background: #86efac; }
</style>
