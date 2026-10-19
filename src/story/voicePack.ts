import type { Alignment, StoryBeat } from './storyBeats'

/**
 * Voice packs: pre-rendered voice files for a story's beats, produced offline
 * (tools/voice/elevenlabs.mjs, or downloaded by hand from the ElevenLabs site).
 *
 * Each beat's audio is named by its id — a hash of the spoken text — so
 * `b1a2b3c4d.mp3` (+ optional `b1a2b3c4d.json` character timestamps) attaches
 * to whichever beat says exactly that line. Editing one beat only changes
 * that beat's id; the rest of the pack still fits.
 */

export interface VoiceClip {
  buffer: AudioBuffer
  /** Character timestamps (ElevenLabs /with-timestamps), when available. */
  alignment: Alignment | null
  /** File the audio came from, for display. */
  name: string
}

export interface PackMeta {
  source: string
  model_id?: string
  voice_id?: string
  voice_name?: string
}

export interface VoiceScript {
  version: 1
  beats: { id: string; stage: string; text: string }[]
}

const ID_RE = /^b[0-9a-f]{8}$/

/** The lines to voice, de-duplicated by id, for the producer tool. */
export function voiceScript(beats: StoryBeat[]): VoiceScript {
  const seen = new Set<string>()
  const out: VoiceScript['beats'] = []
  for (const b of beats) {
    if (!b.text || seen.has(b.id)) continue
    seen.add(b.id)
    out.push({ id: b.id, stage: b.stage, text: b.text })
  }
  return { version: 1, beats: out }
}

/** Decode any browser-playable audio file (mp3, wav, m4a…). */
export async function decodeAudioFile(file: Blob): Promise<AudioBuffer> {
  const ctx = new OfflineAudioContext(1, 1, 44100)
  return ctx.decodeAudioData(await file.arrayBuffer())
}

function isAlignment(x: unknown): x is Alignment {
  const a = x as Alignment
  return !!a && Array.isArray(a.characters) && Array.isArray(a.character_start_times_seconds)
    && Array.isArray(a.character_end_times_seconds)
}

const baseName = (f: File) => f.name.replace(/^.*[\\/]/, '').replace(/\.[^.]+$/, '')

/** Read a pack folder (or any selection of its files) into clips keyed by beat id. */
export async function readPack(files: File[]): Promise<{ clips: Map<string, VoiceClip>; meta: PackMeta | null; skipped: string[] }> {
  const clips = new Map<string, VoiceClip>()
  const skipped: string[] = []
  let meta: PackMeta | null = null
  const alignments = new Map<string, Alignment>()

  for (const f of files) {
    const id = baseName(f)
    if (f.name.endsWith('.json')) {
      try {
        const data = JSON.parse(await f.text())
        if (id === 'pack') meta = data as PackMeta
        else if (ID_RE.test(id) && isAlignment(data.alignment)) alignments.set(id, data.alignment)
      } catch { skipped.push(f.name) }
    }
  }
  for (const f of files) {
    const id = baseName(f)
    if (f.name.endsWith('.json')) continue
    if (!ID_RE.test(id) || !/^audio\//.test(f.type || 'audio/')) { skipped.push(f.name); continue }
    try {
      clips.set(id, { buffer: await decodeAudioFile(f), alignment: alignments.get(id) ?? null, name: f.name })
    } catch { skipped.push(f.name) }
  }
  return { clips, meta, skipped }
}
