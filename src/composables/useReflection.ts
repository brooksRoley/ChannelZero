import { ref } from 'vue'
import type { MethodId } from '@/data/practiceMethods'

/**
 * Reflection feedback for practice prompts.
 *
 * Every answer is read on-device first (`readLocally`, a small lexicon), so
 * feedback is instant and works offline. When allowed, the text is also sent to
 * /api/practice/reflect, which asks the server's free LLM for a better read and
 * a one-line mirror. That endpoint is stateless: nothing is stored. If it is
 * rate-limited, unconfigured or offline, the local read stands.
 */

export type Moment = 'before' | 'during' | 'after'

export interface Reading {
  valence: number // -1 heavy .. 1 light
  energy: number // 0 still .. 1 charged
  tone: string
  reflection: string
  source: 'local' | 'llm'
}

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const LOCAL_ONLY_KEY = 'cz-reflect-local-only'

// ── On-device lexicon ─────────────────────────────────────────────

// word → [valence, energy]
const LEXICON: Record<string, [number, number]> = {
  calm: [0.7, 0.1], calmer: [0.7, 0.1], peaceful: [0.8, 0.1], still: [0.5, 0.05], quiet: [0.5, 0.1],
  relaxed: [0.7, 0.1], soft: [0.5, 0.15], heavy: [-0.1, 0.1], sinking: [0.3, 0.1], floating: [0.6, 0.2],
  warm: [0.6, 0.3], light: [0.6, 0.3], lighter: [0.6, 0.3], open: [0.5, 0.4], clear: [0.6, 0.4],
  safe: [0.7, 0.2], grounded: [0.6, 0.2], sleepy: [0.3, 0.05], tired: [-0.2, 0.1], drowsy: [0.2, 0.05],
  good: [0.5, 0.4], better: [0.5, 0.3], fine: [0.2, 0.3], okay: [0.1, 0.3], ok: [0.1, 0.3],
  happy: [0.8, 0.6], joy: [0.9, 0.6], grateful: [0.8, 0.3], hopeful: [0.6, 0.5], focused: [0.5, 0.6],
  tingling: [0.3, 0.5], buzzing: [0.1, 0.7], energized: [0.6, 0.8], alert: [0.3, 0.7],
  anxious: [-0.6, 0.8], nervous: [-0.5, 0.8], restless: [-0.4, 0.8], tense: [-0.5, 0.7], tight: [-0.4, 0.6],
  scattered: [-0.4, 0.7], busy: [-0.3, 0.7], racing: [-0.5, 0.9], distracted: [-0.3, 0.6], wired: [-0.2, 0.9],
  sad: [-0.7, 0.2], low: [-0.5, 0.2], numb: [-0.4, 0.1], empty: [-0.4, 0.1], lonely: [-0.6, 0.2],
  angry: [-0.7, 0.9], frustrated: [-0.6, 0.7], irritated: [-0.5, 0.7], stuck: [-0.5, 0.3], bored: [-0.2, 0.2],
  overwhelmed: [-0.7, 0.8], stressed: [-0.6, 0.8], afraid: [-0.7, 0.8], scared: [-0.7, 0.8], pain: [-0.5, 0.5],
}
const NEGATORS = new Set(['not', 'no', "don't", 'dont', "isn't", 'never', 'less'])
const UNSAFE = /\b(kill myself|suicid|end it all|hurt myself|self[- ]harm|want to die)\b/i

