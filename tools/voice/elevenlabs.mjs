#!/usr/bin/env node
/* eslint-env node */
// Voice a /story script with ElevenLabs — producer-side only.
//
// The app never calls ElevenLabs: you run this locally with your own key,
// then load the resulting folder into /story ("Load voice pack").
//
//   export ELEVENLABS_API_KEY=...            (never commit it)
//   node tools/voice/elevenlabs.mjs --list-voices
//   node tools/voice/elevenlabs.mjs story-voice-script.json --audition <id>,<id>,<id>
//   node tools/voice/elevenlabs.mjs story-voice-script.json --voice <voice_id> --dry-run
//   node tools/voice/elevenlabs.mjs story-voice-script.json --voice <voice_id>
//
// Options:
//   --model <id>     default eleven_multilingual_v2 (eleven_flash_v2_5 costs ~half the credits)
//   --speed <x>      0.7–1.2, default 0.9 (slower suits trance pacing)
//   --stability <x>  0–1, default 0.7 (higher = calmer, more even delivery)
//   --context        send the neighbouring lines as previous_text / next_text so
//                    each beat flows from the last (ElevenLabs' docs don't say if
//                    this context is billed — compare credits before/after once)
//   --audition <ids> voice one short line per voice into <out>/_audition/ to pick
//                    a narrator (~150 credits per voice)
//   --out <dir>      default voice-packs/<script name>
//   --force          ignore the remaining-credit check
//
// Writes <id>.mp3 + <id>.json (character timestamps) per beat, and pack.json.
// Beats whose <id>.mp3 already exists are skipped, so editing a story only
// spends credits on the lines that changed. You can also drop in an mp3 made
// on the ElevenLabs site under the same <id>.mp3 name (it'll lack timestamps).
//
// Free plan: non-commercial use with attribution. /story credits
// "Voice: ElevenLabs" in the export when a pack is loaded.

import { readFile, writeFile, mkdir, access } from 'node:fs/promises'
import { basename, join } from 'node:path'

const API = 'https://api.elevenlabs.io/v1'
const args = process.argv.slice(2)
const flag = (name, fallback) => {
  const i = args.indexOf(`--${name}`)
  return i >= 0 ? args[i + 1] : fallback
}
const has = (name) => args.includes(`--${name}`)

const key = process.env.ELEVENLABS_API_KEY
if (!key) {
  console.error('Set ELEVENLABS_API_KEY in your environment first.')
  process.exit(1)
}
const headers = { 'xi-api-key': key, 'Content-Type': 'application/json' }

async function api(path, init = {}) {
  for (let attempt = 0; ; attempt++) {
    const res = await fetch(`${API}${path}`, { ...init, headers })
    if (res.status === 429 && attempt < 3) {
      console.warn('  rate limited, waiting 5 s…')
      await new Promise((r) => setTimeout(r, 5000))
      continue
    }
    if (!res.ok) throw new Error(`${res.status} ${path}: ${(await res.text()).slice(0, 300)}`)
    return res.json()
  }
}

if (has('list-voices')) {
  const { voices } = await api('/voices')
  for (const v of voices) {
    const l = v.labels ?? {}
    const tags = [l.gender, l.age, l.accent, l.description, l.use_case].filter(Boolean).join(', ')
    console.log(`${v.voice_id}  ${v.name.padEnd(22)} ${tags}`)
  }
  process.exit(0)
}

const scriptPath = args.find((a) => !a.startsWith('--') && a.endsWith('.json'))
const voiceId = flag('voice')
const audition = flag('audition')
if (!scriptPath || !(voiceId || audition)) {
  console.error('Usage: node tools/voice/elevenlabs.mjs <voice-script.json> --voice <voice_id> [--dry-run]')
  process.exit(1)
}

const model = flag('model', 'eleven_multilingual_v2')
const speed = Number(flag('speed', '0.9'))
const stability = Number(flag('stability', '0.7'))
const voiceSettings = { stability, similarity_boost: 0.75, style: 0, speed }

async function speak(voice, text, context = {}) {
  return api(`/text-to-speech/${voice}/with-timestamps?output_format=mp3_44100_128`, {
    method: 'POST',
    body: JSON.stringify({ text, model_id: model, voice_settings: voiceSettings, ...context }),
  })
}
const out = flag('out', join('voice-packs', basename(scriptPath, '.json')))
const script = JSON.parse(await readFile(scriptPath, 'utf8'))
if (script.version !== 1 || !Array.isArray(script.beats)) throw new Error('Not a /story voice script (version 1).')

await mkdir(out, { recursive: true })

if (audition) {
  // One representative line (the opening, cut at a sentence end) per voice.
  const opening = script.beats.map((b) => b.text).join(' ')
  const cut = opening.slice(0, 160)
  const line = cut.length < opening.length ? cut.slice(0, Math.max(cut.lastIndexOf('. ') + 1, 60)) : cut
  const ids = audition.split(',').map((v) => v.trim()).filter(Boolean)
  await mkdir(join(out, '_audition'), { recursive: true })
  console.log(`Auditioning ${ids.length} voice(s) on: "${line}" (~${line.length} credits each)`)
  for (const id of ids) {
    let name = id
    try { name = (await api(`/voices/${id}`)).name } catch { /* keep id */ }
    const res = await speak(id, line)
    const file = join(out, '_audition', `${name.replace(/[^\w-]+/g, '_')}.mp3`)
    await writeFile(file, Buffer.from(res.audio_base64, 'base64'))
    console.log(`  ${file}`)
  }
  process.exit(0)
}

const exists = (p) => access(p).then(() => true, () => false)
const todo = []
for (const b of script.beats) if (!(await exists(join(out, `${b.id}.mp3`)))) todo.push(b)

const chars = todo.reduce((n, b) => n + b.text.length, 0)
const perChar = /flash|turbo/.test(model) ? 0.5 : 1
const cost = Math.ceil(chars * perChar)
const sub = await api('/user/subscription')
const remaining = sub.character_limit - sub.character_count

console.log(`${script.beats.length} beats · ${todo.length} to voice · ${chars} chars ≈ ${cost} credits (${model})`)
console.log(`Plan: ${sub.tier} · ${remaining} of ${sub.character_limit} credits left this period`)
if (has('dry-run') || !todo.length) process.exit(0)
if (cost > remaining && !has('force')) {
  console.error('Not enough credits left. Shorten the story, use --model eleven_flash_v2_5, or wait for the reset.')
  process.exit(1)
}

for (const [i, b] of todo.entries()) {
  process.stdout.write(`[${i + 1}/${todo.length}] ${b.id} ${b.text.slice(0, 50)}… `)
  const at = script.beats.indexOf(b)
  const context = has('context')
    ? { previous_text: script.beats[at - 1]?.text, next_text: script.beats[at + 1]?.text }
    : {}
  const res = await speak(voiceId, b.text, context)
  await writeFile(join(out, `${b.id}.mp3`), Buffer.from(res.audio_base64, 'base64'))
  await writeFile(join(out, `${b.id}.json`), JSON.stringify({ text: b.text, alignment: res.alignment }))
  console.log('ok')
}

let voiceName
try { voiceName = (await api(`/voices/${voiceId}`)).name } catch { /* optional */ }
await writeFile(join(out, 'pack.json'), JSON.stringify({
  source: 'elevenlabs', model_id: model, voice_id: voiceId, voice_name: voiceName, voice_settings: voiceSettings, created: new Date().toISOString(),
}, null, 2))
console.log(`Done → ${out}  (load this folder in /story)`)
