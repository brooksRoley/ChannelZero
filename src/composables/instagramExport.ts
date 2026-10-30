/**
 * Instagram data export → activity per day, read on the device.
 *
 * Instagram's API only serves Business and Creator accounts, so a personal
 * account's own activity comes from its data export (Accounts Center →
 * Download your information, JSON). Nothing here is uploaded.
 *
 * Least data: for each like, comment, save, post and story we keep only
 * *when* it happened, as a count per local day and per hour. No usernames,
 * links, captions or comment text survive the parse.
 *
 * Export field names have changed between versions, so records are found by
 * shape (the file's list of objects) and each record's time by any
 * `*timestamp` field inside it. The file report says what was read, so a
 * format change shows up as "0 dated" instead of silently missing numbers.
 */

export type ActivityKind = 'like' | 'comment' | 'save' | 'post' | 'story'
export const KINDS: ActivityKind[] = ['like', 'comment', 'save', 'post', 'story']

export interface ExportFile { path: string; text: string }
export interface FileReport { path: string; kind: ActivityKind; records: number; dated: number }
export type ActivityDay = { date: string } & Record<ActivityKind, number>
export interface InstagramActivity {
  days: ActivityDay[]        // newest first, only days with activity
  hours: number[]            // 24 buckets, local time, all kinds
  files: FileReport[]
  skipped: number            // JSON files that aren't activity (settings, ads …)
  htmlOnly: boolean          // an HTML-format export: nothing to parse
  importedAt: string
}

export const KEEP_DAYS = 400

// First match wins: liked_comments.json is a like, not a comment.
const KIND_BY_PATH: [RegExp, ActivityKind][] = [
  [/(^|\/)likes\/liked_(posts|comments)\.json$/, 'like'],
  [/(^|\/)comments\/[^/]*comments[^/]*\.json$/, 'comment'],
  [/(^|\/)saved\/saved_posts\.json$/, 'save'],
  [/(^|\/)(content|media)\/posts_\d+\.json$/, 'post'],
  [/(^|\/)(content|media)\/stories\.json$/, 'story'],
]

export function kindOf(path: string): ActivityKind | null {
  const p = path.replace(/\\/g, '/')
  for (const [re, kind] of KIND_BY_PATH) if (re.test(p)) return kind
  return null
}

/** The file's list of records: the top-level array, or the first array of objects under it. */
export function recordsOf(json: unknown): unknown[] {
  if (Array.isArray(json)) return json
  if (json && typeof json === 'object') {
    for (const v of Object.values(json as Record<string, unknown>)) {
      if (Array.isArray(v) && v.some((x) => x && typeof x === 'object')) return v
    }
  }
  return []
}

/** Seconds since the epoch from the first *timestamp field in a record, or null. */
export function timestampOf(record: unknown, depth = 0): number | null {
  if (!record || typeof record !== 'object' || depth > 6) return null
  const entries = Array.isArray(record) ? record.map((v) => ['', v] as const) : Object.entries(record)
  for (const [k, v] of entries) {
    if (/timestamp/i.test(k) && typeof v === 'number') {
      const s = v > 1e12 ? v / 1000 : v // some fields are milliseconds
      if (s > 1e9 && s < 1e11) return s
    }
  }
  for (const [, v] of entries) {
    const t = timestampOf(v, depth + 1)
    if (t !== null) return t
  }
  return null
}

function localDate(seconds: number): { date: string; hour: number } {
  const d = new Date(seconds * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return { date: `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`, hour: d.getHours() }
}

export function parseExport(files: ExportFile[], now: Date = new Date()): InstagramActivity {
  const byDay = new Map<string, ActivityDay>()
  const hours = new Array(24).fill(0)
  const reports: FileReport[] = []
  let skipped = 0
  const cutoff = now.getTime() / 1000 - KEEP_DAYS * 86400

  for (const f of files) {
    if (!f.path.toLowerCase().endsWith('.json')) continue
    const kind = kindOf(f.path)
    if (!kind) { skipped++; continue }
    let json: unknown
    try { json = JSON.parse(f.text) } catch { reports.push({ path: f.path, kind, records: 0, dated: 0 }); continue }
    const records = recordsOf(json)
    let dated = 0
    for (const r of records) {
      const t = timestampOf(r)
      if (t === null) continue
      dated++
      if (t < cutoff) continue
      const { date, hour } = localDate(t)
      const day = byDay.get(date) ?? { date, like: 0, comment: 0, save: 0, post: 0, story: 0 }
      day[kind]++
      byDay.set(date, day)
      hours[hour]++
    }
    reports.push({ path: f.path, kind, records: records.length, dated })
  }

  const htmlOnly = !files.some((f) => f.path.toLowerCase().endsWith('.json'))
    && files.some((f) => f.path.toLowerCase().endsWith('.html'))
  return {
    days: [...byDay.values()].sort((a, b) => (a.date < b.date ? 1 : -1)),
    hours,
    files: reports,
    skipped,
    htmlOnly,
    importedAt: now.toISOString(),
  }
}

/** Totals per kind over the last `n` days of the parsed activity. */
export function totals(activity: InstagramActivity, n: number, now: Date = new Date()): Record<ActivityKind, number> {
  const since = localDate(now.getTime() / 1000 - n * 86400).date
  const out = { like: 0, comment: 0, save: 0, post: 0, story: 0 }
  for (const d of activity.days) if (d.date > since) for (const k of KINDS) out[k] += d[k]
  return out
}

// ── On-device storage (this browser only) ───────────────────────────────────

const STORE_KEY = 'cz-instagram-activity'

export function loadActivity(): InstagramActivity | null {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    return raw ? (JSON.parse(raw) as InstagramActivity) : null
  } catch { return null }
}

export function saveActivity(a: InstagramActivity): void {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(a)) } catch { /* private mode: shown, not kept */ }
}

export function clearActivity(): void {
  try { localStorage.removeItem(STORE_KEY) } catch { /* nothing stored */ }
}
