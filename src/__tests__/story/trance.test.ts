import { describe, it, expect } from 'vitest'
import { parseStory, buildTimeline, GLIDE_MS } from '@/story/storyBeats'
import { STORY_SAMPLES } from '@/data/storySamples'
import {
  buildAutomation, autoValueAt, resolveBeatSound, heartbeatTimes, cueEvents, stemGain, defaultMix, padCutoffHz,
  STAGE_MIX, HEART_BPM, COMFORT_ENTRAINMENT_MAX, MIX_PRESETS, STEM_IDS,
} from '@/story/trance'
import { cleanStyle } from '@/story/beatStyle'

const line = 'Let every breath carry you a little further down, softer and slower than before.'
const arc = `[induce]\n${line}\n\n[deepen]\n${line}\n\n[emerge]\n${line}\n\n[final]\n${line}\n\n[wake]\n${line}`
const tl = buildTimeline(parseStory(arc))

describe('stage automation', () => {
  const auto = buildAutomation(tl, resolveBeatSound([], tl.beats.length))

  it('glides each bed into the stage level over GLIDE_MS from the beat start', () => {
    const deepen = tl.beats[1]
    expect(autoValueAt(auto.waves, deepen.startMs)).toBeCloseTo(STAGE_MIX.induce.waves)
    expect(autoValueAt(auto.waves, deepen.startMs + GLIDE_MS)).toBeCloseTo(STAGE_MIX.deepen.waves)
    expect(autoValueAt(auto.waves, deepen.startMs + GLIDE_MS / 2)).toBeCloseTo((STAGE_MIX.induce.waves + STAGE_MIX.deepen.waves) / 2)
  })

  it('keeps the voice flat', () => {
    expect(auto.voice).toEqual([{ tMs: 0, v: 1 }])
  })

  it('keeps every curve in time order, even with beats shorter than the glide', () => {
    const short = buildTimeline(parseStory('[induce]\nA.\n[pause 0.5]\n[deepen]\nB.\n[pause 1]\n[final]\nC.'))
    const a = buildAutomation(short, resolveBeatSound([], short.beats.length))
    for (const id of STEM_IDS) {
      for (let i = 1; i < a[id].length; i++) expect(a[id][i].tMs).toBeGreaterThanOrEqual(a[id][i - 1].tMs)
    }
  })

  it('layers a beat balance on top of the stage arc, carried forward', () => {
    const sound = resolveBeatSound([undefined, { heart: 0 }], tl.beats.length)
    expect(sound.map((s) => s.heart)).toEqual([1, 0, 0, 0, 0])
    const a = buildAutomation(tl, sound)
    expect(autoValueAt(a.heart, tl.beats[3].startMs + GLIDE_MS)).toBe(0)
    expect(autoValueAt(a.music, tl.beats[3].startMs + GLIDE_MS)).toBeCloseTo(STAGE_MIX.final.music)
  })

  it('treats an emptied beat sound as no style', () => {
    expect(cleanStyle({ sound: {} })).toBeUndefined()
  })
})

describe('heartbeat (pacing and leading)', () => {
  it('starts near resting pace and slows into the final stage', () => {
    const t = heartbeatTimes(tl)
    const gapAt = (ms: number) => {
      const i = t.findIndex((x) => x >= ms)
      return t[i + 1] - t[i]
    }
    expect(gapAt(tl.beats[0].startMs)).toBeCloseTo(60000 / HEART_BPM.induce, 0)
    expect(gapAt(tl.beats[3].startMs + GLIDE_MS)).toBeGreaterThan(gapAt(tl.beats[0].startMs))
  })

  it('leaves the opening and the tail silent', () => {
    const t = heartbeatTimes(tl)
    expect(t[0]).toBe(tl.beats[0].startMs)
    expect(t[t.length - 1]).toBeLessThan(tl.durationMs - tl.tailMs)
  })
})

describe('cues (the anchor and the lift)', () => {
  it('strikes a bowl on the first beat and every deepening, and rises into emerge and wake', () => {
    expect(cueEvents(tl).map((c) => `${c.kind}@${tl.beats.findIndex((b) => b.startMs === c.atMs)}`))
      .toEqual(['bowl@0', 'bowl@1', 'rise@2', 'bowl@3', 'rise@4'])
  })

  it('does not repeat within a stage', () => {
    const sample = buildTimeline(parseStory(STORY_SAMPLES[0].text))
    const cues = cueEvents(sample)
    const changes = sample.beats.filter((b, i) => i === 0 || b.stage !== sample.beats[i - 1].stage).length
    expect(cues.length).toBe(changes)
  })
})

describe('mixer rules', () => {
  it('mutes, solos and caps entrainment in comfort mode', () => {
    const mix = defaultMix()
    mix.faders.binaural = 0.9
    expect(stemGain(mix, 'binaural', true)).toBe(COMFORT_ENTRAINMENT_MAX)
    expect(stemGain(mix, 'binaural', false)).toBe(0.9)
    mix.muted.music = true
    expect(stemGain(mix, 'music', false)).toBe(0)
    mix.solo = 'voice'
    expect(stemGain(mix, 'waves', false)).toBe(0)
    expect(stemGain(mix, 'voice', false)).toBe(1)
  })

  it('maps warmth onto a dark-to-open pad cutoff', () => {
    expect(padCutoffHz(0)).toBeCloseTo(700)
    expect(padCutoffHz(1)).toBeCloseTo(2400)
    expect(padCutoffHz(0.5)).toBeGreaterThan(700)
  })

  it('ships presets that respect comfort mode', () => {
    for (const p of MIX_PRESETS) {
      expect(p.design.comfort).toBe(true)
      expect(p.faders.binaural).toBeLessThanOrEqual(COMFORT_ENTRAINMENT_MAX)
    }
  })
})
