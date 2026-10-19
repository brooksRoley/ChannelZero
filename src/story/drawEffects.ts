import { mulberry32 } from '@/composables/useGlassComposer'
import { STROBE_PERIOD_MS, SUBLIMINAL_MS, type SubliminalFlash } from './effects'
import type { TimedKey, TimedLine } from './storyBeats'
import type { TextPlace } from './beatStyle'

/**
 * Canvas renderers for key-phrase effects and subliminals. Every effect is a
 * function of (key, tMs) only — randomness is seeded per key — so the live
 * preview and the recorded export draw identical frames.
 */

export const FONTS = {
  display: '"Anton", Impact, "Arial Narrow Bold", sans-serif',
  serif: '"Cormorant Garamond", Georgia, serif',
  mono: '"JetBrains Mono", Menlo, monospace',
  hand: '"Caveat", "Bradley Hand", cursive',
}

const FONT_HREF =
  'https://fonts.googleapis.com/css2?family=Anton&family=Caveat:wght@600&family=Cormorant+Garamond:ital,wght@0,500;1,300&family=JetBrains+Mono:wght@300&display=swap'

let fontsReady: Promise<void> | null = null

/** Load the effect fonts once (canvas text needs them loaded before drawing). */
export function loadEffectFonts(): Promise<void> {
  if (fontsReady) return fontsReady
  if (!document.querySelector(`link[href="${FONT_HREF}"]`)) {
    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = FONT_HREF
    document.head.appendChild(link)
  }
  const loads = [
    `48px ${FONTS.display}`, `500 48px ${FONTS.serif}`, `italic 300 48px ${FONTS.serif}`,
    `300 48px ${FONTS.mono}`, `600 48px ${FONTS.hand}`,
  ].map((f) => document.fonts.load(f).catch(() => []))
  const timeout = new Promise((r) => setTimeout(r, 4000))
  fontsReady = Promise.race([Promise.all(loads), timeout]).then(() => undefined)
  return fontsReady
}

// ── Helpers ──────────────────────────────────────────────────────

type Size = { w: number; h: number }

const clamp01 = (x: number) => Math.max(0, Math.min(1, x))
const easeOut = (x: number) => 1 - Math.pow(1 - clamp01(x), 3)

/** Set `font` at the largest px ≤ `px` whose `text` fits `maxW`. Returns that px. */
function fitFont(ctx: CanvasRenderingContext2D, style: string, family: string, text: string, px: number, maxW: number): number {
  ctx.font = `${style} ${px}px ${family}`
  const w = ctx.measureText(text).width
  if (w > maxW) {
    px = Math.max(8, Math.floor(px * (maxW / w)))
    ctx.font = `${style} ${px}px ${family}`
  }
  return px
}

/** Fade-out over the last `ms` of the key's window. */
function tailAlpha(key: TimedKey, tMs: number, ms = 350): number {
  return clamp01((key.endMs - tMs) / ms)
}

function glow(ctx: CanvasRenderingContext2D, px: number, color = 'rgba(0,0,0,0.65)') {
  ctx.shadowColor = color
  ctx.shadowBlur = px * 0.25
}

// ── Effects ──────────────────────────────────────────────────────

function drawFlash(ctx: CanvasRenderingContext2D, key: TimedKey, tMs: number, { w, h }: Size) {
  const u = tMs - key.startMs
  if (tMs < key.strobeEndMs && Math.floor(u / (STROBE_PERIOD_MS / 2)) % 2 === 1) return // strobe "off" half
  const text = key.text.toUpperCase()
  const px = fitFont(ctx, '', FONTS.display, text, w * 0.14, w * 0.86)
  ctx.globalAlpha = tailAlpha(key, tMs)
  ctx.fillStyle = '#ffffff'
  // Strobe in inverted letters (they cut the footage), then settle solid.
  if (tMs < key.strobeEndMs) ctx.globalCompositeOperation = 'difference'
  else glow(ctx, px)
  ctx.fillText(text, w / 2, h / 2)
}

