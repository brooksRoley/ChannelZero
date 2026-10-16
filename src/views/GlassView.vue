<template>
  <div class="relative w-full h-screen bg-[#0a0a0a] overflow-hidden flex flex-col">

    <!-- ── First-run entrainment intro ── -->
    <Transition name="fade">
      <div
        v-if="showIntro"
        class="absolute inset-0 z-40 flex items-center justify-center bg-[#0a0a0a]/96 backdrop-blur-sm"
      >
        <div class="max-w-sm w-full px-8 text-center space-y-6">
          <div>
            <h1 class="text-white/90 text-lg font-light tracking-[0.25em] uppercase mb-2">Glass Studio</h1>
            <p class="text-slate-500 text-[10px] tracking-widest uppercase">Binaural Entrainment · Subliminal Authoring</p>
          </div>

          <p class="text-slate-400 text-sm leading-relaxed">
            Layer subliminal intention onto any audio or video. Binaural beats — precise frequency
            differentials played separately to each ear — guide your nervous system into specific
            states: alpha for calm focus, theta for deep creativity, gamma for heightened clarity.
          </p>

          <div class="space-y-3 text-left">
            <div class="flex gap-3 items-start">
              <span class="text-slate-600 text-[10px] mt-0.5 shrink-0 font-mono">01</span>
              <p class="text-slate-500 text-xs leading-relaxed">Upload a video or audio file as your carrier wave</p>
            </div>
            <div class="flex gap-3 items-start">
              <span class="text-slate-600 text-[10px] mt-0.5 shrink-0 font-mono">02</span>
              <p class="text-slate-500 text-xs leading-relaxed">Layer text that surfaces subliminally — intentions, affirmations, mantras</p>
            </div>
            <div class="flex gap-3 items-start">
              <span class="text-slate-600 text-[10px] mt-0.5 shrink-0 font-mono">03</span>
              <p class="text-slate-500 text-xs leading-relaxed">Activate binaural synthesis and export the composed session</p>
            </div>
          </div>

          <div class="space-y-3 pt-2">
            <button
              @click="dismissIntroToRecipes"
              class="w-full px-6 py-3 bg-white/5 hover:bg-white/10 border border-white/10 rounded-full text-white/70 hover:text-white/90 text-sm tracking-wider transition-all"
            >
              Browse Recipes
            </button>
            <label class="block w-full px-6 py-2 text-slate-600 hover:text-slate-400 text-xs tracking-wider cursor-pointer transition-all text-center rounded-full hover:bg-white/[0.03] relative">
              Upload your own media
              <input type="file" @change="handleUploadFromIntro" accept="video/*,audio/*" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
            </label>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ── Main viewport ── -->
    <div class="flex-1 relative overflow-hidden min-h-0">

      <!-- Video / audio element (hidden for audio-only, shown for video) -->
      <video
        ref="mediaRef"
        class="absolute inset-0 w-full h-full object-contain bg-black"
        :class="{ 'invisible': mediaType === 'audio' }"
        playsinline
        :loop="!isExporting"
        @loadedmetadata="onMediaLoaded"
        @timeupdate="onTimeUpdate"
        @ended="onEnded"
      />

      <!-- Audio-only waveform visualiser -->
      <canvas
        v-if="mediaType === 'audio' && hasMedia"
        ref="vizRef"
        class="absolute inset-0 w-full h-full"
      />

      <!-- Text overlay — SHARED composer canvas (same drawFrame as export) -->
      <canvas
        ref="overlayRef"
        class="absolute inset-0 w-full h-full pointer-events-none"
      />

      <!-- Empty state -->
      <div v-if="!hasMedia" class="absolute inset-0 flex items-center justify-center">
        <div class="text-center space-y-4">
          <p class="text-slate-600 text-sm tracking-[0.2em] uppercase">Glass Studio</p>
          <p class="text-slate-700 text-xs max-w-xs mx-auto leading-relaxed">
            Upload a video or audio file, layer customizable subliminal text, add
            Tone.js synthesis that reacts to the speech, and export the composition.
          </p>
          <label class="inline-block px-6 py-3 bg-white/5 hover:bg-white/10 border border-white/10 rounded-full text-white/60 hover:text-white/80 text-sm tracking-wider cursor-pointer transition-all">
            Upload Video or Audio
            <input type="file" @change="handleUpload" accept="video/*,audio/*" class="hidden" />
          </label>
        </div>
      </div>

      <!-- Export progress -->
      <Transition name="fade">
        <div v-if="isExporting" class="absolute inset-0 flex items-center justify-center bg-black/50 z-30">
          <div class="text-center">
            <p class="text-white/80 text-sm tracking-[0.2em] uppercase mb-3">Exporting&hellip;</p>
            <div
              role="progressbar"
              :aria-valuenow="Math.round(exportProgress * 100)"
              aria-valuemin="0"
              aria-valuemax="100"
              class="w-48 h-1 bg-white/10 rounded-full overflow-hidden mx-auto"
            >
              <div class="h-full bg-emerald-500 transition-all duration-150" :style="{ width: `${exportProgress * 100}%` }" />
            </div>
            <button @click="cancelExport" class="mt-4 text-xs text-white/30 hover:text-white/60 uppercase tracking-wider transition-colors">
              Cancel
            </button>
          </div>
        </div>
      </Transition>
    </div>

    <!-- ── Editor panel (Text / Sound tabs) ── -->
    <Transition name="fade">
      <div
        v-if="activePanel"
        class="relative z-20 bg-black/70 backdrop-blur-xl border-t border-white/[0.04] px-4 py-3 max-h-[45vh] overflow-y-auto"
      >
        <TextControls v-if="activePanel === 'text'" :layers="composition.textLayers" />
        <SoundControls
          v-else-if="activePanel === 'sound'"
          :binaural="composition.binaural"
          :active-beat-hz="studioBinaural.activeBeatHz.value"
          :tone-presets="presetLabels"
          :active-tone-preset="activePreset"
          v-model:fade-s="composition.fadeS"
          @textures="studioBinaural.updateTextures()"
          @apply="onBinauralApply"
          @volume="onBinauralVolume"
          @tone="(k: string) => selectPreset(k as TonePreset)"
        />
        <RecipeControls
          v-else-if="activePanel === 'recipes'"
          :active-recipe-id="composition.recipeId"
          @apply="applyRecipe"
        />
      </div>
    </Transition>

    <!-- ── Bottom controls ── -->
    <div class="relative z-20 bg-black/60 backdrop-blur-xl border-t border-white/[0.04] px-4 py-3 space-y-2.5">

      <!-- Transport -->
      <div class="flex items-center gap-3">
        <button
          @click="togglePlay"
          :disabled="!hasMedia"
          :aria-label="isPlaying ? 'Pause' : 'Play'"
          class="ctrl-btn disabled:opacity-20"
        >
          <svg v-if="!isPlaying" class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
          <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
        </button>

        <span class="text-[10px] text-slate-500 font-mono w-10 text-right shrink-0">{{ fmt(currentTime) }}</span>
        <input
          aria-label="Seek"
          type="range" min="0" :max="duration" :value="currentTime" @input="seek" step="0.1"
          class="flex-1 h-1 accent-white/40 cursor-pointer" :disabled="!hasMedia"
        />
        <span class="text-[10px] text-slate-500 font-mono w-10 shrink-0">{{ fmt(duration) }}</span>
      </div>

      <!-- Trim (In / Out from the playhead) -->
      <div v-if="hasMedia" class="flex items-center gap-2 pl-12">
        <button class="trim-btn" title="Set In point at playhead" @click="markIn">[ In</button>
        <div class="relative flex-1 h-1 rounded-full bg-white/[0.06]" aria-hidden="true">
          <div
            class="absolute inset-y-0 rounded-full bg-emerald-500/40"
            :style="{ left: `${pct(trim.startS)}%`, width: `${pct(trim.endS) - pct(trim.startS)}%` }"
          />
        </div>
        <button class="trim-btn" title="Set Out point at playhead" @click="markOut">Out ]</button>
        <span class="text-[10px] text-slate-500 font-mono shrink-0">
          {{ fmt(trim.startS) }}–{{ fmt(trim.endS) }}
        </span>
        <button v-if="trimmed" class="trim-btn" title="Clear trim" @click="clearTrim">×</button>
      </div>

      <!-- Tools -->
      <div class="flex items-center gap-3 flex-wrap">
        <!-- Upload -->
        <label class="ctrl-btn cursor-pointer relative shrink-0" title="Upload media">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
          </svg>
          <input type="file" @change="handleUpload" accept="video/*,audio/*" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
        </label>
        <span v-if="fileName" class="text-[10px] text-slate-600 truncate max-w-[100px] shrink-0">{{ fileName }}</span>

        <div class="w-px h-5 bg-white/[0.06] shrink-0" />

        <!-- Quick text (binds the first / title layer) -->
        <input
          v-model="quickText"
          placeholder="Overlay text..."
          class="bg-transparent border-b border-white/10 focus:border-white/30 text-white text-sm px-2 py-1 w-28 sm:w-40 outline-none placeholder-slate-600 transition-colors font-light tracking-wide"
        />

        <!-- Panel toggles -->
        <button
          @click="togglePanel('text')"
          class="px-2.5 py-1 rounded-full text-[10px] tracking-wider transition-all border whitespace-nowrap shrink-0"
          :class="activePanel === 'text'
            ? 'bg-white/10 border-white/20 text-white/90'
            : 'bg-transparent border-white/[0.06] text-white/40 hover:text-white/60 hover:border-white/10'"
        >
          Text ({{ composition.textLayers.length }})
        </button>
        <button
          @click="togglePanel('sound')"
          class="px-2.5 py-1 rounded-full text-[10px] tracking-wider transition-all border whitespace-nowrap shrink-0"
          :class="activePanel === 'sound'
            ? 'bg-white/10 border-white/20 text-white/90'
            : 'bg-transparent border-white/[0.06] text-white/40 hover:text-white/60 hover:border-white/10'"
        >
          Sound<span v-if="composition.binaural.enabled" class="text-emerald-400/80"> ♪</span>
        </button>
        <button
          @click="togglePanel('recipes')"
          class="px-2.5 py-1 rounded-full text-[10px] tracking-wider transition-all border whitespace-nowrap shrink-0"
          :class="activePanel === 'recipes'
            ? 'bg-white/10 border-white/20 text-white/90'
            : 'bg-transparent border-white/[0.06] text-white/40 hover:text-white/60 hover:border-white/10'"
        >
          Recipes
        </button>

        <div class="flex-1 min-w-0" />

        <!-- Export -->
        <button
          @click="doExport"
          :disabled="!hasMedia || isExporting"
          class="px-4 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/30 text-emerald-400/80 hover:text-emerald-400 rounded-full text-[11px] tracking-wider transition-all disabled:opacity-20 disabled:cursor-default shrink-0"
        >
          Export
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import * as Tone from 'tone'
import { useAudioSync } from '@/composables/useAudioSync'
import { useGlassTones, PRESET_LABELS, type TonePreset } from '@/composables/useGlassTones'
import { useGlassExport } from '@/composables/useGlassExport'
import { useStudioBinaural } from '@/composables/useStudioBinaural'
import { drawFrame, drawFade } from '@/composables/useGlassComposer'
import { makeDefaultComposition } from '@/composables/studioTypes'
import {
  clampTrim, setTrimIn, setTrimOut, isTrimmed, loopCorrection, sessionEnvelope, type TrimRange,
} from '@/composables/studioTrim'
import { type GlassRecipe } from '@/data/glassRecipes'
import TextControls from '@/components/studio/TextControls.vue'
import SoundControls from '@/components/studio/SoundControls.vue'
import RecipeControls from '@/components/studio/RecipeControls.vue'

