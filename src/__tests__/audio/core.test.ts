import { describe, it, expect } from 'vitest'
import { earFrequencies, isochronicDepth, createBinauralPair, pinkNoiseBuffer } from '@/audio/core'

// Minimal fake AudioContext: enough graph surface for the primitives.
function fakeCtx() {
  const param = (v = 0) => ({
    value: v,
    setTargetAtTime(x: number) { this.value = x },
    cancelScheduledValues() {},
    setValueAtTime() {},
    linearRampToValueAtTime(x: number) { this.value = x },
  })
  const node = () => ({ connect() {}, disconnect() {} })
  return {
    currentTime: 0,
    sampleRate: 8000,
    createChannelMerger: () => node(),
    createOscillator: () => ({ ...node(), type: 'sine', frequency: param(), start() {}, stop() {} }),
    createBuffer: (ch: number, len: number) => {
      const data = Array.from({ length: ch }, () => new Float32Array(len))
      return { numberOfChannels: ch, length: len, getChannelData: (i: number) => data[i] }
    },
  } as unknown as BaseAudioContext
}

describe('audio core', () => {
  it('splits a carrier into ears around the beat', () => {
    expect(earFrequencies(200, 10)).toEqual({ leftHz: 195, rightHz: 205 })
  })

  it('engages the isochronic pulse only above 30 Hz', () => {
    expect(isochronicDepth(10)).toBe(0)
    expect(isochronicDepth(40)).toBeGreaterThan(0)
  })

  it('pair glides both ears to carrier ± beat/2, or each ear on its own', () => {
    const pair = createBinauralPair(fakeCtx(), { leftHz: 195, rightHz: 205 })
    pair.setBeat(6, 180)
    expect([pair.left.frequency.value, pair.right.frequency.value]).toEqual([177, 183])
    pair.setEars(250, 260)
    expect([pair.left.frequency.value, pair.right.frequency.value]).toEqual([250, 260])
  })

  it('pink noise is bounded and decorrelated across channels', () => {
    const buf = pinkNoiseBuffer(fakeCtx(), { seconds: 1, channels: 2, level: 0.04 })
    const [l, r] = [buf.getChannelData(0), buf.getChannelData(1)]
    expect(Math.max(...l.map(Math.abs))).toBeLessThan(0.5)
    expect(l.some((v, i) => v !== r[i])).toBe(true)
  })
})