function drawSlam(ctx: CanvasRenderingContext2D, key: TimedKey, tMs: number, { w, h }: Size) {
  const u = tMs - key.startMs
  const text = key.text.toUpperCase()
  const scale = 1 + 0.6 * (1 - easeOut(u / 180))
  const shake = u < 320 ? (1 - u / 320) * 0.012 * w : 0
  const rand = mulberry32(key.seed * 1000 + Math.floor(u / 16))
  const x = w / 2 + (rand() * 2 - 1) * shake
  const y = h / 2 + (rand() * 2 - 1) * shake
  const px = fitFont(ctx, '', FONTS.display, text, w * 0.15 * scale, w * 0.9 * scale)
  const split = w * (u < 400 ? 0.005 : 0.0015)
  ctx.globalAlpha = tailAlpha(key, tMs) * clamp01(u / 60)
  ctx.globalCompositeOperation = 'screen'
  ctx.fillStyle = '#ff2a55'
  ctx.fillText(text, x - split, y)
  ctx.fillStyle = '#2af0ff'
  ctx.fillText(text, x + split, y)
  ctx.globalCompositeOperation = 'source-over'
  glow(ctx, px)
  ctx.fillStyle = '#ffffff'
  ctx.fillText(text, x, y)
}

function drawWhisper(ctx: CanvasRenderingContext2D, key: TimedKey, tMs: number, { w, h }: Size) {
  const u = tMs - key.startMs
  const d = key.endMs - key.startMs
  const rand = mulberry32(key.seed * 31)
  const px = fitFont(ctx, 'italic 300', FONTS.serif, key.text, w * 0.045, w * 0.8)
  ;(ctx as unknown as { letterSpacing: string }).letterSpacing = '0.06em'
  ctx.globalAlpha = 0.75 * clamp01(u / 600) * tailAlpha(key, tMs, 700)
  ctx.fillStyle = '#ece6ff'
  glow(ctx, px, 'rgba(60,40,120,0.8)')
  const x = w / 2 + (rand() - 0.5) * w * 0.2
  const y = h * (0.6 + (rand() - 0.5) * 0.1) - (u / d) * h * 0.04
  ctx.fillText(key.text, x, y)
}

function drawType(ctx: CanvasRenderingContext2D, key: TimedKey, tMs: number, { w, h }: Size) {
  const span = Math.max(1, key.spokenEndMs - key.spokenStartMs)
  const n = Math.ceil(key.text.length * clamp01((tMs - key.spokenStartMs) / span))
  const px = fitFont(ctx, '300', FONTS.mono, key.text, w * 0.045, w * 0.86)
  const full = ctx.measureText(key.text).width
  const shown = key.text.slice(0, Math.max(0, n))
  const x = (w - full) / 2
  ctx.textAlign = 'left'
  ctx.globalAlpha = tailAlpha(key, tMs)
  glow(ctx, px)
  ctx.fillStyle = '#d7ffe9'
  ctx.fillText(shown, x, h / 2)
  const typing = n < key.text.length
  if (typing || Math.floor((tMs - key.startMs) / 500) % 2 === 0) {
    ctx.fillRect(x + ctx.measureText(shown).width + px * 0.1, h / 2 - px * 0.45, px * 0.5, px * 0.9)
  }
}

function drawEcho(ctx: CanvasRenderingContext2D, key: TimedKey, tMs: number, { w, h }: Size) {
  const u = tMs - key.startMs
  const text = key.text.toUpperCase()
  const base = fitFont(ctx, '500', FONTS.serif, text, w * 0.075, w * 0.7)
  const a = tailAlpha(key, tMs, 600) * clamp01(u / 300)
  ctx.fillStyle = '#ffffff'
  for (let i = 3; i >= 1; i--) {
    const phase = ((u / 1000) * 0.5 + i / 3) % 1 // 0.5 Hz ripple
    ctx.font = `500 ${base * (1 + phase * 0.45)}px ${FONTS.serif}`
    ctx.globalAlpha = a * (1 - phase) * 0.3
    ctx.fillText(text, w / 2, h / 2)
  }
  ctx.font = `500 ${base}px ${FONTS.serif}`
  ctx.globalAlpha = a
  glow(ctx, base)
  ctx.fillText(text, w / 2, h / 2)
}

const SCATTER_SPOTS = [[0.25, 0.3], [0.72, 0.28], [0.5, 0.5], [0.3, 0.7], [0.74, 0.68], [0.5, 0.22], [0.5, 0.8]]
const SCATTER_FACES: [string, string, number][] = [
  ['', FONTS.display, 0.09], ['italic 300', FONTS.serif, 0.07], ['300', FONTS.mono, 0.05],
]

