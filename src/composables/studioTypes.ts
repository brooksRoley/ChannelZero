/**
 * Glass Studio — shared data model for the subliminal / entrainment authoring studio.
 *
 * Owned by the Foundation layer. The composer (`useGlassComposer`), the export
 * pipeline (`useGlassExport`) and the control panels all speak these types.
 *
 * See docs/superpowers/specs/2026-08-04-glass-studio-subliminal-design.md
 */

// 9-grid anchor: top/center/bottom × left/center/right
export type Anchor = 'tl' | 'tc' | 'tr' | 'cl' | 'cc' | 'cr' | 'bl' | 'bc' | 'br'

export type BlendMode =
  | 'normal'
  | 'exclusion'
  | 'difference'
  | 'screen'
  | 'overlay'
  | 'multiply'

export type TimingMode = 'persistent' | 'sequence' | 'subliminal'

export type MotionType = 'none' | 'pulse' | 'drift' | 'zoom' | 'shake' | 'waver'

// Entrainment bands (used by the binaural layer, defined here so the model is complete)
export type Band = 'delta' | 'theta' | 'alpha' | 'beta' | 'gamma'

export interface TextLayer {
  id: string
  content: string[] // 1 = static; many = sequence / flash pool
  font: {
    family: string
    sizeVw: number
    weight: number
    letterSpacing: number
    upper: boolean
  }
  pos: {
    anchor: Anchor
    dx: number // % of viewport width
    dy: number // % of viewport height
  }
  style: {
    color: string
    opacity: number // 0..1
    blend: BlendMode
  }
  timing: {
    mode: TimingMode
    holdMs: number
    fadeMs: number
    intervalMs: number
    flashMs: number
  }
  motion: {
    type: MotionType
    amount: number // 0..1 authoring-normalized strength
    syncToBeat: boolean
  }
}

export interface BinauralConfig {
  enabled: boolean
  mode: 'preset' | 'journey'
  band: Band // preset mode
  journey: { band: Band; durationS: number }[] // journey mode, auto-fit to media length
  volume: number // 0..100
  /** Texture bed under the beat, 0..1 each (see useBinauralEngine). */
  textures: { noise: number; pad: number; shimmer: number }
}

export interface GlassComposition {
  textLayers: TextLayer[]
  binaural: BinauralConfig
  /** Fade in/out at the edges of the (trimmed) session, seconds. 0 = hard cut. */
  fadeS: number
  recipeId?: string
}

// ── Factory helpers ────────────────────────────────────────────────

let _idCounter = 0
function makeId(): string {
  _idCounter += 1
  // crypto.randomUUID isn't guaranteed in every target; a monotonic id is enough here.
  return `layer-${Date.now().toString(36)}-${_idCounter}`
}

export function makeDefaultTextLayer(overrides: Partial<TextLayer> = {}): TextLayer {
  const base: TextLayer = {
    id: makeId(),
    content: [''],
    font: {
      family: 'system-ui, -apple-system, sans-serif',
      sizeVw: 10,
      weight: 900,
      letterSpacing: -0.02,
      upper: true,
    },
    pos: {
      anchor: 'cc',
      dx: 0,
      dy: 0,
    },
    style: {
      color: '#ffffff',
      opacity: 1,
      blend: 'exclusion',
    },
    timing: {
      mode: 'persistent',
      holdMs: 2000,
      fadeMs: 400,
      intervalMs: 4000,
      flashMs: 200,
    },
    motion: {
      type: 'none',
      amount: 0.5,
      syncToBeat: false,
    },
  }
  return {
    ...base,
    ...overrides,
    font: { ...base.font, ...overrides.font },
    pos: { ...base.pos, ...overrides.pos },
    style: { ...base.style, ...overrides.style },
    timing: { ...base.timing, ...overrides.timing },
    motion: { ...base.motion, ...overrides.motion },
  }
}

export function makeDefaultBinauralConfig(): BinauralConfig {
  return {
    enabled: false,
    mode: 'preset',
    band: 'theta',
    journey: [],
    volume: 40,
    textures: { noise: 0, pad: 0, shimmer: 0 },
  }
}

export function makeDefaultComposition(): GlassComposition {
  return {
    textLayers: [makeDefaultTextLayer()],
    binaural: makeDefaultBinauralConfig(),
    fadeS: 3,
  }
}