// ── Refs ──
const mediaRef = ref<HTMLVideoElement | null>(null)
const vizRef = ref<HTMLCanvasElement | null>(null)
const overlayRef = ref<HTMLCanvasElement | null>(null)

const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const mediaType = ref<'video' | 'audio' | ''>('')
const mediaUrl = ref('')
const fileName = ref('')
const activePanel = ref<'text' | 'sound' | 'recipes' | null>(null)
const hasMedia = computed(() => !!mediaUrl.value)

// ── Trim ──
const trim = reactive<TrimRange>({ startS: 0, endS: 0 })
const trimmed = computed(() => isTrimmed(trim, duration.value))

function applyTrim(next: TrimRange) {
  Object.assign(trim, next)
  // Journey phases fit the trimmed span, not the whole file.
  studioBinaural.setMediaDuration(trim.endS - trim.startS)
}
function markIn() { applyTrim(setTrimIn(trim, currentTime.value, duration.value)) }
function markOut() { applyTrim(setTrimOut(trim, currentTime.value, duration.value)) }
function clearTrim() { applyTrim(clampTrim({ startS: 0, endS: 0 }, duration.value)) }
function pct(s: number) { return duration.value > 0 ? (s / duration.value) * 100 : 0 }

function togglePanel(p: 'text' | 'sound' | 'recipes') {
  activePanel.value = activePanel.value === p ? null : p
}

