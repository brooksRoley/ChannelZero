import { describe, it, expect } from 'vitest'
import {
  parseStory, buildTimeline, frameAt, entrainmentAt, depthDimAt, beatIndexAt,
  GLIDE_MS, STAGES,
} from '@/story/storyBeats'
import { chunkPhrases, splitWords } from '@/story/phrases'
import { BANDS } from '@/composables/useStudioBinaural'
import { captionLayer, canvasSizeFor } from '@/story/useStoryPlayer'
import { extractKeys, textId, type Alignment } from '@/story/storyBeats'
import { STAGE_EFFECTS, maxFlashesPerSecond } from '@/story/effects'
import { voiceScript } from '@/story/voicePack'
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
    expect(beats.map(({ stage, text, pauseMs }) => ({ stage, text, pauseMs }))).toEqual([
      { stage: 'induce', text: 'One line.', pauseMs: undefined },
      { stage: 'induce', text: 'Two lines.', pauseMs: undefined },
      { stage: 'deepen', text: 'Down.', pauseMs: undefined },
      { stage: 'deepen', text: '', pauseMs: 2500 },
      { stage: 'wake', text: 'Up.', pauseMs: undefined },
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
  it('builds a bottom subtitle layer whose opacity follows the frame alpha', () => {
    const l = captionLayer('go deeper', 0.5)
    expect(l.content).toEqual(['go deeper'])
    expect(l.pos.anchor).toBe('bc')
    expect(l.style.opacity).toBeCloseTo(0.425)
  })

  it('sizes the canvas to the video, capped at 1920 on the long edge', () => {
    expect(canvasSizeFor(null)).toEqual({ w: 1280, h: 720 })
    const v = { videoWidth: 2160, videoHeight: 3840 } as HTMLVideoElement
    expect(canvasSizeFor(v)).toEqual({ w: 1080, h: 1920 })
  })
})

describe('key phrases', () => {
  it('strips *key* markup and records offsets into the spoken text', () => {
    const { text, keys } = extractKeys('Go *down* now, *flash:let go* fully.')
    expect(text).toBe('Go down now, let go fully.')
    expect(keys).toEqual([
      { text: 'down', effect: undefined, charStart: 3, charEnd: 7 },
      { text: 'let go', effect: 'flash', charStart: 13, charEnd: 19 },
    ])
    expect(text.slice(keys[1].charStart, keys[1].charEnd)).toBe('let go')
  })

  it('gives each beat an id from its spoken text only', () => {
    const [a] = parseStory('[induce]\nSink *down*.')
    const [b] = parseStory('[deepen]\nSink down.')
    expect(a.id).toBe(b.id)
    expect(a.id).toMatch(/^b[0-9a-f]{8}$/)
    expect(textId('Sink down!')).not.toBe(a.id)
  })

  it('rotates effects through the stage set unless one is named', () => {
    const tl = buildTimeline(parseStory('[induce]\n*a* *b* *c* *slam:d* *e*'))
    expect(tl.keys.map((k) => k.effect)).toEqual([...STAGE_EFFECTS.induce, 'slam', STAGE_EFFECTS.induce[1]])
  })

  it('times keys from character timestamps when the alignment matches', () => {
    const [beat] = parseStory('[induce]\nNow *let go* please.')
    const chars = [...beat.text]
    const al: Alignment = {
      characters: chars,
      character_start_times_seconds: chars.map((_, i) => i * 0.1),
      character_end_times_seconds: chars.map((_, i) => i * 0.1 + 0.1),
    }
    const tl = buildTimeline([beat], { leadInMs: 0, voiceMs: [5000], alignments: [al] })
    const k = tl.keys[0]
    expect(tl.beats[0].aligned).toBe(true)
    expect(k.spokenStartMs).toBeCloseTo(400) // 'l' is char 4
    expect(k.spokenEndMs).toBeCloseTo(1000) // 'o' (char 9) ends at 1.0 s
    // A mismatched alignment (story edited after voicing) falls back to estimates.
    const off = buildTimeline([beat], { leadInMs: 0, voiceMs: [5000], alignments: [{ ...al, characters: chars.slice(1) }] })
    expect(off.beats[0].aligned).toBe(false)
  })
})

describe('subliminals', () => {
  it('parses pools and switches them off', () => {
    const beats = parseStory('[subliminal calm, safe]\nOne.\n\n[subliminal off]\nTwo.')
    expect(beats.map((b) => b.subliminal)).toEqual([['calm', 'safe'], []])
  })

  it('schedules deterministic flashes only inside beats with a pool', () => {
    const story = '[induce]\nA quiet start with nothing flashing at all here.\n\n[subliminal calm]\n[deepen]\n' + 'Slow words drift by. '.repeat(10)
    const a = buildTimeline(parseStory(story))
    const b = buildTimeline(parseStory(story))
    expect(a.subliminals.length).toBeGreaterThan(2)
    expect(a.subliminals).toEqual(b.subliminals)
    expect(a.subliminals.every((s) => s.atMs >= a.beats[1].startMs && s.text === 'calm')).toBe(true)
  })
})

describe('photosensitivity', () => {
  it('downgrades a flash whose strobe would overlap another', () => {
    const tl = buildTimeline(parseStory('[induce]\n*flash:one* *flash:two* *flash:three*'))
    expect(tl.keys[0].effect).toBe('flash')
    expect(tl.keys.filter((k) => k.effect === 'flash').length).toBeLessThan(3)
  })

  it('keeps every starter story and a flash-heavy story under 3 flashes/s', () => {
    const heavy = '[subliminal a, b, c]\n' + Array.from({ length: 12 }, () => '*flash:now* and *flash:now*').join('\n\n')
    for (const src of [...STORY_SAMPLES.map((s) => s.text), heavy]) {
      const tl = buildTimeline(parseStory(src), { wpm: 220 })
      expect(maxFlashesPerSecond(tl.keys, tl.subliminals)).toBeLessThan(3)
    }
  })

  it('counts strobe and subliminal onsets in a sliding second', () => {
    const subs = [0, 300, 600, 900].map((atMs, i) => ({ text: 'x', atMs, seed: i }))
    expect(maxFlashesPerSecond([], subs)).toBe(4)
  })
})

describe('voice script', () => {
  it('lists each spoken line once, skipping pauses', () => {
    const vs = voiceScript(parseStory('Same line.\n\n[pause 2]\n\nSame line.\n\nOther.'))
    expect(vs.version).toBe(1)
    expect(vs.beats.map((b) => b.text)).toEqual(['Same line.', 'Other.'])
  })
})
