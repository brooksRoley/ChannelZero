/**
 * useEyeState — opt-in webcam eye-closure sensing for fractionation pacing.
 *
 * Privacy: everything runs on-device. Camera frames go from getUserMedia into
 * an in-page <video> and MediaPipe Face Landmarker (WASM, in the browser);
 * no frame, landmark or score is uploaded, logged or stored. Only the
 * MediaPipe runtime and model files are fetched from public CDNs. stop()
 * releases the camera, and the page hiding (pagehide) does the same.
 *
 * Eye closure is a pacing cue ("eyes closed" / "open your eyes"), not proof
 * of trance or of any inner state.
 */
import { ref, readonly } from 'vue'
import type { FaceLandmarker, FaceLandmarkerResult } from '@mediapipe/tasks-vision'

const WASM_URL = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.1.1/wasm'
const MODEL_URL =
  'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'

export const CLOSE_THRESHOLD = 0.55
export const OPEN_THRESHOLD = 0.35
export const CLOSE_DWELL_MS = 300
export const OPEN_DWELL_MS = 200
const FRAME_INTERVAL_MS = 1000 / 12
const NO_FACE_MS = 1000

export type EyeStatus = 'off' | 'loading' | 'tracking' | 'no-face' | 'denied' | 'error'

export interface EyeClassState {
  /** Debounced state: true once the eyes have stayed closed past the dwell. */
  closed: boolean
  /** Raw hysteresis state, before dwell debouncing. */
  candidateClosed: boolean
  /** How long the candidate has disagreed with `closed`. */
  pendingMs: number
  closedForMs: number
  openForMs: number
}

export const INITIAL_EYE_STATE: EyeClassState = Object.freeze({
  closed: false,
  candidateClosed: false,
  pendingMs: 0,
  closedForMs: 0,
  openForMs: 0,
})

/**
 * Pure classifier step. Hysteresis on the averaged blink score, then a minimum
 * dwell before the debounced state flips, so ordinary blinks never count.
 * Pending time is measured from the first sample that disagreed.
 */
export function classifyEyes(
  blinkL: number,
  blinkR: number,
  prev: EyeClassState,
  dtMs: number,
): EyeClassState {
  const dt = Math.max(0, dtMs)
  const avg = (blinkL + blinkR) / 2
  const candidateClosed =
    avg >= CLOSE_THRESHOLD ? true : avg <= OPEN_THRESHOLD ? false : prev.candidateClosed

  if (candidateClosed === prev.closed) {
    return {
      closed: prev.closed,
      candidateClosed,
      pendingMs: 0,
      closedForMs: prev.closed ? prev.closedForMs + dt : 0,
      openForMs: prev.closed ? 0 : prev.openForMs + dt,
    }
  }

  const pendingMs = prev.candidateClosed === candidateClosed ? prev.pendingMs + dt : 0
  const dwell = candidateClosed ? CLOSE_DWELL_MS : OPEN_DWELL_MS

  if (pendingMs >= dwell) {
    return {
      closed: candidateClosed,
      candidateClosed,
      pendingMs: 0,
      closedForMs: candidateClosed ? pendingMs : 0,
      openForMs: candidateClosed ? 0 : pendingMs,
    }
  }

  return {
    closed: prev.closed,
    candidateClosed,
    pendingMs,
    closedForMs: prev.closed ? prev.closedForMs + dt : 0,
    openForMs: prev.closed ? 0 : prev.openForMs + dt,
  }
}

function blinkScores(result: FaceLandmarkerResult): { l: number; r: number } | null {
  const cats = result.faceBlendshapes?.[0]?.categories
  if (!cats?.length) return null
  let l = NaN
  let r = NaN
  for (const c of cats) {
    if (c.categoryName === 'eyeBlinkLeft') l = c.score
    else if (c.categoryName === 'eyeBlinkRight') r = c.score
  }
  return Number.isFinite(l) && Number.isFinite(r) ? { l, r } : null
}

// ── module singleton ────────────────────────────────────────────────
const status = ref<EyeStatus>('off')
const eyesClosed = ref(false)
const closedForMs = ref(0)
const openForMs = ref(0)
const confidence = ref(0)

const listeners = new Set<(closed: boolean) => void>()

let classState: EyeClassState = INITIAL_EYE_STATE
let stream: MediaStream | null = null
let video: HTMLVideoElement | null = null
let landmarker: FaceLandmarker | null = null
let rafId: number | null = null
let lastFrameAt = 0
let lastFaceAt = 0
let presence = 0
let generation = 0