// ── Composition (in-memory) ──
const composition = reactive(makeDefaultComposition())

// Quick text binds the first/title layer's primary line (preserves old behavior).
const quickText = computed({
  get: () => composition.textLayers[0]?.content[0] ?? '',
  set: (v: string) => {
    const l = composition.textLayers[0]
    if (l) l.content = [v, ...l.content.slice(1)]
  },
})

// ── Session bus ──
// Media audio, reactive tones and the binaural engine all sum here; its gain
// carries the session fade and export taps it once.
let sessionBus: GainNode | null = null
function getBus(): GainNode {
  if (!sessionBus) {
    const ctx = Tone.getContext().rawContext as AudioContext
    sessionBus = ctx.createGain()
    sessionBus.connect(ctx.destination)
    const toneMaster = tones.getMasterNode()
    toneMaster.disconnect()
    toneMaster.connect(sessionBus)
  }
  return sessionBus
}

// ── Composables ──
const sync = useAudioSync()
const tones = useGlassTones()
const studioBinaural = useStudioBinaural(composition.binaural, getBus)
const { isRecording: isExporting, progress: exportProgress, startExport, stopExport: cancelExport } = useGlassExport()

const presetLabels = PRESET_LABELS
const activePreset = tones.activePreset

// Wire audio analysis → tone modulation + visualiser
sync.onFrame((env, speaking) => {
  tones.update(env, speaking)
  if (mediaType.value === 'audio' && vizRef.value) drawViz(env)
})

