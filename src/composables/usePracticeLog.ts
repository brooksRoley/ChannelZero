import { ref, computed } from 'vue'

// Local-only log of completed hypnosis sessions. Like the journal, this never
// leaves the device — it lets check-in close the loop on "today's practice".

export type PracticeSession = 'zeromind' | 'audio' | 'spiral'

export interface PracticeRecord {
  session: PracticeSession
  completedAt: number
  durationMs: number
}

export interface PracticeRecommendation {
  session: PracticeSession
  reason: string
}

const STORAGE_KEY = 'cz-practice-log'
const MAX_RECORDS = 500

export const PRACTICE_LABELS: Record<PracticeSession, string> = {
  zeromind: 'Zeromind',
  audio: 'Audio Journey',
  spiral: 'Spiral',
}

function loadLog(): PracticeRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as PracticeRecord[]) : []
  } catch {
    return []
  }
}

const log = ref<PracticeRecord[]>(loadLog())

function logPractice(session: PracticeSession, durationMs: number) {
  log.value.push({ session, completedAt: Date.now(), durationMs })
  if (log.value.length > MAX_RECORDS) log.value.splice(0, log.value.length - MAX_RECORDS)
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(log.value))
  } catch { /* storage full or blocked — the session still happened */ }
}

const todayPractice = computed(() => {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  return log.value.filter((r) => r.completedAt >= start.getTime())
})

// Mood (latest journal mood today, if any) takes precedence over time of day.
// Moods come from JournalView's mood list.
export function recommendPractice(hour: number, mood: string | null): PracticeRecommendation {
  switch (mood) {
    case 'anxious':
    case 'heavy':
      return { session: 'zeromind', reason: `You noted feeling ${mood}. Slow binaural entrainment helps the body settle.` }
    case 'scattered':
      return { session: 'spiral', reason: 'You noted feeling scattered. The spiral gives your attention one point to rest on.' }
    case 'energized':
    case 'focused':
      return { session: 'audio', reason: `You noted feeling ${mood}. Adaptive audio follows that energy instead of fighting it.` }
  }
  if (hour >= 5 && hour < 12) return { session: 'spiral', reason: 'A short visual reset to open the day.' }
  if (hour >= 12 && hour < 18) return { session: 'audio', reason: 'A midday reset that adapts to how you move.' }
  return { session: 'zeromind', reason: 'Theta-range entrainment to wind the day down.' }
}

export function usePracticeLog() {
  return { log, todayPractice, logPractice }
}
