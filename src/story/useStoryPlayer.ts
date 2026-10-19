import { ref, readonly } from 'vue'
import { drawFade, safeVisualHz } from '@/composables/useGlassComposer'
import { pickMime, downloadRecording } from '@/composables/useGlassExport'
import { sessionEnvelope } from '@/composables/studioTrim'
import { frameAt, depthDimAt, lineAt, type Timeline } from './storyBeats'
import { drawKeys, drawSubliminals, drawCredit, drawReadingLine } from './drawEffects'
import { backdropAt, type Backdrop, type BeatScene } from './beatStyle'
import { createMixer, type Mixer } from './mixer'
import { scheduleScore, type ScoreHandle } from './score'
import type { Automation, MixState, SoundDesign, StemId } from './trance'

/**
 * Plays — and optionally records — a story: the score is scheduled live
 * through the trance mixer and the audio clock is the master clock; each frame draws the beat's backdrop (a looping clip, a
 * still, a colour or the breathing field — crossfading when it changes),
 * dims it with depth, then draws the key-phrase effects and subliminals
 * (drawEffects) and, optionally, the reading line. Recording taps the same canvas and
 * soundtrack into a MediaRecorder (mp4 where the browser supports it).
 *
 * Recording runs in real time, like the studio export.
 */

/** A clip or still in the backdrop library. */
export interface StoryMedia {
  id: string
  name: string
  kind: 'video' | 'image'
  el: HTMLVideoElement | HTMLImageElement
}

/** What the backdrops are: one resolved scene per timeline beat, plus the library. */
export interface SceneInput {
  scenes: BeatScene[]
  media: Map<string, StoryMedia>
}

export interface FrameOptions {
  /** Show the story as a reading line (current sentence, words lit as spoken). */
  captions: boolean
  /** Attribution drawn over the closing seconds (e.g. "Voice: ElevenLabs"). */
  credit?: string
}

/** Fade to/from black at the session edges, seconds (matches the soundtrack). */
export const STORY_FADE_S = 3

/** Intrinsic size of a library item, 0×0 until it has decoded. */
function mediaSize(m: StoryMedia | null | undefined): { w: number; h: number } {
  if (!m) return { w: 0, h: 0 }
  return m.el instanceof HTMLVideoElement
    ? { w: m.el.videoWidth, h: m.el.videoHeight }
    : { w: m.el.complete ? m.el.naturalWidth : 0, h: m.el.complete ? m.el.naturalHeight : 0 }
}

/** Canvas size for a backdrop: its own aspect, longest edge ≤ 1920. */
export function canvasSizeFor(media: StoryMedia | null): { w: number; h: number } {
  const size = mediaSize(media)
  const vw = size.w || 1280
  const vh = size.h || 720
  const k = Math.min(1, 1920 / Math.max(vw, vh))
  return { w: Math.round(vw * k), h: Math.round(vh * k) }
}

/** Phase of the fallback field's breathing, accumulated so rate changes never jump. */
let fieldPhase = 0
let lastFieldMs = 0

function drawField(ctx: CanvasRenderingContext2D, w: number, h: number, tMs: number, beatHz: number) {
  const dt = Math.max(0, Math.min(100, tMs - lastFieldMs))
  lastFieldMs = tMs
  fieldPhase += 2 * Math.PI * safeVisualHz(beatHz) * 0.25 * (dt / 1000)
  ctx.fillStyle = '#07070c'
  ctx.fillRect(0, 0, w, h)
  const r = Math.max(w, h) * (0.45 + 0.06 * Math.sin(fieldPhase))
  const g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, r)
  g.addColorStop(0, 'rgba(88, 70, 160, 0.55)')
  g.addColorStop(0.5, 'rgba(30, 40, 90, 0.25)')
  g.addColorStop(1, 'rgba(0, 0, 0, 0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, w, h)
}

/** Draw a library item to cover the canvas, cropping the overflow. False if it isn't ready. */
function drawCover(ctx: CanvasRenderingContext2D, media: StoryMedia | undefined, w: number, h: number): boolean {
  const size = mediaSize(media)
  if (!media || !size.w || !size.h) return false
  const k = Math.max(w / size.w, h / size.h)
  const dw = size.w * k
  const dh = size.h * k
  ctx.drawImage(media.el, (w - dw) / 2, (h - dh) / 2, dw, dh)
  return true
}

