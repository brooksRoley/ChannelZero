/**
 * Glass Studio — recipe presets.
 *
 * A recipe is a named, fully-formed `GlassComposition` starting point that
 * teaches the studio by example: apply one, then edit the Text and Sound panels
 * from there. Built entirely with the `studioTypes` factories so recipes never
 * duplicate the schema. Each links to a real `/learn` article for the honest,
 * non-overclaiming context behind its bands.
 *
 * See docs/superpowers/specs/2026-08-04-glass-studio-subliminal-design.md
 * ("Teaching: recipes + deep-dive links").
 */

import {
  makeDefaultTextLayer,
  makeDefaultBinauralConfig,
  type BinauralConfig,
  type GlassComposition,
} from '@/composables/studioTypes'

export interface GlassRecipe {
  id: string
  name: string
  /** One short line describing the recipe (chip subtitle). */
  blurb: string
  /** Slug of a real `/learn/:slug` article (verified against src/data/learn.ts). */
  learnSlug?: string
  /** Returns a fresh, fully-formed composition each call (no shared references). */
  build(): GlassComposition
}

/** Enable + override the default binaural config in one place. */
function binaural(overrides: Partial<BinauralConfig>): BinauralConfig {
  return { ...makeDefaultBinauralConfig(), enabled: true, ...overrides }
}

