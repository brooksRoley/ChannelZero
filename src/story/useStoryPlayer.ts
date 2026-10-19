import { ref, readonly } from 'vue'
import { drawFrame, drawFade, safeVisualHz } from '@/composables/useGlassComposer'
import { pickMime, downloadRecording } from '@/composables/useGlassExport'
import { makeDefaultTextLayer, type TextLayer } from '@/composables/studioTypes'
import { sessionEnvelope } from '@/composables/studioTrim'
import { STAGES, frameAt, depthDimAt, type StoryStage, type Timeline } from './storyBeats'

/**
 * Plays — and optionally records — a story: the pre-rendered soundtrack is
 * the master clock; each frame draws the looping background video (or a
 * breathing field), dims it with depth, and overlays the current phrase with
 * the Glass Studio's shared `drawFrame`. Recording taps the same canvas and
 * soundtrack into a MediaRecorder (mp4 where the browser supports it).
 *
 * Recording runs in real time, like the studio export.
 */

export type OverlayStyle = 'soft' | 'glass'

/** Fade to/from black at the session edges, seconds (matches the soundtrack). */
export const STORY_FADE_S = 3

/** PURE: the single text layer for this frame's phrase. */
export function overlayLayer(text: string, alpha: number, stage: StoryStage, style: OverlayStyle): TextLayer {
  const glass = style === 'glass'
  return makeDefaultTextLayer({
    content: [text],
    font: {
      family: glass ? 'system-ui, -apple-system, sans-serif' : 'Georgia, "Iowan Old Style", serif',
      sizeVw: glass ? 7 : 4.6,
      weight: glass ? 900 : 400,
      letterSpacing: glass ? -0.02 : 0.01,
      upper: glass,
    },
    style: { color: glass ? '#ffffff' : '#f4efe6', opacity: alpha, blend: glass ? 'exclusion' : 'normal' },
    timing: { mode: 'persistent', holdMs: 0, fadeMs: 0, intervalMs: 0, flashMs: 0 },
    motion: { type: STAGES[stage].motion, amount: 0.5, syncToBeat: true },
  })
}

/** Canvas size for a background: its own aspect, longest edge ≤ 1920. */
export function canvasSizeFor(video: HTMLVideoElement | null): { w: number; h: number } {
  const vw = video?.videoWidth || 1280
  const vh = video?.videoHeight || 720
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

/** Draw `video` to cover the canvas, cropping the overflow. */
function drawCover(ctx: CanvasRenderingContext2D, video: HTMLVideoElement, w: number, h: number) {
  const k = Math.max(w / video.videoWidth, h / video.videoHeight)
  const dw = video.videoWidth * k
  const dh = video.videoHeight * k
  ctx.drawImage(video, (w - dw) / 2, (h - dh) / 2, dw, dh)
}

/** Render one frame of the story at `tMs`. Used by playback, recording and scrubbing. */
export function drawStoryFrame(
  ctx: CanvasRenderingContext2D,
  tl: Timeline,
  tMs: number,
  video: HTMLVideoElement | null,
  style: OverlayStyle,
) {
  const { width: w, height: h } = ctx.canvas
  const frame = frameAt(tl, tMs)

  if (video && video.videoWidth > 0) drawCover(ctx, video, w, h)
  else drawField(ctx, w, h, tMs, frame.beatHz)

  // Depth dim + a soft vignette so the phrase reads over bright footage.
  ctx.save()
  ctx.fillStyle = `rgba(0, 0, 0, ${depthDimAt(tl, tMs)})`
  ctx.fillRect(0, 0, w, h)
  if (style === 'soft') {
    const v = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.2, w / 2, h / 2, Math.max(w, h) * 0.7)
    v.addColorStop(0, 'rgba(0, 0, 0, 0.35)')
    v.addColorStop(1, 'rgba(0, 0, 0, 0.1)')
    ctx.fillStyle = v
    ctx.fillRect(0, 0, w, h)
  }
  ctx.restore()

  if (frame.text && frame.beat && frame.alpha > 0.001) {
    // Beat-local clock + the beat's own rate: motion restarts with each beat
    // (while the phrase fades in) instead of jumping phase mid-glide.
    const layer = overlayLayer(frame.text, frame.alpha, frame.beat.stage, style)
    drawFrame(ctx, tMs - frame.beat.startMs, [layer], { w, h }, frame.beat.beatHz)
  }

  drawFade(ctx, { w, h }, sessionEnvelope({ startS: 0, endS: tl.durationMs / 1000 }, tMs / 1000, STORY_FADE_S))
}

// ── Player (module singleton, like the studio export) ────────────

type PlayerState = 'idle' | 'playing' | 'recording'

const state = ref<PlayerState>('idle')
const clockMs = ref(0)

let audioCtx: AudioContext | null = null
let source: AudioBufferSourceNode | null = null
let recorder: MediaRecorder | null = null
let rafId: number | undefined
let activeVideo: HTMLVideoElement | null = null
/** Per-recording flag, so a late onstop from a cancelled take can't save. */
let take: { discard: boolean } | null = null

export interface PlayOptions {
  canvas: HTMLCanvasElement
  video: HTMLVideoElement | null
  soundtrack: AudioBuffer
  timeline: Timeline
  style: OverlayStyle
  /** Record to a file; always starts from 0. */
  record?: boolean
  fromMs?: number
}

export function useStoryPlayer() {
  async function play({ canvas, video, soundtrack, timeline, style, record = false, fromMs = 0 }: PlayOptions) {
    stop()
    const ctx2d = canvas.getContext('2d')
    if (!ctx2d) return
    audioCtx ??= new AudioContext()
    await audioCtx.resume()
    const ac = audioCtx
    const offsetS = record ? 0 : Math.max(0, Math.min(fromMs, timeline.durationMs - 100)) / 1000

    source = ac.createBufferSource()
    source.buffer = soundtrack
    source.connect(ac.destination)

    if (record) {
      const dest = ac.createMediaStreamDestination()
      source.connect(dest)
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

    activeVideo = video
    if (video && video.readyState > 0 && isFinite(video.duration) && video.duration > 0) {
      video.loop = true
      video.muted = true
      video.currentTime = offsetS % video.duration
      await video.play().catch(() => { /* field fallback still draws */ })
    }

    lastFieldMs = offsetS * 1000
    const startAt = ac.currentTime + 0.05
    const t0 = startAt - offsetS
    source.onended = () => finish()
    source.start(startAt, offsetS)
    recorder?.start(250)
    state.value = record ? 'recording' : 'playing'

    const loop = () => {
      const t = Math.max(0, (ac.currentTime - t0) * 1000)
      clockMs.value = t
      drawStoryFrame(ctx2d, timeline, t, activeVideo, style)
      rafId = requestAnimationFrame(loop)
    }
    rafId = requestAnimationFrame(loop)
  }

  function finish() {
    if (rafId) cancelAnimationFrame(rafId)
    rafId = undefined
    if (recorder && recorder.state !== 'inactive') recorder.stop()
    recorder = null
    take = null
    activeVideo?.pause()
    source = null
    state.value = 'idle'
  }

  /** Stop playback. A recording in progress is discarded, not saved. */
  function stop() {
    if (source) {
      source.onended = null
      try { source.stop() } catch { /* not started */ }
    }
    if (take) take.discard = true
    finish()
  }

  return {
    state: readonly(state),
    clockMs: readonly(clockMs),
    play,
    stop,
  }
}