function drawScatter(ctx: CanvasRenderingContext2D, key: TimedKey, tMs: number, { w, h }: Size) {
  const u = tMs - key.startMs
  const words = key.text.split(/\s+/)
  const rand = mulberry32(key.seed * 97)
  const order = SCATTER_SPOTS.map((s) => [rand(), s] as const).sort((a, b) => a[0] - b[0]).map(([, s]) => s)
  const tail = tailAlpha(key, tMs)
  words.forEach((word, i) => {
    const t = u - i * 140
    if (t < 0) return
    const [style, family, size] = SCATTER_FACES[i % SCATTER_FACES.length]
    const [fx, fy] = order[i % order.length]
    const pop = 1 + 0.3 * (1 - easeOut(t / 150))
    const px = fitFont(ctx, style, family, i % 3 === 0 ? word.toUpperCase() : word, w * size * pop, w * 0.42)
    ctx.globalAlpha = tail * clamp01(t / 120)
    ctx.fillStyle = i % 2 ? '#ffe7b0' : '#ffffff'
    glow(ctx, px)
    ctx.fillText(i % 3 === 0 ? word.toUpperCase() : word, fx * w, fy * h)
  })
}

function drawHand(ctx: CanvasRenderingContext2D, key: TimedKey, tMs: number, { w, h }: Size) {
  const u = tMs - key.startMs
  const rand = mulberry32(key.seed * 13)
  const px = fitFont(ctx, '600', FONTS.hand, key.text, w * 0.08, w * 0.8)
  const tw = ctx.measureText(key.text).width
  const x = w / 2 + (rand() - 0.5) * w * 0.3
  const y = h / 2 + (rand() - 0.5) * h * 0.24
  const write = clamp01(u / Math.min(900, Math.max(300, key.spokenEndMs - key.spokenStartMs)))
  ctx.translate(x, y)
  ctx.rotate((rand() - 0.5) * 0.2)
  ctx.beginPath()
  ctx.rect(-tw / 2 - px, -px, (tw + 2 * px) * write, px * 2)
  ctx.clip()
  ctx.globalAlpha = tailAlpha(key, tMs, 600)
  glow(ctx, px)
  ctx.fillStyle = '#ffd9a8'
  ctx.fillText(key.text, 0, 0)
}

function drawBloom(ctx: CanvasRenderingContext2D, key: TimedKey, tMs: number, { w, h }: Size) {
  const u = tMs - key.startMs
  const d = key.endMs - key.startMs
  const inA = easeOut(u / 800)
  const outA = clamp01((key.endMs - tMs) / 900)
  const px = fitFont(ctx, '500', FONTS.serif, key.text, w * 0.062 * (1 + 0.03 * (u / d)), w * 0.8)
  ;(ctx as unknown as { letterSpacing: string }).letterSpacing = '0.02em'
  ctx.globalAlpha = 0.95 * inA * outA
  ctx.shadowColor = 'rgba(255, 186, 120, 0.55)'
  ctx.shadowBlur = px * 0.6
  ctx.fillStyle = '#fff3e0'
  ctx.fillText(key.text, w / 2, h * 0.4)
}

const DRAW: Record<TimedKey['effect'], typeof drawFlash> = {
  flash: drawFlash, slam: drawSlam, whisper: drawWhisper, type: drawType, echo: drawEcho,
  scatter: drawScatter, hand: drawHand, bloom: drawBloom,
}

/** Soft dark band behind the reading line, from y0 (clear) to y1 (darkest). */
function shadeBand(ctx: CanvasRenderingContext2D, w: number, y0: number, y1: number, alpha: number) {
  const band = ctx.createLinearGradient(0, y0, 0, y1)
  band.addColorStop(0, 'rgba(0,0,0,0)')
  band.addColorStop(1, `rgba(0,0,0,${0.55 * alpha})`)
  ctx.fillStyle = band
  ctx.fillRect(0, Math.min(y0, y1), w, Math.abs(y1 - y0))
}

/**
 * The reading line: the current sentence on a soft backdrop (lower third by
 * default), each word brightening as it's spoken, key words in warm gold.
 * Middle sits just below centre so gentle key phrases (at 0.4 h) stay clear.
 */
