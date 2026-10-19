import { describe, it, expect } from 'vitest'
import { parseStory, buildTimeline, lineAt } from '@/story/storyBeats'
import {
  resolveScenes, remapStyles, backdropAt, cleanStyle, BACKDROP_XFADE_MS, type Backdrop, type BeatStyle,
} from '@/story/beatStyle'

const field: Backdrop = { kind: 'field' }
const red: Backdrop = { kind: 'solid', color: '#ff0000' }
const blue: Backdrop = { kind: 'solid', color: '#0000ff' }

describe('resolveScenes', () => {
  it('carries backdrop and placement forward until a beat changes them', () => {
    const scenes = resolveScenes([undefined, { backdrop: red }, { place: 'high' }, { backdrop: blue }], 5, field)
    expect(scenes.map((s) => s.backdrop)).toEqual([field, red, red, blue, blue])
    expect(scenes.map((s) => s.place)).toEqual(['low', 'low', 'high', 'high', 'high'])
  })
})

describe('backdropAt', () => {
  const tl = buildTimeline(parseStory('One.\n\nTwo.\n\nThree.'), { look: 'gentle' })

  it('crossfades into a new backdrop from the beat start', () => {
    const scenes = resolveScenes([undefined, { backdrop: red }], 3, field)
    const start = tl.beats[1].startMs
    expect(backdropAt(tl, scenes, start)).toEqual({ from: field, to: red, k: 0 })
    expect(backdropAt(tl, scenes, start + BACKDROP_XFADE_MS / 2)?.k).toBeCloseTo(0.5)
    expect(backdropAt(tl, scenes, start + BACKDROP_XFADE_MS)).toEqual({ from: field, to: red, k: 1 })
  })

  it('holds steady when the backdrop is unchanged', () => {
    const scenes = resolveScenes([{ backdrop: red }], 3, field)
    expect(backdropAt(tl, scenes, tl.beats[2].startMs)).toEqual({ from: red, to: red, k: 1 })
  })
})

describe('remapStyles', () => {
  const ids = (...xs: string[]) => xs.map((id) => ({ id }))
  const a: BeatStyle = { backdrop: red }
  const b: BeatStyle = { place: 'high' }

  it('follows a beat that moved', () => {
    expect(remapStyles(ids('x', 'y'), ids('new', 'x', 'y'), [a, b])).toEqual([undefined, a, b])
  })

  it('keeps the style of a beat edited in place', () => {
    expect(remapStyles(ids('x', 'y'), ids('x', 'y2'), [a, b])).toEqual([a, b])
  })

  it('drops the style of a deleted beat', () => {
    expect(remapStyles(ids('x', 'y'), ids('y'), [a, b])).toEqual([b])
  })
})

describe('cleanStyle', () => {
  it('collapses an empty style to undefined', () => {
    expect(cleanStyle({ holdMs: 0, backdrop: undefined })).toBeUndefined()
    expect(cleanStyle({ holdMs: 500 })).toEqual({ holdMs: 500 })
  })
})

describe('timeline options from the editor', () => {
  const beats = parseStory('[induce]\nBreathe *slowly* now.\n\nAnd *rest* here.')

  it('extends a beat by its hold, shifting everything after', () => {
    const plain = buildTimeline(beats)
    const held = buildTimeline(beats, { holdMs: [4000] })
    expect(held.beats[0].endMs - plain.beats[0].endMs).toBe(4000)
    expect(held.beats[1].startMs - plain.beats[1].startMs).toBe(4000)
    expect(held.durationMs - plain.durationMs).toBe(4000)
  })

  it('uses the beat effect for keys without an explicit one', () => {
    const tl = buildTimeline(beats, { look: 'bold', effects: [undefined, 'echo'] })
    expect(tl.keys.find((k) => k.text === 'rest')?.effect).toBe('echo')
    expect(tl.keys.find((k) => k.text === 'slowly')?.effect).not.toBe('echo')
  })

  it('still softens a sharp beat effect in the gentle look', () => {
    const tl = buildTimeline(beats, { look: 'gentle', effects: ['slam', 'slam'] })
    expect(tl.keys.every((k) => k.effect === 'bloom')).toBe(true)
  })

  it('tags reading lines with their beat', () => {
    const tl = buildTimeline(beats)
    expect(lineAt(tl, tl.beats[1].lines[0].startMs + 1)?.beat).toBe(1)
  })
})