/** PURE: lexicon read of a short answer. */
export function readLocally(text: string, moment: Moment): Reading {
  if (UNSAFE.test(text)) {
    return {
      valence: -1, energy: 0.5, tone: 'unsafe', source: 'local',
      reflection: 'Thank you for saying that. Please pause here and reach out to someone you trust, or a local crisis line.',
    }
  }
  const words = text.toLowerCase().match(/[a-z']+/g) ?? []
  let v = 0, e = 0, n = 0
  words.forEach((w, i) => {
    const hit = LEXICON[w]
    if (!hit) return
    const negated = NEGATORS.has(words[i - 1] ?? '') || NEGATORS.has(words[i - 2] ?? '')
    v += negated ? -hit[0] * 0.6 : hit[0]
    e += hit[1]
    n++
  })
  const valence = n ? Math.max(-1, Math.min(1, v / n)) : 0
  const energy = n ? Math.max(0, Math.min(1, e / n)) : 0.4
  const tone = toneFor(valence, energy, n > 0)
  return { valence, energy, tone, reflection: mirrorFor(tone, moment), source: 'local' }
}

/** PURE: name a quadrant of valence × energy. */
export function toneFor(valence: number, energy: number, known = true): string {
  if (!known) return 'present'
  if (valence >= 0.2) return energy >= 0.55 ? 'bright' : 'settling'
  if (valence <= -0.2) return energy >= 0.55 ? 'restless' : 'heavy'
  return energy >= 0.55 ? 'stirred' : 'neutral'
}

const MIRRORS: Record<string, Record<Moment, string>> = {
  settling: {
    before: 'You’re arriving already a little settled. Let the session meet you there.',
    during: 'Something is softening. Let the next exhale be a little longer than the last.',
    after: 'You’re leaving softer than you came. Notice where in the body that lives.',
  },
  bright: {
    before: 'There’s energy here. Let the first minutes match it before slowing down.',
    during: 'Lively attention. Rest it on one sound and let the rest blur.',
    after: 'You came out bright. Carry one breath of this into whatever is next.',
  },
  restless: {
    before: 'Restless is a fine place to start. You don’t have to be calm to begin.',
    during: 'The mind is busy, and that’s allowed. Count three slow exhales and see what’s left.',
    after: 'Still some charge left. A shorter, slower session later might finish the job.',
  },
  heavy: {
    before: 'Heavy days count too. Go gently, and stop whenever you need to.',
    during: 'Let the heaviness be held by whatever is under you. You don’t have to lift it.',
    after: 'It was heavy today. Showing up for it is the practice.',
  },
  stirred: {
    before: 'A little stirred up. Give the first few breaths permission to be uneven.',
    during: 'Something is moving. Let it, and follow the breath ring for a moment.',
    after: 'Things moved. Notice whether they settled somewhere new.',
  },
  neutral: {
    before: 'A neutral start is a clean start.',
    during: 'Just noticing is enough. Stay with the sound.',
    after: 'Even subtle shifts count. Did anything move by a degree?',
  },
  present: {
    before: 'Noted. Begin whenever you’re ready.',
    during: 'Noted. Let the words go and return to the breath.',
    after: 'Noted. That’s yours to keep.',
  },
}

function mirrorFor(tone: string, moment: Moment): string {
  return (MIRRORS[tone] ?? MIRRORS.present)[moment]
}

// ── Composable ────────────────────────────────────────────────────

const localOnly = ref(readLocalOnly())

function readLocalOnly(): boolean {
  try { return localStorage.getItem(LOCAL_ONLY_KEY) === '1' } catch { return false }
}

function setLocalOnly(v: boolean) {
  localOnly.value = v
  try { localStorage.setItem(LOCAL_ONLY_KEY, v ? '1' : '0') } catch { /* fine */ }
}

export interface ReflectInput {
  method: MethodId
  moment: Moment
  prompt: string
  text: string
  before?: number
  after?: number
}

/**
 * Read an answer. Resolves immediately with the local read via `onLocal`,
 * then upgrades to the LLM read if it arrives within `timeoutMs`.
 */
async function reflect(input: ReflectInput, onLocal?: (r: Reading) => void, timeoutMs = 12000): Promise<Reading> {
  const local = readLocally(input.text, input.moment)
  onLocal?.(local)
  if (localOnly.value || local.tone === 'unsafe' || !input.text.trim()) return local

  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(`${API}/api/practice/reflect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...input, text: input.text.slice(0, 600), prompt: input.prompt.slice(0, 200) }),
      signal: ctrl.signal,
    })
    if (!res.ok) return local
    const data = await res.json()
    return { ...data, source: 'llm' } as Reading
  } catch {
    return local
  } finally {
    clearTimeout(timer)
  }
}

export function useReflection() {
  return { localOnly, setLocalOnly, reflect }
}