function drawBackdrop(ctx: CanvasRenderingContext2D, bd: Backdrop, media: SceneInput['media'], w: number, h: number, tMs: number, beatHz: number) {
  if (bd.kind === 'solid') {
    ctx.fillStyle = bd.color
    ctx.fillRect(0, 0, w, h)
  } else if (bd.kind === 'gradient') {
    const g = ctx.createLinearGradient(0, 0, 0, h)
    g.addColorStop(0, bd.from)
    g.addColorStop(1, bd.to)
    ctx.fillStyle = g
    ctx.fillRect(0, 0, w, h)
  } else if (bd.kind === 'field' || !drawCover(ctx, media.get(bd.mediaId), w, h)) {
    drawField(ctx, w, h, tMs, beatHz)
  }
}

/** Render one frame of the story at `tMs`. Used by playback, recording and scrubbing. */
export function drawStoryFrame(
  ctx: CanvasRenderingContext2D,
  tl: Timeline,
  tMs: number,
  scene: SceneInput,
  opts: FrameOptions,
) {
  const { width: w, height: h } = ctx.canvas
  const size = { w, h }
  const frame = frameAt(tl, tMs)

  const bd = backdropAt(tl, scene.scenes, tMs)
  if (!bd) drawField(ctx, w, h, tMs, frame.beatHz)
  else if (bd.k >= 1) drawBackdrop(ctx, bd.to, scene.media, w, h, tMs, frame.beatHz)
  else {
    drawBackdrop(ctx, bd.from, scene.media, w, h, tMs, frame.beatHz)
    ctx.save()
    ctx.globalAlpha = bd.k
    drawBackdrop(ctx, bd.to, scene.media, w, h, tMs, frame.beatHz)
    ctx.restore()
  }

  // Depth dim + a soft vignette so text reads over bright footage.
  ctx.save()
  ctx.fillStyle = `rgba(0, 0, 0, ${depthDimAt(tl, tMs)})`
  ctx.fillRect(0, 0, w, h)
  const v = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.2, w / 2, h / 2, Math.max(w, h) * 0.7)
  v.addColorStop(0, 'rgba(0, 0, 0, 0.3)')
  v.addColorStop(1, 'rgba(0, 0, 0, 0.1)')
  ctx.fillStyle = v
  ctx.fillRect(0, 0, w, h)
  ctx.restore()

  drawSubliminals(ctx, tl.subliminals, tMs, size, tl.look === 'gentle')
  drawKeys(ctx, tl.keys, tMs, size)
  if (opts.captions) {
    const line = lineAt(tl, tMs)
    if (line) drawReadingLine(ctx, line, tMs, size, scene.scenes[line.beat]?.place)
  }
  if (opts.credit) drawCredit(ctx, opts.credit, creditAlpha(tl, tMs), size)

  drawFade(ctx, size, sessionEnvelope({ startS: 0, endS: tl.durationMs / 1000 }, tMs / 1000, STORY_FADE_S))
}

/** Credit fades in over the tail, before the closing fade-to-black. */
function creditAlpha(tl: Timeline, tMs: number): number {
  const from = tl.durationMs - tl.tailMs - 2000
  return Math.max(0, Math.min(1, (tMs - from) / 800))
}

// ── Player (module singleton, like the studio export) ────────────

type PlayerState = 'idle' | 'playing' | 'recording'

const state = ref<PlayerState>('idle')
const clockMs = ref(0)
const meters = ref<Partial<Record<StemId, number>>>({})

let audioCtx: AudioContext | null = null
let mixer: Mixer | null = null
let score: ScoreHandle | null = null
let endTimer: ReturnType<typeof setTimeout> | undefined
let recorder: MediaRecorder | null = null
let rafId: number | undefined
let activeVideos: HTMLVideoElement[] = []
/** Per-recording flag, so a late onstop from a cancelled take can't save. */
let take: { discard: boolean } | null = null

export interface PlayOptions {
  canvas: HTMLCanvasElement
  scene: SceneInput
  timeline: Timeline
  /** Rendered voice per beat (null where unvoiced). */
  voices: (AudioBuffer | null)[]
  design: SoundDesign
  mix: MixState
  automation: Automation
  frame: FrameOptions
  /** Record to a file; always starts from 0. */
  record?: boolean
  fromMs?: number
}