// ── Shared-composer overlay loop (matches export exactly) ──
let overlayRaf: number | undefined

function overlayLoop() {
  overlayRaf = requestAnimationFrame(overlayLoop)
  const canvas = overlayRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  const w = canvas.clientWidth
  const h = canvas.clientHeight
  if (w === 0 || h === 0) return
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr)
    canvas.height = Math.round(h * dpr)
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)

  // Export re-draws text on a canvas frame while recording; skip preview draw
  // then to avoid double compositing artifacts.
  // Session fade: drive the bus gain from the media clock (preview and export).
  const media = mediaRef.value
  const env = media && (isPlaying.value || isExporting.value)
    ? sessionEnvelope(trim, media.currentTime, composition.fadeS)
    : 1
  if (sessionBus) sessionBus.gain.setTargetAtTime(env, sessionBus.context.currentTime, 0.015)

  if (isExporting.value || !mediaRef.value) return
  // Keep preview playback inside the trim range (frame-accurate, unlike timeupdate).
  if (isPlaying.value && trimmed.value) {
    const to = loopCorrection(trim, mediaRef.value.currentTime)
    if (to !== null) mediaRef.value.currentTime = to
  }
  const clockMs = mediaRef.value.currentTime * 1000
  // Pass the live binaural beat so `syncToBeat` motion pulses in the preview.
  const beatHz = composition.binaural.enabled ? studioBinaural.activeBeatHz.value : undefined
  drawFrame(ctx, clockMs, composition.textLayers, { w, h }, beatHz)
  drawFade(ctx, { w, h }, env)
}

// ── Audio-only waveform ring ──
function drawViz(env: number) {
  const canvas = vizRef.value!
  const ctx = canvas.getContext('2d')!
  const dpr = window.devicePixelRatio || 1
  const w = canvas.clientWidth
  const h = canvas.clientHeight
  if (canvas.width !== w * dpr) {
    canvas.width = w * dpr
    canvas.height = h * dpr
    ctx.scale(dpr, dpr)
  }
  ctx.fillStyle = 'rgba(10,10,10,0.12)'
  ctx.fillRect(0, 0, w, h)

  const cx = w / 2, cy = h / 2
  const r = Math.min(w, h) * 0.18

  ctx.beginPath()
  ctx.arc(cx, cy, r + env * 50, 0, Math.PI * 2)
  ctx.strokeStyle = `rgba(100,180,255,${0.08 + env * 0.35})`
  ctx.lineWidth = 1.5
  ctx.stroke()

  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r)
  grad.addColorStop(0, `rgba(100,180,255,${env * 0.06})`)
  grad.addColorStop(1, 'transparent')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, w, h)
}

// ── First-run intro ──
const showIntro = ref(!localStorage.getItem('cz_glass_intro_seen'))

function dismissIntro() {
  localStorage.setItem('cz_glass_intro_seen', '1')
  showIntro.value = false
}

function dismissIntroToRecipes() {
  dismissIntro()
  activePanel.value = 'recipes'
}

async function handleUploadFromIntro(e: Event) {
  dismissIntro()
  await handleUpload(e)
}

