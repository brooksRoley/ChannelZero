import { ref, readonly } from 'vue'
import * as Tone from 'tone'
import { drawFrame, drawFade } from './useGlassComposer'
import type { TextLayer } from './studioTypes'
import { trimProgress, sessionEnvelope, type TrimRange } from './studioTrim'

/**
 * Records the Glass Studio composition to a downloadable video file.
 *
 * Pipeline:
 *   1. Composites each video frame + text overlay onto a hidden canvas. The
 *      text is drawn by the SHARED `drawFrame` composer so the export is
 *      byte-for-byte identical to the live preview.
 *   2. canvas.captureStream(30) → video track.
 *   3. MediaStreamAudioDestinationNode taps the studio's session bus — media
 *      audio, Tone.js synthesis and the binaural engine already summed and
 *      faded — into one audio track.
 *   4. MediaRecorder merges the two tracks and writes chunks.
 *   5. On reaching the trim Out point (or media end) → stop → Blob → download link.
 *
 * The export runs in real-time (duration = trim range, default the whole media).
 */

const isRecording = ref(false)
const progress = ref(0)

let recorder: MediaRecorder | null = null
let chunks: Blob[] = []
let exportCanvas: HTMLCanvasElement | null = null
let exportCtx: CanvasRenderingContext2D | null = null
let rafId: number | undefined
let endHandler: (() => void) | null = null

/** Pick the best supported container. */
function pickMime(): string {
  for (const mime of [
    'video/mp4;codecs=avc1,mp4a.40.2',
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm',
  ]) {
    if (MediaRecorder.isTypeSupported(mime)) return mime
  }
  return 'video/webm'
}

export interface ExportOptions {
  /** Live beat for `syncToBeat` motion. */
  beatHz?: number
  /** Trim range; defaults to the whole media. */
  range?: TrimRange
  /** Session fade-to-black at the range edges, seconds. */
  fadeS?: number
}

export function useGlassExport() {
  async function startExport(
    mediaEl: HTMLVideoElement,
    textLayers: TextLayer[],
    audioOut: AudioNode,
    { beatHz, range, fadeS = 0 }: ExportOptions = {},
  ) {
    if (isRecording.value) return
    await Tone.start()

    const ctx = Tone.getContext().rawContext as AudioContext

    // ── Canvas for compositing ──
    const startS = range?.startS ?? 0
    const endS = range && range.endS > startS ? range.endS : mediaEl.duration
    const span: TrimRange = { startS, endS }

    const w = mediaEl.videoWidth || 1920
    const h = mediaEl.videoHeight || 1080
    exportCanvas = document.createElement('canvas')
    exportCanvas.width = w
    exportCanvas.height = h
    exportCtx = exportCanvas.getContext('2d')!

    // ── Capture streams ──
    const canvasStream = exportCanvas.captureStream(30)
    const audioDest = ctx.createMediaStreamDestination()

    audioOut.connect(audioDest)

    const combined = new MediaStream([
      ...canvasStream.getVideoTracks(),
      ...audioDest.stream.getAudioTracks(),
    ])

    // ── MediaRecorder ──
    const mimeType = pickMime()
    chunks = []
    recorder = new MediaRecorder(combined, { mimeType, videoBitsPerSecond: 5_000_000 })

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data)
    }

    recorder.onstop = () => {
      // Download the file
      const ext = mimeType.startsWith('video/mp4') ? 'mp4' : 'webm'
      const blob = new Blob(chunks, { type: mimeType })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `glass-export-${Date.now()}.${ext}`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 5000)

      // Tear down the export-only connection
      try { audioOut.disconnect(audioDest) } catch { /* ok */ }

      isRecording.value = false
      progress.value = 0
    }

    // ── Render loop ──
    function renderFrame() {
      if (!isRecording.value || !exportCtx || !exportCanvas) return
      const cw = exportCanvas.width
      const ch = exportCanvas.height

      // Video frame (or dark fill for audio-only)
      if (mediaEl.videoWidth > 0) {
        exportCtx.drawImage(mediaEl, 0, 0, cw, ch)
      } else {
        exportCtx.fillStyle = '#0a0a0a'
        exportCtx.fillRect(0, 0, cw, ch)
      }

      // Text overlays — SAME renderer as the live preview, driven by the
      // media clock so subliminal flashes / motion are frame-accurate.
      const clockMs = mediaEl.currentTime * 1000
      drawFrame(exportCtx, clockMs, textLayers, { w: cw, h: ch }, beatHz)
      if (isFinite(span.endS)) {
        drawFade(exportCtx, { w: cw, h: ch }, sessionEnvelope(span, mediaEl.currentTime, fadeS))
      }

      // Progress / Out point
      if (isFinite(span.endS)) {
        progress.value = trimProgress(span, mediaEl.currentTime)
        if (mediaEl.currentTime >= span.endS) {
          mediaEl.pause()
          stopExport()
          return
        }
      }

      rafId = requestAnimationFrame(renderFrame)
    }

    // ── Kick off ──
    mediaEl.currentTime = startS
    recorder.start(200) // collect chunks every 200ms
    isRecording.value = true

    // Wait for seek, then play
    mediaEl.onseeked = () => {
      mediaEl.onseeked = null
      mediaEl.play()
    }

    rafId = requestAnimationFrame(renderFrame)

    // Stop on media end
    endHandler = () => stopExport()
    mediaEl.addEventListener('ended', endHandler, { once: true })
  }

  function stopExport() {
    if (rafId) cancelAnimationFrame(rafId)
    if (recorder && recorder.state !== 'inactive') recorder.stop()
    // endHandler is cleaned up by { once: true }
    endHandler = null
  }

  return {
    isRecording: readonly(isRecording),
    progress: readonly(progress),
    startExport,
    stopExport,
  }
}
