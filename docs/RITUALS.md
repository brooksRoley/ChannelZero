# Rituals: habits and priorities, evidenced by your connectors

Design, 2026-10-30; updated the same day after Strava was retired (#117) and
movement moved to Apple Health (#118). Only the movement ingest is built.
Build order and open questions are at the end.

## Why

Connectors today are mirrors that never move. Each one takes a snapshot at
connect time (GitHub: repos; Calendar: a
window of events), distills it once into `vibe_vectors.<provider>_data`, and
writes a narrative about it. Nothing about the user's *days* ever reaches the
app, so the routine layer (priority #3 in Creative Direction) and the
connectors (priority #5) never meet.

Rituals joins them. The user says what matters (a few habits, today's
priorities), and the connectors they already granted become **evidence**:
"moved" is checked by an Apple Health workout, "built" by commits, "protected the
morning" by an empty calendar until noon. The user still sees things before
the app does; the app just stops making them tick boxes.

This is Brooks's own ask: daily habits (move, build, reach out, practice,
sleep) and priorities, integrated into the connector tools. It's designed as
a feature for every user, and Brooks is user one.

## Principles

- **Declared, not inferred.** The user names the habits and priorities. The
  app never guesses a goal from data ("you seem to want to run more").
- **Evidence, not a score.** A habit is evidenced or not today. No
  percentages, no streak to lose, no week-over-week comparison, no ranking.
- **Local-first, like the journal.** Habits and priorities live on the device
  (`useRitualStore`, localStorage), next to the journal and the intention.
  The server only returns the user's own day-level facts. The one thing it
  stores is movement, because an iOS Shortcut can only post to a server.
- **Least data.** Day-level rows only: movement is a workout's start, end and
  type, never heart rate, distance or location (routes start at home). GitHub gives a date, a commit count and the repo name. Calendar gives
  a date and busy/free minutes, plus titles only where the user tagged a priority.
- **Honest when stale.** Every connector says when it last synced, and what
  failed in plain words ("Nothing from the Shortcut since Tuesday").
  Never a pulse that spins forever.
- **Overridable by hand, always.** Evidence can check a box; the user can
  check or uncheck any box. A walk without a watch still counts.

## What the user declares (on the device)

```ts
// src/composables/useRitualStore.ts (localStorage, like useJournalStore)
type Habit = {
  id: string
  label: string            // "Move", "Build", "Reach out", "Practice", "Sleep"
  evidence?: EvidenceRule  // optional: which connector rows count
}
type EvidenceRule =
  | { provider: 'movement'; minMinutes?: number; types?: string[] } // "Running", "Strength Training"...
  | { provider: 'github'; repos?: string[] }                         // any repo, or these
  | { provider: 'gcal'; freeBefore?: string }                        // "12:00" = a protected morning
type Priority = {
  date: string             // YYYY-MM-DD; at most three per day
  text: string             // "Send the Nova Credit application"
  tags?: string[]          // words that link evidence: "BballTactics", "Hardwood"
  done?: boolean           // by hand only: a priority is never auto-completed
}
```

- **Habits:** at most five, edited in a small "Rituals" section of Check-in.
- **Priorities:** set in Check-in beside the intention ("Today's three"). They
  are never auto-completed: evidence can say a priority *got time* ("6 commits
  to BballTactics"), but only the user says it's done.

## What the connectors return (the day ledger)

One new read endpoint per connector, all with the same shape:

```
GET /api/<provider>/days?since=YYYY-MM-DD   (max 14 days back)
→ [{ date, provider, kind, minutes?, count?, label? }]
```

| Provider | kind | Fields | Source call |
|---|---|---|---|
| Movement (Apple Health) | `move` | minutes, label = workout type | `GET /api/movement/days` (built, #118; stored, posted by the user's Shortcut) |
| GitHub | `build` | count = commits, label = repo | `/users/{login}/events` (PushEvent), newest 100 |
| Google Calendar | `time` | minutes busy, minutes free before the user's cutoff; label = event title only when it matches a priority tag | `/calendars/primary/events?timeMin=` |

- GitHub and Calendar are fetched live on request, with a token refresh when
  needed (`oauth_base.refresh_if_needed`, #117). **Not stored**: the ledger
  is a view of the provider, so there's no new table and no new personal data
  at rest. Movement is the exception (see Principles). A short in-memory cache (10 minutes) keeps reloads cheap.
- The client matches ledger rows to habits and priority tags. The server never
  sees the habit list or the priorities.
- Other connectors (Spotify, YouTube, Reddit) give no day-level habit signal
  worth having yet; they stay as they are.

## Where it shows

- **Morning, Check-in:** today's three priorities, and the habits with any
  evidence already in ("Moved: a 40-minute run at 7:10").
- **Evening, Journal:** one line of what the day held, before the reflection
  prompt: "Today held a run, 6 commits to BballTactics (Hardwood), and a clear
  morning." Specific or silent: no line when nothing came in.
- **Home:** the existing day streak is unchanged. Rituals add no streak of their own.
- **Psychoanalysis / Oracle:** not by default. If the user opts in, the
  oracle may read *which habits had evidence on how many days*. It never reads
  priorities' text and never gets raw activity. Movement never reaches it at
  all (tests/test_movement.py).

## Connector state (2026-10-30)

- **Strava: retired** (#117). Its API now needs a paid subscription and its
  policy (§5.3) forbids any AI use of its data. Connect, sync and narratives
  answer 410. Stored `strava_data` is still in production, pending Brooks's
  yes to delete it. Brooks must remove `STRAVA_ACCESS_TOKEN` /
  `STRAVA_REFRESH_TOKEN` from `.env` by hand; no code uses them.
- **Token refresh: built** (#117). `oauth_base.refresh_if_needed` stores the
  rotated refresh token and answers 409 `reauth_required`, never 401.
- **Movement: built** (#118). An Apple Health Shortcut posts workouts
  (docs/APPLE_HEALTH_SHORTCUT.md).
- **Calendar honesty: still to do.** Map provider errors to plain states
  (`reauth_required`, 429 → retry later), store the granted scope, and add
  `synced_at` so the card can say how old a snapshot is.

## Build order

1. **Connector honesty** on Calendar. Tests use mocked httpx: refresh
   rotation, 401, 429, scope denied.
2. **Day ledger** for GitHub and Calendar: `/days` endpoints + tests that
   assert no untagged event titles leave the server. (Movement's is built.)
3. **`useRitualStore` + Check-in:** habits (≤5) and today's three priorities,
   with evidence matched on the device.
4. **The evening line** in Journal.
5. **Oracle opt-in**, last, and only if it earns its place.

## Tests

- The ledger never returns fields outside `{date, provider, kind, minutes,
  count, label}`, and never a heart rate, distance or location.
- Calendar labels appear only for events matching a priority tag.
- Matching is pure and client-side: a fixture ledger + habits → evidenced set.
- A priority is never marked done by evidence.
- A stale or failed connector renders its plain-words state, never a spinner.

## Open questions for Brooks

1. **Job tool link: none, as designed.** The job tool and ChannelZero stay
   separate: priorities are typed in Check-in. (A later option: a "paste
   today's moves" helper that reads `agent.py status` locally. It would never
   be a sync.)
2. **Local-only vs. synced rituals.** Local-only matches the journal. The cost
   is no cross-device rituals. Sync would need a server table.
3. **Which habits are yours?** A starting set: Move (a workout ≥ 20 min), Build
   (GitHub, any repo), Reach out (by hand), Practice (by hand), Sleep (by hand).
