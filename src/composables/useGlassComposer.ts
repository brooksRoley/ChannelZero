import type { Anchor, BlendMode, TextLayer } from './studioTypes'

/**
 * Glass Studio — the ONE shared canvas renderer used by both live preview and
 * export. Preview calls `drawFrame` every requestAnimationFrame over the video;
 * `useGlassExport` calls the SAME function into the export canvas so subliminal
 * flashes and motion are frame-accurate in the downloaded file.
 *
 * The per-layer timing/motion math lives in PURE functions (`layerStateAt` and
 * its helpers) so it can be unit-tested with no canvas. `drawFrame` is the only
 * part that touches a CanvasRenderingContext2D.
 *
 * See docs/superpowers/specs/2026-08-04-glass-studio-subliminal-design.md
 */

// ── Constants ──────────────────────────────────────────────────────

/**
 * Practical floor for a subliminal flash. Export captures at 30fps, so a single
 * frame is ~33ms. Flashes shorter than this can be dropped entirely between
 * captured frames, so we clamp the effective visible window to this floor.
 */
export const FLASH_FLOOR_MS = 33

/** Default oscillation rate (Hz) for motion when not synced to a binaural beat. */
export const DEFAULT_MOTION_HZ = 0.5

/**
 * Ceiling for beat-synced visual motion. WCAG 2.3.1 fails more than 3 flashes/s,
 * and `waver` swings opacity — at a raw 10 Hz alpha or 40 Hz gamma beat it is a
 * flicker. Stay under 3 Hz with margin.
 */
export const MAX_VISUAL_HZ = 2.5

/**
 * PURE: the visual rate for a beat — the highest integer subharmonic of
 * `beatHz` (beatHz / k) at or below MAX_VISUAL_HZ, so motion stays phase-locked
 * to the beat (every k-th beat) without flickering. 10 Hz → 2.5 Hz, 40 Hz → 2.5 Hz,
 * 6 Hz → 2 Hz, 2 Hz → 2 Hz.
 */
export function safeVisualHz(beatHz: number): number {
  if (!(beatHz > 0)) return DEFAULT_MOTION_HZ
  return beatHz / Math.max(1, Math.ceil(beatHz / MAX_VISUAL_HZ))
}

/** Fraction of viewport width used as the text wrap / padding margin. */
const TEXT_MARGIN = 0.08

// ── Types ──────────────────────────────────────────────────────────

/** Additive motion transform, expressed size-independently so it stays pure. */
export interface LayerTransform {
  scale: number // multiplies font size
  txFrac: number // translate X as fraction of viewport width
  tyFrac: number // translate Y as fraction of viewport height
  alphaMul: number // multiplies the timing alpha
}

export interface LayerState {
  text: string | null // effective text for this frame (null → draw nothing)
  alpha: number // final 0..1 alpha (timing × motion)
  transform: LayerTransform
}

const IDENTITY_TRANSFORM: LayerTransform = { scale: 1, txFrac: 0, tyFrac: 0, alphaMul: 1 }

// ── Deterministic PRNG (for subliminal shuffle + shake jitter) ─────

/** mulberry32 — small deterministic PRNG so preview and export agree. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return function () {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Deterministic Fisher-Yates permutation of [0..n) seeded by `seed`. */
function seededPermutation(n: number, seed: number): number[] {
  const arr = Array.from({ length: n }, (_, i) => i)
  const rand = mulberry32(seed + 1)
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}

// ── Pure timing helpers ────────────────────────────────────────────

/** Non-empty content entries — empty textarea lines are ignored. */
function pool(layer: TextLayer): string[] {
  return layer.content.map((c) => c ?? '').filter((c) => c.trim().length > 0)
}

/** persistent: content[0], fade in once at start over fadeMs. */
function persistentState(layer: TextLayer, tMs: number): { text: string | null; alpha: number } {
  const items = pool(layer)
  const text = items[0] ?? null
  if (!text) return { text: null, alpha: 0 }
  const fade = Math.max(0, layer.timing.fadeMs)
  const fadeAlpha = fade > 0 ? Math.min(1, Math.max(0, tMs) / fade) : 1
  return { text, alpha: layer.style.opacity * fadeAlpha }
}

/**
 * sequence: cycle content[], each item shows holdMs with fadeMs in/out, loops.
 * Full cycle = content.length * (holdMs + 2*fadeMs).
 */
function sequenceState(layer: TextLayer, tMs: number): { text: string | null; alpha: number } {
  const items = pool(layer)
  const n = items.length
  if (n === 0) return { text: null, alpha: 0 }

  const hold = Math.max(0, layer.timing.holdMs)
  const fade = Math.max(0, layer.timing.fadeMs)
  const slot = hold + 2 * fade
  if (slot <= 0) return { text: items[0], alpha: layer.style.opacity }

  const cycle = n * slot
  const tInCycle = ((tMs % cycle) + cycle) % cycle
  const idx = Math.min(n - 1, Math.floor(tInCycle / slot))
  const tInSlot = tInCycle - idx * slot

  let env: number
  if (tInSlot < fade) {
    env = fade > 0 ? tInSlot / fade : 1 // fade in
  } else if (tInSlot < fade + hold) {
    env = 1 // full hold
  } else {
    env = fade > 0 ? 1 - (tInSlot - fade - hold) / fade : 0 // fade out
  }
  return { text: items[idx], alpha: layer.style.opacity * Math.max(0, Math.min(1, env)) }
}