// ── Media handling ──
async function handleUpload(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file || !mediaRef.value) return

  fileName.value = file.name
  mediaType.value = file.type.startsWith('video') ? 'video' : 'audio'

  if (mediaUrl.value) URL.revokeObjectURL(mediaUrl.value)
  mediaUrl.value = URL.createObjectURL(file)
  mediaRef.value.src = mediaUrl.value
  isPlaying.value = false
  currentTime.value = 0
}

async function onMediaLoaded() {
  if (!mediaRef.value) return
  duration.value = mediaRef.value.duration
  // New media resets the trim; journey phases auto-fit to the (full) length.
  applyTrim(clampTrim({ startS: 0, endS: 0 }, mediaRef.value.duration))
  await Tone.start()
  await sync.connect(mediaRef.value, getBus())
}

function onTimeUpdate() {
  if (!mediaRef.value) return
  currentTime.value = mediaRef.value.currentTime
  // Advance the binaural journey off the media clock (no-op in preset mode).
  studioBinaural.tickJourney(mediaRef.value.currentTime - trim.startS)
}

function onEnded() {
  if (!isExporting.value) {
    isPlaying.value = false
    studioBinaural.stop()
  }
}

async function togglePlay() {
  if (!mediaRef.value) return
  await Tone.start()
  if (isPlaying.value) {
    mediaRef.value.pause()
    studioBinaural.stop()
  } else {
    await mediaRef.value.play()
    if (composition.binaural.enabled) await studioBinaural.start()
  }
  isPlaying.value = !isPlaying.value
}

function seek(e: Event) {
  if (!mediaRef.value) return
  const t = parseFloat((e.target as HTMLInputElement).value)
  mediaRef.value.currentTime = t
  currentTime.value = t
}

function fmt(s: number): string {
  if (!isFinite(s)) return '0:00'
  return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`
}

// ── Tone preset ──
async function selectPreset(preset: TonePreset) {
  await Tone.start()
  tones.setPreset(preset)
}

// ── Binaural (Sound panel) ──
// `apply` fires after a band/mode/journey/enable change → re-sync the engine.
async function onBinauralApply() {
  if (composition.binaural.enabled && isPlaying.value) {
    await studioBinaural.start() // idempotent init + applies current config
  } else if (!composition.binaural.enabled) {
    studioBinaural.stop()
  } else {
    // Enabled but paused — just keep config in sync for the next play.
    studioBinaural.refresh()
  }
}

function onBinauralVolume(v: number) {
  studioBinaural.setVolume(v)
}

// ── Recipes (Recipes panel) ──
// Applying a recipe replaces the live composition's contents in place so the
// reactive Text and Sound bindings update, then re-syncs the binaural engine.
async function applyRecipe(recipe: GlassRecipe) {
  const built = recipe.build()
  composition.textLayers.splice(0, composition.textLayers.length, ...built.textLayers)
  Object.assign(composition.binaural, built.binaural)
  composition.fadeS = built.fadeS
  composition.recipeId = recipe.id
  // Re-seat the engine on the new binaural config (same path as a Sound-panel edit).
  await onBinauralApply()
}

// ── Export ──
async function doExport() {
  if (!mediaRef.value) return
  isPlaying.value = true

  // Start the beat first so its graph lives in Tone's shared context, routed
  // into the session bus the export taps (same context = it lands in the file).
  let beatHz: number | undefined
  if (composition.binaural.enabled) {
    await studioBinaural.start()
    beatHz = studioBinaural.activeBeatHz.value
  }

  await startExport(mediaRef.value, composition.textLayers, getBus(), {
    beatHz,
    range: { ...trim },
    fadeS: composition.fadeS,
  })
}

// ── Lifecycle ──
onMounted(() => {
  overlayRaf = requestAnimationFrame(overlayLoop)
})

onUnmounted(() => {
  if (overlayRaf) cancelAnimationFrame(overlayRaf)
  sync.disconnect()
  tones.dispose()
  studioBinaural.destroy()
  if (mediaUrl.value) URL.revokeObjectURL(mediaUrl.value)
})
</script>

<style scoped>
.ctrl-btn {
  @apply w-9 h-9 rounded-full bg-white/5 hover:bg-white/10
         border border-white/[0.06] text-white/50 hover:text-white/80
         flex items-center justify-center transition-all shrink-0 active:scale-95;
}

.trim-btn {
  @apply px-2 py-0.5 rounded-full text-[10px] tracking-wider border border-white/[0.08]
         text-white/40 hover:text-white/70 hover:border-white/20 transition-all shrink-0;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