export function drawReadingLine(ctx: CanvasRenderingContext2D, line: TimedLine, tMs: number, { w, h }: Size, place: TextPlace = 'low') {
  const alpha = Math.min(clamp01((tMs - line.startMs) / 350), clamp01((line.endMs - tMs) / 450))
  if (alpha <= 0) return
  ctx.save()
  if (place === 'low') shadeBand(ctx, w, h * 0.6, h, alpha)
  else if (place === 'high') shadeBand(ctx, w, h * 0.4, 0, alpha)
  else {
    shadeBand(ctx, w, h * 0.44, h * 0.6, alpha)
    shadeBand(ctx, w, h * 0.76, h * 0.6, alpha)
  }

  const px = Math.max(18, Math.round(w * 0.036))
  ctx.font = `500 ${px}px ${FONTS.serif}`
  ctx.textBaseline = 'middle'
  ctx.textAlign = 'left'
  const space = ctx.measureText(' ').width
  const maxW = w * 0.8

  // Lay words into rows.
  const rows: { words: { text: string; i: number; wpx: number }[]; width: number }[] = [{ words: [], width: 0 }]
  line.words.forEach((word, i) => {
    const wpx = ctx.measureText(word.text).width
    let row = rows[rows.length - 1]
    if (row.words.length && row.width + space + wpx > maxW) rows.push((row = { words: [], width: 0 }))
    row.width += (row.words.length ? space : 0) + wpx
    row.words.push({ text: word.text, i, wpx })
  })

  const lh = px * 1.35
  const block = (rows.length - 1) * lh
  const top = place === 'high' ? h * 0.12 : place === 'middle' ? h * 0.6 - block / 2 : h * 0.88 - block
  let offset = 0
  const charAt: number[] = line.words.map((wd) => { const o = offset; offset += wd.text.length + 1; return o })
  const inKey = (i: number) => line.keySpans.some(([a, b]) => charAt[i] >= a && charAt[i] < b)

  ctx.shadowColor = 'rgba(0,0,0,0.7)'
  ctx.shadowBlur = px * 0.3
  rows.forEach((row, r) => {
    let x = (w - row.width) / 2
    const y = top + r * lh
    for (const word of row.words) {
      const spoken = tMs >= line.words[word.i].startMs
      ctx.globalAlpha = alpha * (spoken ? 1 : 0.5)
      ctx.fillStyle = inKey(word.i) ? '#ffd9a0' : '#f7f1e6'
      ctx.fillText(word.text, x, y)
      x += word.wpx + space
    }
  })
  ctx.restore()
}

/** Draw every key phrase on screen at tMs. */
export function drawKeys(ctx: CanvasRenderingContext2D, keys: TimedKey[], tMs: number, size: Size) {
  for (const key of keys) {
    if (tMs < key.startMs || tMs >= key.endMs) continue
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    DRAW[key.effect](ctx, key, tMs, size)
    ctx.restore()
  }
}

const SUB_FACES: [string, string][] = [['', FONTS.display], ['italic 300', FONTS.serif], ['300', FONTS.mono], ['600', FONTS.hand]]

/** Draw any subliminal whose brief window contains tMs. */
export function drawSubliminals(ctx: CanvasRenderingContext2D, subs: SubliminalFlash[], tMs: number, { w, h }: Size, gentle = false) {
  for (const s of subs) {
    if (tMs < s.atMs || tMs >= s.atMs + SUBLIMINAL_MS) continue
    const rand = mulberry32(s.seed * 7 + 3)
    const [style, family] = SUB_FACES[Math.floor(rand() * SUB_FACES.length)]
    ctx.save()
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    fitFont(ctx, style, family, s.text, w * (0.06 + rand() * 0.05), w * 0.6)
    // Gentle: a faint presence, felt more than seen. Bold: an inverted cut.
    ctx.globalAlpha = gentle ? 0.18 : 0.6
    ctx.globalCompositeOperation = gentle ? 'source-over' : 'difference'
    ctx.fillStyle = gentle ? '#efe6ff' : '#ffffff'
    ctx.fillText(s.text, w * (0.2 + rand() * 0.6), h * (0.2 + rand() * 0.6))
    ctx.restore()
  }
}

/** Small attribution line (ElevenLabs free plan requires it). */
export function drawCredit(ctx: CanvasRenderingContext2D, text: string, alpha: number, { w, h }: Size) {
  if (alpha <= 0) return
  ctx.save()
  ctx.font = `300 ${Math.round(w * 0.014)}px ${FONTS.mono}`
  ctx.textAlign = 'right'
  ctx.textBaseline = 'bottom'
  ctx.globalAlpha = alpha * 0.7
  ctx.fillStyle = '#ffffff'
  ctx.fillText(text, w * 0.97, h * 0.96)
  ctx.restore()
}