/**
 * subliminal: every intervalMs, flash one pool item for flashMs (hard on/off).
 * Pool advances each flash and the order is deterministically shuffled per pass
 * so preview and export agree. flashMs is clamped to FLASH_FLOOR_MS.
 */
function subliminalState(layer: TextLayer, tMs: number): { text: string | null; alpha: number } {
  const items = pool(layer)
  const n = items.length
  if (n === 0) return { text: null, alpha: 0 }

  const interval = Math.max(1, layer.timing.intervalMs)
  const flash = Math.max(FLASH_FLOOR_MS, layer.timing.flashMs)

  const t = Math.max(0, tMs)
  const flashIndex = Math.floor(t / interval)
  const tInInterval = t - flashIndex * interval

  // Which pool item this flash lands on (deterministic per-pass shuffle).
  const passIndex = Math.floor(flashIndex / n)
  const posInPass = ((flashIndex % n) + n) % n
  const perm = seededPermutation(n, passIndex)
  const text = items[perm[posInPass]]

  const on = tInInterval < flash
  return { text, alpha: on ? layer.style.opacity : 0 }
}

/**
 * PURE: worst-case combined subliminal flash rate (flashes/s) across layers,
 * assuming their intervals line up. Above 3/s breaches WCAG 2.3.1.
 */
export function subliminalFlashRate(layers: TextLayer[]): number {
  return layers
    .filter((l) => l.timing.mode === 'subliminal' && l.content.some((c) => c.trim()))
    .reduce((sum, l) => sum + 1000 / Math.max(1, l.timing.intervalMs), 0)
}

/** Additive motion transform for this frame. */
function motionTransform(layer: TextLayer, tMs: number, beatHz?: number): LayerTransform {
  const { type, amount, syncToBeat } = layer.motion
  if (type === 'none' || amount <= 0) return { ...IDENTITY_TRANSFORM }

  const a = Math.max(0, Math.min(1, amount))
  const tSec = tMs / 1000
  const freq = syncToBeat && beatHz && beatHz > 0 ? safeVisualHz(beatHz) : DEFAULT_MOTION_HZ
  const phase = 2 * Math.PI * freq * tSec

  const tf: LayerTransform = { scale: 1, txFrac: 0, tyFrac: 0, alphaMul: 1 }

  switch (type) {
    case 'pulse':
      tf.scale = 1 + a * 0.14 * (0.5 + 0.5 * Math.sin(phase))
      break
    case 'waver':
      tf.scale = 1 + a * 0.06 * Math.sin(phase)
      tf.alphaMul = 1 - a * 0.45 * (0.5 + 0.5 * Math.sin(phase))
      break
    case 'drift': {
      // Slow translate — always gentle regardless of beat frequency.
      const slow = 2 * Math.PI * DEFAULT_MOTION_HZ * 0.35 * tSec
      tf.txFrac = a * 0.05 * Math.sin(slow)
      tf.tyFrac = a * 0.04 * Math.cos(slow * 0.8)
      break
    }
    case 'zoom': {
      const slow = 2 * Math.PI * DEFAULT_MOTION_HZ * 0.25 * tSec
      tf.scale = 1 + a * 0.2 * (0.5 + 0.5 * Math.sin(slow))
      break
    }
    case 'shake': {
      // Deterministic per-frame jitter (~60 buckets/sec) so it survives export.
      const bucket = Math.floor(tMs / 16)
      const rand = mulberry32(bucket)
      tf.txFrac = a * 0.02 * (rand() * 2 - 1)
      tf.tyFrac = a * 0.02 * (rand() * 2 - 1)
      break
    }
  }
  return tf
}

/**
 * PURE: effective render state for a layer at clock time `tMs`.
 * Combines the timing mode (text + base alpha) with additive motion.
 */
export function layerStateAt(layer: TextLayer, tMs: number, beatHz?: number): LayerState {
  let base: { text: string | null; alpha: number }
  switch (layer.timing.mode) {
    case 'sequence':
      base = sequenceState(layer, tMs)
      break
    case 'subliminal':
      base = subliminalState(layer, tMs)
      break
    case 'persistent':
    default:
      base = persistentState(layer, tMs)
      break
  }

  const transform = motionTransform(layer, tMs, beatHz)
  const alpha = Math.max(0, Math.min(1, base.alpha * transform.alphaMul))
  return { text: base.text, alpha, transform }
}

// ── Canvas helpers ─────────────────────────────────────────────────