function emit(closed: boolean) {
  for (const cb of listeners) {
    try {
      cb(closed)
    } catch (err) {
      console.warn('[useEyeState] listener failed', err)
    }
  }
}

function applyState(next: EyeClassState) {
  const changed = next.closed !== classState.closed
  classState = next
  eyesClosed.value = next.closed
  closedForMs.value = Math.round(next.closedForMs)
  openForMs.value = Math.round(next.openForMs)
  if (changed) emit(next.closed)
}

function tick(now: number) {
  rafId = requestAnimationFrame(tick)
  if (!landmarker || !video || video.readyState < 2) return
  if (now - lastFrameAt < FRAME_INTERVAL_MS) return
  const dt = lastFrameAt ? now - lastFrameAt : 0
  lastFrameAt = now

  let scores: { l: number; r: number } | null = null
  try {
    scores = blinkScores(landmarker.detectForVideo(video, now))
  } catch (err) {
    console.warn('[useEyeState] detection failed', err)
  }

  presence += ((scores ? 1 : 0) - presence) * 0.2
  if (scores) {
    lastFaceAt = now
    if (status.value !== 'tracking') status.value = 'tracking'
    applyState(classifyEyes(scores.l, scores.r, classState, dt))
    const avg = (scores.l + scores.r) / 2
    const clarity = Math.min(1, Math.abs(avg - (CLOSE_THRESHOLD + OPEN_THRESHOLD) / 2) / 0.25)
    confidence.value = presence * (0.5 + 0.5 * clarity)
  } else {
    confidence.value = presence * 0.5
    if (now - lastFaceAt > NO_FACE_MS) status.value = 'no-face'
  }
}

function onPageHide() {
  stop()
}

async function start(): Promise<void> {
  if (status.value === 'loading' || status.value === 'tracking' || status.value === 'no-face') return
  const gen = ++generation
  status.value = 'loading'

  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera API unavailable')
    const media = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: 320, height: 240 },
      audio: false,
    })
    if (gen !== generation) {
      media.getTracks().forEach((t) => t.stop())
      return
    }
    stream = media
    window.addEventListener('pagehide', onPageHide)

    const el = document.createElement('video')
    el.muted = true
    el.playsInline = true
    el.autoplay = true
    el.setAttribute('playsinline', '')
    el.setAttribute('aria-hidden', 'true')
    el.style.cssText =
      'position:fixed;left:-9999px;top:0;width:1px;height:1px;opacity:0;pointer-events:none;'
    el.srcObject = media
    document.body.appendChild(el)
    video = el
    await el.play()

    const { FilesetResolver, FaceLandmarker } = await import('@mediapipe/tasks-vision')
    const fileset = await FilesetResolver.forVisionTasks(WASM_URL)
    const lm = await FaceLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: MODEL_URL, delegate: 'GPU' },
      runningMode: 'VIDEO',
      numFaces: 1,
      outputFaceBlendshapes: true,
    })
    if (gen !== generation) {
      lm.close()
      return
    }
    landmarker = lm

    lastFrameAt = 0
    lastFaceAt = performance.now()
    status.value = 'tracking'
    rafId = requestAnimationFrame(tick)
  } catch (err) {
    if (gen !== generation) return
    const name = (err as { name?: string } | null)?.name
    const next: EyeStatus = name === 'NotAllowedError' ? 'denied' : 'error'
    if (next === 'error') console.warn('[useEyeState] failed to start', err)
    release()
    status.value = next
  }
}

function release() {
  if (rafId !== null) cancelAnimationFrame(rafId)
  rafId = null
  stream?.getTracks().forEach((t) => t.stop())
  stream = null
  if (video) {
    video.pause()
    video.srcObject = null
    video.remove()
  }
  video = null
  try {
    landmarker?.close()
  } catch {
    /* already closed */
  }
  landmarker = null
  window.removeEventListener('pagehide', onPageHide)

  const wasClosed = classState.closed
  classState = INITIAL_EYE_STATE
  eyesClosed.value = false
  closedForMs.value = 0
  openForMs.value = 0
  confidence.value = 0
  presence = 0
  lastFrameAt = 0
  lastFaceAt = 0
  if (wasClosed) emit(false)
}

function stop(): void {
  generation++
  release()
  status.value = 'off'
}

function onChange(cb: (closed: boolean) => void): () => void {
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}

export function useEyeState() {
  return {
    status: readonly(status),
    eyesClosed: readonly(eyesClosed),
    closedForMs: readonly(closedForMs),
    openForMs: readonly(openForMs),
    confidence: readonly(confidence),
    start,
    stop,
    onChange,
  }
}
