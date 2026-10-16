import { useAuthStore } from './useAuthStore'

// ── Types ──────────────────────────────────────────────────────────

export interface StreakData {
  streak: number
  today_active: boolean
  last_7_days: { date: string; active: boolean }[]
}

export type PublicRoute = 'zeromind' | 'spiral' | 'trance'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const ANON_KEY = 'channelzero-anon-id'

/** Random per-browser id for anonymous repeat-visit counting; never tied to an account. */
function anonId(): string {
  try {
    let id = localStorage.getItem(ANON_KEY)
    if (!id) {
      id = crypto.randomUUID()
      localStorage.setItem(ANON_KEY, id)
    }
    return id
  } catch {
    return 'anon-' + Math.random().toString(36).slice(2, 12)
  }
}

/** Fire-and-forget anonymous event for open routes (experiment E3). Never throws. */
export function logPublicEvent(
  event: 'public_visit' | 'public_session_completed',
  route: PublicRoute,
  durationMs?: number,
) {
  try {
    fetch(`${API}/api/analytics/public-event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      keepalive: true,
      body: JSON.stringify({
        event,
        route,
        anon_id: anonId(),
        ...(durationMs != null ? { duration_ms: Math.round(durationMs) } : {}),
      }),
    }).catch(() => { /* analytics must never break the experience */ })
  } catch { /* ignore */ }
}

// ── Composable ─────────────────────────────────────────────────────

/**
 * Lightweight wrapper around the analytics funnel endpoints.
 *
 * `logEvent` is fire-and-forget: it never throws, never blocks the UI, and
 * is a no-op when the user isn't authenticated (so public routes like
 * /zeromind don't trigger a 401 → forced logout).
 */
export function useAnalytics() {
  const { apiFetch, isAuthenticated } = useAuthStore()

  function logEvent(event: string, metadata: Record<string, unknown> = {}) {
    if (!isAuthenticated.value) return
    apiFetch('/api/analytics/event', {
      method: 'POST',
      body: JSON.stringify({ event, metadata }),
    }).catch(() => { /* analytics must never break the experience */ })
  }

  async function fetchStreak(): Promise<StreakData | null> {
    if (!isAuthenticated.value) return null
    try {
      return await apiFetch<StreakData>('/api/analytics/streak')
    } catch {
      return null
    }
  }

  return { logEvent, fetchStreak }
}