function blendToComposite(blend: BlendMode): GlobalCompositeOperation {
  switch (blend) {
    case 'normal':
      return 'source-over'
    case 'exclusion':
      return 'exclusion'
    case 'difference':
      return 'difference'
    case 'screen':
      return 'screen'
    case 'overlay':
      return 'overlay'
    case 'multiply':
      return 'multiply'
    default:
      return 'source-over'
  }
}

/** 0..1 horizontal / vertical fractions for the 9-grid anchor. */
function anchorFractions(anchor: Anchor): { fx: number; fy: number } {
  const h = anchor[1] // l | c | r
  const v = anchor[0] // t | c | b
  const fx = h === 'l' ? 0 : h === 'r' ? 1 : 0.5
  const fy = v === 't' ? 0 : v === 'b' ? 1 : 0.5
  return { fx, fy }
}

/** Greedy word-wrap to a max pixel width using the current ctx font. */
function wrapLines(ctx: CanvasRenderingContext2D, text: string, maxW: number): string[] {
  const words = text.split(/\s+/).filter(Boolean)
  if (words.length === 0) return []
  const lines: string[] = []
  let cur = ''
  for (const w of words) {
    const test = cur ? `${cur} ${w}` : w
    if (ctx.measureText(test).width > maxW && cur) {
      lines.push(cur)
      cur = w
    } else {
      cur = test
    }
  }
  if (cur) lines.push(cur)
  return lines
}

// ── The shared frame renderer ──────────────────────────────────────

/**
 * PURE-ish: renders every text layer for clock time `tMs` into `ctx`.
 * Does not touch the video frame — the caller draws media first, then calls this.
 * Identical between live preview and export.
 */
export function drawFrame(
  ctx: CanvasRenderingContext2D,
  tMs: number,
  layers: TextLayer[],
  size: { w: number; h: number },
  beatHz?: number,
): void {
  const { w, h } = size
  if (!layers || layers.length === 0) return

  for (const layer of layers) {
    const state = layerStateAt(layer, tMs, beatHz)
    if (!state.text || state.alpha <= 0.001) continue

    let text = state.text
    if (layer.font.upper) text = text.toUpperCase()

    ctx.save()

    // Font (scaled by motion transform)
    const sizePx = Math.max(1, (layer.font.sizeVw / 100) * w * state.transform.scale)
    ctx.font = `${layer.font.weight} ${sizePx}px ${layer.font.family}`
    // letterSpacing is not in the older TS DOM lib; supported by modern canvases.
    ;(ctx as unknown as { letterSpacing: string }).letterSpacing = `${layer.font.letterSpacing}em`

    ctx.globalCompositeOperation = blendToComposite(layer.style.blend)
    ctx.globalAlpha = state.alpha
    ctx.fillStyle = layer.style.color

    // Anchor → base position (+ dx/dy % + motion translate)
    const { fx, fy } = anchorFractions(layer.pos.anchor)
    const margin = TEXT_MARGIN * w
    // Horizontal: pad in from the edges for l/r anchors.
    let x = fx === 0 ? margin : fx === 1 ? w - margin : w / 2
    x += (layer.pos.dx / 100) * w + state.transform.txFrac * w
    ctx.textAlign = fx === 0 ? 'left' : fx === 1 ? 'right' : 'center'

    const marginY = TEXT_MARGIN * h
    let anchorY = fy === 0 ? marginY : fy === 1 ? h - marginY : h / 2
    anchorY += (layer.pos.dy / 100) * h + state.transform.tyFrac * h

    // Wrap + vertical block placement
    const maxW = w * (1 - 2 * TEXT_MARGIN)
    const lines = wrapLines(ctx, text, maxW)
    const lineHeight = sizePx * 1.1
    const blockH = lines.length * lineHeight
    ctx.textBaseline = 'middle'

    // Position the block relative to the anchor's vertical edge.
    let blockCenter: number
    if (fy === 0) blockCenter = anchorY + blockH / 2
    else if (fy === 1) blockCenter = anchorY - blockH / 2
    else blockCenter = anchorY

    const firstLineCenter = blockCenter - blockH / 2 + lineHeight / 2
    lines.forEach((line, i) => {
      ctx.fillText(line, x, firstLineCenter + i * lineHeight)
    })

    ctx.restore()
  }
}

/**
 * Composable wrapper. `drawFrame` / `layerStateAt` are also importable directly
 * as standalone pure functions — this is just a convenience surface.
 */
export function useGlassComposer() {
  return { drawFrame, layerStateAt }
}

/** Fade-to-black over the whole frame: `env` 1 = untouched, 0 = black. */
export function drawFade(ctx: CanvasRenderingContext2D, size: { w: number; h: number }, env: number) {
  if (env >= 1) return
  ctx.save()
  ctx.globalCompositeOperation = 'source-over'
  ctx.globalAlpha = Math.max(0, Math.min(1, 1 - env))
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, size.w, size.h)
  ctx.restore()
}