export function useStoryPlayer() {
  async function play({ canvas, scene, timeline, voices, design, mix, automation, frame, record = false, fromMs = 0 }: PlayOptions) {
    stop()
    const ctx2d = canvas.getContext('2d')
    if (!ctx2d) return
    audioCtx ??= new AudioContext()
    await audioCtx.resume()
    const ac = audioCtx
    const offsetMs = record ? 0 : Math.max(0, Math.min(fromMs, timeline.durationMs - 100))
    const startAt = ac.currentTime + 0.08

    const mx = createMixer(ac, { meters: true })
    mixer = mx
    mx.output.connect(ac.destination)
    mx.setMix(mix, design.comfort)
    mx.scheduleAutomation(automation, startAt, offsetMs)
    mx.scheduleFade(timeline.durationMs, STORY_FADE_S, startAt, offsetMs)
    score = scheduleScore(ac, timeline, voices, mx.inputs, { design, fromMs: offsetMs, startAt })

    if (record) {
      const dest = ac.createMediaStreamDestination()
      mx.output.connect(dest)
      const stream = new MediaStream([
        ...canvas.captureStream(30).getVideoTracks(),
        ...dest.stream.getAudioTracks(),
      ])
      const mimeType = pickMime()
      const thisTake = { discard: false }
      take = thisTake
      const takeChunks: Blob[] = []
      recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 6_000_000 })
      recorder.ondataavailable = (e) => { if (e.data.size > 0) takeChunks.push(e.data) }
      recorder.onstop = () => {
        if (!thisTake.discard) downloadRecording(takeChunks, mimeType, 'channelzero-story')
      }
    }

    // Every clip loops from the start of playback, so a beat's clip is
    // already moving when its backdrop fades in.
    activeVideos = [...scene.media.values()]
      .map((m) => m.el)
      .filter((el): el is HTMLVideoElement => el instanceof HTMLVideoElement && el.readyState > 0 && isFinite(el.duration) && el.duration > 0)
    await Promise.all(activeVideos.map((v) => {
      v.loop = true
      v.muted = true
      v.currentTime = (offsetMs / 1000) % v.duration
      return v.play().catch(() => { /* field fallback still draws */ })
    }))

    lastFieldMs = offsetMs
    const t0 = startAt - offsetMs / 1000
    recorder?.start(250)
    state.value = record ? 'recording' : 'playing'
    // The score has no single source to end on; finish on the clock (with a
    // timer backstop, since rAF stalls in a background tab).
    endTimer = setTimeout(() => finish(), (startAt - ac.currentTime) * 1000 + timeline.durationMs - offsetMs + 250)

    let frameNo = 0
    const loop = () => {
      const t = Math.max(0, (ac.currentTime - t0) * 1000)
      clockMs.value = Math.min(t, timeline.durationMs)
      drawStoryFrame(ctx2d, timeline, t, scene, frame)
      if (++frameNo % 3 === 0) {
        // Fall back slowly, so short sounds (heartbeat, bowl strikes) still register.
        const now = mx.levels()
        const prev = meters.value
        meters.value = Object.fromEntries(Object.entries(now).map(([id, v]) => [id, Math.max(v, (prev[id as StemId] ?? 0) * 0.82)]))
      }
      if (t >= timeline.durationMs) { finish(); return }
      rafId = requestAnimationFrame(loop)
    }
    rafId = requestAnimationFrame(loop)
  }

  function finish() {
    clearTimeout(endTimer)
    if (rafId) cancelAnimationFrame(rafId)
    rafId = undefined
    if (recorder && recorder.state !== 'inactive') recorder.stop()
    recorder = null
    take = null
    activeVideos.forEach((v) => v.pause())
    activeVideos = []
    score?.stop()
    score = null
    mixer?.dispose()
    mixer = null
    meters.value = {}
    state.value = 'idle'
  }

  /** Stop playback. A recording in progress is discarded, not saved. */
  function stop() {
    if (take) take.discard = true
    finish()
  }

  /** Move faders / mute / solo on the running mix. */
  function setMix(mix: MixState, comfort: boolean) {
    mixer?.setMix(mix, comfort)
  }

  return {
    state: readonly(state),
    clockMs: readonly(clockMs),
    meters: readonly(meters),
    play,
    stop,
    setMix,
  }
}

/**
 * A soft tone in the left ear, then the right — binaural only works on
 * headphones worn the right way round. Resolves with each side as it plays.
 */
export async function headphoneCheck(onSide: (side: 'left' | 'right' | null) => void) {
  audioCtx ??= new AudioContext()
  await audioCtx.resume()
  const ac = audioCtx
  for (const [side, ch, freq] of [['left', 0, 392], ['right', 1, 494]] as const) {
    onSide(side)
    const o = ac.createOscillator()
    o.frequency.value = freq
    const g = ac.createGain()
    const t = ac.currentTime + 0.02
    g.gain.setValueAtTime(0, t)
    g.gain.linearRampToValueAtTime(0.18, t + 0.08)
    g.gain.setValueAtTime(0.18, t + 0.8)
    g.gain.linearRampToValueAtTime(0, t + 1)
    const merger = ac.createChannelMerger(2)
    o.connect(g).connect(merger, 0, ch)
    merger.connect(ac.destination)
    o.start(t)
    o.stop(t + 1.05)
    await new Promise((r) => setTimeout(r, 1250))
    merger.disconnect()
  }
  onSide(null)
}