export const GLASS_RECIPES: GlassRecipe[] = [
  {
    id: 'confidence-subliminal',
    name: 'Confidence subliminal',
    blurb: 'Theta journey with self-directed affirmations flashed at the edge of notice.',
    learnSlug: 'suggestion-induction',
    build: (): GlassComposition => ({
      fadeS: 3,
      recipeId: 'confidence-subliminal',
      textLayers: [
        makeDefaultTextLayer({
          content: [
            'I meet challenges with a steady mind',
            'I trust the work I have put in',
            'I speak clearly and stand at ease',
            'I belong in the room',
            'I let calm carry me forward',
          ],
          font: {
            family: 'system-ui, -apple-system, sans-serif',
            sizeVw: 6,
            weight: 500,
            letterSpacing: 0.02,
            upper: false,
          },
          pos: { anchor: 'cc', dx: 0, dy: 0 },
          style: { color: '#ffffff', opacity: 0.18, blend: 'screen' },
          timing: { mode: 'subliminal', holdMs: 2000, fadeMs: 400, intervalMs: 3000, flashMs: 200 },
        }),
      ],
      // Alpha to settle, then rest in theta — the workhorse band for receptive depth.
      binaural: binaural({
        textures: { noise: 0, pad: 0.4, shimmer: 0.2 },
        mode: 'journey',
        band: 'theta',
        journey: [
          { band: 'alpha', durationS: 30 },
          { band: 'theta', durationS: 120 },
        ],
        volume: 35,
      }),
    }),
  },

  {
    id: 'calm-descent',
    name: 'Calm descent',
    blurb: 'Alpha to theta journey under a persistent breath cue.',
    learnSlug: 'targeting-brainwave-states',
    build: (): GlassComposition => ({
      fadeS: 6,
      recipeId: 'calm-descent',
      textLayers: [
        makeDefaultTextLayer({
          content: ['Breathe in… and slowly out'],
          font: {
            family: 'Georgia, "Times New Roman", serif',
            sizeVw: 4,
            weight: 400,
            letterSpacing: 0.04,
            upper: false,
          },
          pos: { anchor: 'bc', dx: 0, dy: -6 },
          style: { color: '#ffffff', opacity: 0.55, blend: 'normal' },
          timing: { mode: 'persistent', holdMs: 2000, fadeMs: 1200, intervalMs: 4000, flashMs: 200 },
          motion: { type: 'waver', amount: 0.3, syncToBeat: false },
        }),
      ],
      binaural: binaural({
        textures: { noise: 0.4, pad: 0.6, shimmer: 0 },
        mode: 'journey',
        band: 'theta',
        journey: [
          { band: 'alpha', durationS: 60 },
          { band: 'theta', durationS: 120 },
        ],
        volume: 40,
      }),
    }),
  },

  {
    id: 'focus-field',
    name: 'Focus field',
    blurb: 'Steady gamma anchor with a short rotation of focus cues.',
    learnSlug: 'targeting-brainwave-states',
    build: (): GlassComposition => ({
      fadeS: 3,
      recipeId: 'focus-field',
      textLayers: [
        makeDefaultTextLayer({
          content: ['Focus', 'One thing', 'Begin', 'Stay with it'],
          font: {
            family: '"SF Mono", ui-monospace, Menlo, Consolas, monospace',
            sizeVw: 7,
            weight: 500,
            letterSpacing: 0.08,
            upper: true,
          },
          pos: { anchor: 'cc', dx: 0, dy: 0 },
          style: { color: '#ffffff', opacity: 0.7, blend: 'exclusion' },
          timing: { mode: 'sequence', holdMs: 2600, fadeMs: 500, intervalMs: 4000, flashMs: 200 },
        }),
      ],
      binaural: binaural({
        textures: { noise: 0.3, pad: 0, shimmer: 0.3 },
        mode: 'preset',
        band: 'gamma',
        journey: [],
        volume: 35,
      }),
    }),
  },

  {
    id: 'sleep-drift',
    name: 'Sleep drift',
    blurb: 'A long descent toward delta with a single fading release cue.',
    learnSlug: 'binaural-beats-protocol',
    build: (): GlassComposition => ({
      fadeS: 10,
      recipeId: 'sleep-drift',
      textLayers: [
        makeDefaultTextLayer({
          content: ['Let the day go'],
          font: {
            family: 'Georgia, "Times New Roman", serif',
            sizeVw: 4,
            weight: 300,
            letterSpacing: 0.05,
            upper: false,
          },
          pos: { anchor: 'cc', dx: 0, dy: 0 },
          style: { color: '#ffffff', opacity: 0.35, blend: 'normal' },
          timing: { mode: 'persistent', holdMs: 2000, fadeMs: 2000, intervalMs: 4000, flashMs: 200 },
          motion: { type: 'drift', amount: 0.2, syncToBeat: false },
        }),
      ],
      binaural: binaural({
        textures: { noise: 0.6, pad: 0.7, shimmer: 0 },
        mode: 'journey',
        band: 'delta',
        journey: [
          { band: 'alpha', durationS: 30 },
          { band: 'theta', durationS: 90 },
          { band: 'delta', durationS: 180 },
        ],
        volume: 30,
      }),
    }),
  },

  {
    id: 'creative-alpha',
    name: 'Creative alpha',
    blurb: 'Relaxed alpha with drifting, open-ended prompts.',
    learnSlug: 'binaural-entrainment',
    build: (): GlassComposition => ({
      fadeS: 4,
      recipeId: 'creative-alpha',
      textLayers: [
        makeDefaultTextLayer({
          content: ['What if…', 'Follow the thread', 'No wrong turns', 'Keep the pen moving'],
          font: {
            family: '"Helvetica Neue", Helvetica, Arial, sans-serif',
            sizeVw: 5,
            weight: 400,
            letterSpacing: 0.01,
            upper: false,
          },
          pos: { anchor: 'tc', dx: 0, dy: 8 },
          style: { color: '#ffffff', opacity: 0.5, blend: 'screen' },
          timing: { mode: 'sequence', holdMs: 3200, fadeMs: 800, intervalMs: 4000, flashMs: 200 },
          motion: { type: 'drift', amount: 0.25, syncToBeat: false },
        }),
      ],
      binaural: binaural({
        textures: { noise: 0, pad: 0.3, shimmer: 0.5 },
        mode: 'preset',
        band: 'alpha',
        journey: [],
        volume: 38,
      }),
    }),
  },
]
