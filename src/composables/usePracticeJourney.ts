import { ref, computed, watch } from 'vue'
import { usePracticeLog, type PracticeRecord } from './usePracticeLog'
import { METHODS, METHOD_ORDER, SESSION_TO_METHOD, type MethodId } from '@/data/practiceMethods'
import type { Reading } from './useReflection'

/**
 * The practice journey: before-check → session (with soft prompts) → after-check.
 *
 * Local-only, like the journal and practice log: entries never leave the device.
 * The "game" is deliberately quiet — no points or breakable streaks. It tracks
 * three things a person can actually feel: the days they showed up (a thread,
 * not a streak), how familiar each method has become, and their own
 * before → after shift.
 */

export interface Check {
  rating: number // 1–5 felt sense: 1 = tight/heavy, 5 = open/at ease
  text?: string
  reading?: Reading
}

export interface DuringNote {
  prompt: string
  text: string
  tone: string
  valence: number
  at: number
}

export interface PracticeEntry {
  id: string
  method: MethodId
  startedAt: number
  sessionEndedAt?: number
  before: Check
  during: DuringNote[]
  after?: Check
  finishedAt?: number
}

const ENTRIES_KEY = 'cz-practice-journey'
const PENDING_KEY = 'cz-practice-pending'
const MAX_ENTRIES = 300
const DAY = 86_400_000

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}
function save(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, JSON.stringify(value))
  } catch { /* storage blocked — the practice still happened */ }
}

const entries = ref<PracticeEntry[]>(load(ENTRIES_KEY, []))
const pending = ref<PracticeEntry | null>(load(PENDING_KEY, null))

watch(entries, (v) => save(ENTRIES_KEY, v), { deep: true })
watch(pending, (v) => save(PENDING_KEY, v), { deep: true })

// ── Pure derivations (unit-tested) ────────────────────────────────

function dayStart(t: number): number {
  const d = new Date(t)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/** Days practiced over the last `days` days, oldest first (today last). */
export function practiceThread(times: number[], now: number, days = 14): boolean[] {
  const today = dayStart(now)
  const hit = new Set(times.map(dayStart))
  return Array.from({ length: days }, (_, i) => hit.has(today - (days - 1 - i) * DAY))
}

export interface Familiarity {
  label: string
  count: number
  /** 0–1 progress toward the next label (1 at the top). */
  progress: number
}

const FAMILIARITY: [number, string][] = [
  [0, 'new to you'],
  [1, 'tried it'],
  [3, 'getting familiar'],
  [7, 'practiced'],
  [15, 'your own'],
]

export function familiarity(count: number): Familiarity {
  let i = 0
  while (i + 1 < FAMILIARITY.length && count >= FAMILIARITY[i + 1][0]) i++
  const [lo, label] = FAMILIARITY[i]
  const hi = FAMILIARITY[i + 1]?.[0]
  const progress = hi === undefined ? 1 : (count - lo) / (hi - lo)
  return { label, count, progress }
}

/** Mean after − before rating over finished entries (null if none). */
export function averageShift(list: PracticeEntry[]): number | null {
  const done = list.filter((e) => e.after)
  if (!done.length) return null
  return done.reduce((s, e) => s + (e.after!.rating - e.before.rating), 0) / done.length
}

/**
 * Plain observations about the person's own practice — the feedback the game
 * gives instead of scores. Newest-first entries in, up to three lines out.
 */
export function noticings(list: PracticeEntry[], thread: boolean[]): string[] {
  const out: string[] = []
  const done = list.filter((e) => e.after)

  const last3 = done.slice(0, 3)
  if (last3.length === 3 && last3.every((e) => e.after!.rating > e.before.rating)) {
    out.push('Your last three sessions all ended lighter than they began.')
  }

  const week = thread.slice(-7).filter(Boolean).length
  if (week >= 3) out.push(`You’ve come back on ${week} of the last 7 days.`)
  else if (thread.slice(-2).every((d) => !d) && thread.some(Boolean)) {
    out.push('It’s been a couple of days. One short session is enough to pick the thread back up.')
  }

  const byMethod = METHOD_ORDER
    .map((m) => ({ m, shift: averageShift(done.filter((e) => e.method === m)), n: done.filter((e) => e.method === m).length }))
    .filter((x) => x.shift !== null && x.n >= 2)
    .sort((a, b) => b.shift! - a.shift!)
  if (byMethod.length && byMethod[0].shift! > 0) {
    out.push(`${METHODS[byMethod[0].m].name} shifts you most so far (${signed(byMethod[0].shift!)} on average).`)
  }

  const tones = done.slice(0, 5).map((e) => e.after?.reading?.tone).filter(Boolean)
  if (tones.length >= 3 && tones.every((t) => t === tones[0])) {
    out.push(`You’ve often come out “${tones[0]}” lately.`)
  }
  return out.slice(0, 3)
}

export function signed(n: number): string {
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}`
}

// ── Composable ────────────────────────────────────────────────────

const { log } = usePracticeLog()

// The tools log completions to the practice log; mark the pending session ended
// when its tool reports in (zeromind / spiral / audio).
watch(
  () => log.value.length,
  () => {
    const last: PracticeRecord | undefined = log.value[log.value.length - 1]
    const p = pending.value
    if (!last || !p || p.sessionEndedAt) return
    if (SESSION_TO_METHOD[last.session] === p.method && last.completedAt >= p.startedAt) {
      p.sessionEndedAt = last.completedAt
    }
  },
)

function begin(method: MethodId, before: Check): string {
  pending.value = {
    id: `p-${Date.now().toString(36)}`,
    method,
    startedAt: Date.now(),
    before,
    during: [],
  }
  return METHODS[method].route
}

function addDuring(note: Omit<DuringNote, 'at'>) {
  pending.value?.during.push({ ...note, at: Date.now() })
}

/** For tools that don't report completion (studio, trance): the person says so. */
function markEnded() {
  if (pending.value && !pending.value.sessionEndedAt) pending.value.sessionEndedAt = Date.now()
}

function finish(after: Check): PracticeEntry | null {
  const p = pending.value
  if (!p) return null
  const done: PracticeEntry = { ...p, after, finishedAt: Date.now(), sessionEndedAt: p.sessionEndedAt ?? Date.now() }
  entries.value.unshift(done)
  if (entries.value.length > MAX_ENTRIES) entries.value.length = MAX_ENTRIES
  pending.value = null
  return done
}

function abandon() {
  pending.value = null
}

const thread = computed(() =>
  practiceThread(
    [...log.value.map((r) => r.completedAt), ...entries.value.map((e) => e.finishedAt ?? e.startedAt)],
    Date.now(),
  ),
)

const familiarityByMethod = computed(() => {
  const counts = Object.fromEntries(METHOD_ORDER.map((m) => [m, 0])) as Record<MethodId, number>
  for (const r of log.value) {
    const m = SESSION_TO_METHOD[r.session]
    if (m) counts[m]++
  }
  // Studio and trance aren't in the practice log; count their finished entries.
  for (const e of entries.value) if (e.method === 'studio' || e.method === 'trance') counts[e.method]++
  return Object.fromEntries(METHOD_ORDER.map((m) => [m, familiarity(counts[m])])) as Record<MethodId, Familiarity>
})

const overallShift = computed(() => averageShift(entries.value))
const observations = computed(() => noticings(entries.value, thread.value))

export function usePracticeJourney() {
  return {
    entries,
    pending,
    thread,
    familiarityByMethod,
    overallShift,
    observations,
    begin,
    addDuring,
    markEnded,
    finish,
    abandon,
  }
}
