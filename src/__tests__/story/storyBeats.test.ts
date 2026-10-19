import { describe, it, expect } from 'vitest'
import {
  parseStory, buildTimeline, frameAt, entrainmentAt, depthDimAt, beatIndexAt,
  GLIDE_MS, STAGES,
} from '@/story/storyBeats'
import { chunkPhrases, splitWords } from '@/story/phrases'
import { BANDS } from '@/composables/useStudioBinaural'
import { overlayLayer, canvasSizeFor } from '@/story/useStoryPlayer'
import { STORY_SAMPLES } from '@/data/storySamples'

describe('chunkPhrases', () => {
  it('breaks at sentence ends and caps phrases at three words', () => {
    const ps = chunkPhrases(splitWords('Breathe. Let the room grow quiet around you.'))
    expect(ps.map((p) => p.text)).toEqual(['Breathe.', 'Let the room', 'grow quiet around', 'you.'])
    expect(ps[0].isPausePoint).toBe(true)
    expect(ps[1].isPausePoint).toBe(false)
  })
})

describe('parseStory', () => {
  it('splits beats on blank lines and applies stage markers', () => {
    const beats = parseStory('[induce]\nOne line.\n\nTwo\nlines.\n[deepen]\nDown.\n[pause 2.5]\n[wake]\nUp.')
    expect(beats).toEqual([
      { stage: 'induce', text: 'One line.' },
      { stage: 'induce', text: 'Two lines.' },
      { stage: 'deepen', text: 'Down.' },
      { stage: 'deepen', text: '', pauseMs: 2500 },
      { stage: 'wake', text: 'Up.' },
    ])
  })

  it('assigns an automatic arc when there are no markers', () => {
    const beats = parseStory('a.\n\nb.\n\nc.\n\nd.\n\ne.')
    expect(beats.map((b) => b.stage)).toEqual(['induce', 'induce', 'deepen', 'deepen', 'wake'])
  })

  it('treats marker-like text inside a paragraph as words', () => {
    expect(parseStory('say [deepen] now')[0].text).toBe('say [deepen] now')
  })

  it('parses every starter story into beats', () => {
    for (const s of STORY_SAMPLES) expect(parseStory(s.text).length).toBeGreaterThan(3)
  })
})

describe('buildTimeline', () => {
  const beats = parseStory('[induce]\nSettle in. Let go.\n\n[deepen]\nSlower now, and slower.\n[pause 2]\n[wake]\nEyes open.')

  it('lays beats end to end after the lead-in, with the tail after', () => {
    const tl = buildTimeline(beats, { leadInMs: 1000, tailMs: 2000 })
    expect(tl.beats[0].startMs).toBe(1000)
    for (let i = 1; i < tl.beats.length; i++) expect(tl.beats[i].startMs).toBe(tl.beats[i - 1].endMs)
    expect(tl.durationMs).toBe(tl.beats[tl.beats.length - 1].endMs + 2000)
  })

  it('stretches a beat to fit its voice and starts the first phrase with it', () => {
    const quiet = buildTimeline(beats)
    const voiced = buildTimeline(beats, { voiceMs: [20000, null, null, null] })
    const b = voiced.beats[0]
    expect(b.voiced).toBe(true)
    expect(b.bodyEndMs - b.startMs).toBe(20000)
    expect(b.phrases[0].startMs).toBe(b.startMs)
    expect(voiced.durationMs).toBeGreaterThan(quiet.durationMs)
  })

  it('keeps phrases contiguous and inside their beat', () => {
    const tl = buildTimeline(beats)
    for (const b of tl.beats) {
      b.phrases.forEach((p, i) => {
        expect(p.endMs).toBeGreaterThan(p.startMs)
        if (i > 0) expect(p.startMs).toBeCloseTo(b.phrases[i - 1].endMs)
        expect(p.endMs).toBeLessThanOrEqual(b.endMs)
      })
    }
  })

  it('paces deeper stages slower and gives pause beats no phrases', () => {
    const same = 'one two three four five six.'
    const tl = buildTimeline(parseStory(`[induce]\n${same}\n[deepen]\n${same}`))
    const [a, d] = tl.beats
    expect(d.bodyEndMs - d.startMs).toBeGreaterThan(a.bodyEndMs - a.startMs)
    const p = buildTimeline(beats).beats[2]
    expect(p.phrases).toEqual([])
    expect(p.endMs - p.startMs).toBe(2000)
  })

  it('carries each stage band onto its beat', () => {
    const tl = buildTimeline(beats)
    expect(tl.beats[0].beatHz).toBe(BANDS[STAGES.induce.band].beatHz)
    expect(tl.beats[2].beatHz).toBe(BANDS[STAGES.deepen.band].beatHz)
  })
})

describe('sampling', () => {
  const tl = buildTimeline(parseStory('[induce]\nHello there, friend.\n\n[final]\nRest.'), { leadInMs: 2000 })
  const [first, second] = tl.beats

  it('shows nothing during the lead-in', () => {
    expect(frameAt(tl, 500).text).toBeNull()
    expect(beatIndexAt(tl, 500)).toBe(0)
  })

  it('shows the phrase being spoken, faded in', () => {
    const p = first.phrases[0]
    const mid = frameAt(tl, (p.startMs + p.endMs) / 2)
    expect(mid.text).toBe(p.text)
    expect(mid.alpha).toBeCloseTo(STAGES.induce.opacity)
    expect(frameAt(tl, p.startMs).alpha).toBe(0)
  })

  it('glides the binaural beat and the depth dim over GLIDE_MS', () => {
    const from = first.beatHz
    const to = second.beatHz
    expect(entrainmentAt(tl, second.startMs).beatHz).toBe(from)
    expect(entrainmentAt(tl, second.startMs + GLIDE_MS / 2).beatHz).toBeCloseTo((from + to) / 2)
    expect(entrainmentAt(tl, second.startMs + GLIDE_MS).beatHz).toBe(to)
    expect(depthDimAt(tl, second.startMs + GLIDE_MS)).toBeGreaterThan(depthDimAt(tl, first.startMs))
  })
})

describe('overlay', () => {
  it('builds a beat-synced layer whose opacity is the frame alpha', () => {
    const l = overlayLayer('go deeper', 0.4, 'deepen', 'glass')
    expect(l.content).toEqual(['go deeper'])
    expect(l.style.opacity).toBe(0.4)
    expect(l.motion).toMatchObject({ type: STAGES.deepen.motion, syncToBeat: true })
    expect(l.font.upper).toBe(true)
    expect(overlayLayer('x', 1, 'wake', 'soft').style.blend).toBe('normal')
  })

  it('sizes the canvas to the video, capped at 1920 on the long edge', () => {
    expect(canvasSizeFor(null)).toEqual({ w: 1280, h: 720 })
    const v = { videoWidth: 2160, videoHeight: 3840 } as HTMLVideoElement
    expect(canvasSizeFor(v)).toEqual({ w: 1080, h: 1920 })
  })
})
