# ChannelZero — Claude Code Guide

## Mission
**Community rather than convenience.** ChannelZero reimagines popular apps and connection
capabilities: where mainstream apps optimize for frictionless consumption, ChannelZero turns
the same connections (Spotify, GitHub, YouTube, calendar…) into mirrors for self-knowledge,
and treats connection between people as something earned through understanding — not a swipe.
Product copy, feature framing, and routine-agent proposals should reflect this lens.

## Creative Direction (read first — overrides older "matching engine" framing)
ChannelZero is a suite of **immersive self-expression and hypnosis experiences** with an
embedded psychoanalysis layer. The product is, in priority order:
1. **Self-expression** — journal (text/draw/audio), glass video studio, speed reader, check-in.
   The journal is **local-only by design** (localStorage via `useJournalStore`); entries never
   leave the device. The server-side journal API was removed 2026-10-14 — don't re-add sync.
2. **Hypnosis / entrainment** — binaural & trance audio, spiral, star-tunnel breath journey,
   generative visuals (Tone.js + Web Audio + Canvas).
3. **Routine / ritual building** — daily loops the user returns to.
4. **Embedded gaming** — small introspective games/rituals (no swipe/match mechanics).
5. **Psychoanalysis insights from OAuth connections** — per-connector LLM narratives over the
   user's OWN data (Spotify→sonic psyche, GitHub→maker's mind, etc.). Runs on **server-side LLM
   (OpenRouter free tier — no user key needed)**; needs **no embeddings and no Pinecone**.
   LLMKeyManager.vue is intentionally orphaned; do not revive BYOK flows.

**Shelved / aspirational — do NOT build on these without an explicit ask:**
- The Pinecone **vibe-vector matching network** (ANN "three shadows", mutual-match swiping,
  karma ledger). The paid OpenAI embed key is intentionally **unfunded** — `/api/health/embeddings`
  returns 429 `insufficient_quota` and Pinecone is empty. Embedding/matching code degrades
  gracefully and should stay dormant. Grow **OAuth insights** instead of embeddings.
- Prefer work that runs entirely on **already-installed packages** (Tone.js, Matter.js, Web
  Audio, Canvas). Avoid anything that needs a paid API to function.

## Stack
- **Frontend**: Vue 3 + Vite + TypeScript + Tailwind — deployed to Vercel (`channelzero.vercel.app`)
- **Backend**: FastAPI (Python) — deployed to Render (`channelzero.onrender.com`)
- **Database**: Neon PostgreSQL (asyncpg pooled + unpooled connections)
- **Vector DB**: Pinecone (`channelzero` index) — vibe vectors for user matching (**SHELVED**, see Creative Direction)
- **Auth**: JWT HS256, 24hr expiry, stored as `channelzero-jwt` in localStorage

## Project Structure
```
/src
  /views          — Route-level page components
  /components     — Reusable UI components
  /composables    — Business logic and state (useAuthStore, useVibeStore, etc.)
  /router         — index.ts with auth guard
/server
  /app
    /auth         — Login, register, JWT, Google/X OAuth identity
    /analytics    — Admin funnel + connector metrics + insights panels
    /brain        — Image library (upload, browse, embeddings, similarity)
    /costar       — Co-Star credential-based natal chart ingestion
    /gcal         — Google Calendar OAuth + temporal pattern extraction
    /github       — GitHub OAuth + developer profile ingestion
    /intake       — Psychoanalytic confessional pipeline + matching
    /letterboxd   — Letterboxd API film taste ingestion
    /llm          — Encryption helpers (AES-256-GCM)
    /oracle       — 7D psychological synthesis + Pinecone upsert
    /poll         — Archetype poll tokens
    /psychometrics — Multi-part assessment scoring + profile generation
    /reddit       — Reddit OAuth + behavioral profile ingestion
    /spotify      — Spotify OAuth + sonic profile
    /steam        — Steam OpenID + game library ingestion
    /strava       — Strava OAuth + activity data
    /twitter      — X OAuth 2.0 PKCE data connector
    /vector       — Pinecone upsert/query + zeromind sessions
    /youtube      — YouTube OAuth + attention profile ingestion
  /migrations     — SQL files run by migrate.py (tracked in _migrations table)
```

## Auth Patterns
- `useAuthStore` — exposes `token`, `user`, `apiFetch` (auto-attaches Bearer token)
- Backend: `get_current_user_id` dep → returns UUID; `require_admin` dep → checks `is_admin` column
- Protected routes: `meta: { requiresAuth: true }` in router; guest-only: `meta: { guest: true }`
- Admin access: set `is_admin = true` in `users` table directly via Neon

## Database Conventions
- Migrations live in `server/migrations/NNN_name.sql`
- Run locally: `source server/venv/bin/activate && python -m server.app.migrate`
- Connections: use pooled `DATABASE_URL` for app, unpooled `DATABASE_URL_UNPOOLED` for migrations and admin queries
- OAuth tokens encrypted with AES-256-GCM via `encrypt_api_key` / `decrypt_api_key`

## Key Composables
| Composable | Purpose |
|---|---|
| `useAuthStore` | JWT token, user object, `apiFetch` wrapper |
| `useVibeStore` | Intake/vibe vector state, OAuth connection state |
| `useCosmicPhysics` | Matter.js physics: orbs, particles, stars, spring attractors |
| `useSpotifyPhysics` | Wraps cosmic physics with Spotify audio data (genre→color, valence field) |
| `useAdminStore` | Admin analytics API calls (funnel, connectors, users, events) |

## Canvas / Physics Pattern
- `useCosmicPhysics(canvasRef, options)` — base physics engine (Matter.js via npm)
- Two-canvas pattern: base canvas (physics) + overlay canvas (labels, HUD)
- `getOrbPositions()` returns current `{x, y, idx}[]` for overlay label placement
- Custom `rrect()` helper for rounded rects (avoids TypeScript `ctx.roundRect` compat issues)

## Deploy Workflow
1. `npm run build` locally to verify no TypeScript errors (`vue-tsc --noEmit`)
2. `git push origin main` → Vercel auto-deploys frontend
3. Render auto-deploys backend on push (build dir: `server/`, start: `uvicorn server.app.main:app`)
4. Render applies pending migrations automatically on deploy — **merging a migration PR runs it
   against production Neon**. Treat destructive migrations (DROP, data rewrites) as needing explicit
   sign-off before merge. Verify via the `_migrations` table, not by re-running migrate.

## Env Vars (Render must have all of these)
`DATABASE_URL`, `DATABASE_URL_UNPOOLED`, `JWT_SECRET`, `SERVER_ENCRYPTION_KEY`,
`PINECONE_API_KEY`, `OPENAI_EMBED_KEY`, `OPENAI_API_KEY`,
`SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`,
`X_CLIENT_ID`, `X_CLIENT_SECRET`, `TWITTER_DATA_REDIRECT_URI`,
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`,
`GCAL_REDIRECT_URI`,
`STEAM_API_KEY`,
`LETTERBOXD_API_KEY`, `LETTERBOXD_API_SECRET`,
`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI`,
`YOUTUBE_REDIRECT_URI`,
`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_REDIRECT_URI`,
`CORS_ORIGINS`

## Commit Style
- Short, imperative subject line — no body needed for small changes
- No `Co-Authored-By` lines
- Prefer one focused commit per feature/fix

## Route Map
| Route | Auth | Purpose |
|---|---|---|
| `/` | no | Home hub |
| `/login` | guest | Auth |
| `/learn` | no | Learn index |
| `/learn/:slug` | no | Learn article |
| `/sessions` | no | Sessions listing |
| `/about` | no | About page |
| `/discovery` | yes | Physics-driven onboarding |
| `/onboarding` | yes | Onboarding flow |
| `/calibrate` | yes | All connector OAuth (Spotify, X, Strava, CoStar, Letterboxd, Steam) |
| `/intake` | yes | Psychometric confessional intake |
| `/psychoanalysis` | yes | Psychometric assessment + narrative |
| `/calibrate/:provider` | yes | Per-connector data reading + psychoanalysis |
| `/portrait` | yes | Integrated psychoanalytic portrait (2+ providers) |
| `/universe` | yes | Solar system signal visualization |
| `/spotify` | yes | Spotify sonic field physics |
| `/x` | yes | X/Twitter signal visualization |
| `/journal` | yes | Journal editor (text, drawing, audio, mood) |
| `/checkin` | yes | Daily check-in + mood arc |
| `/admin` | yes+admin | Analytics dashboard |
| `/zeromind` | no | Trance entrainment (Tone.js) |
| `/audio` | no | Adaptive entrainment audio player |
| `/trance` | no | Trance visualization |
| `/hypno` | no | Hypno visualization |
| `/spiral` | no | Spiral visualization |
| `/studio` | no | Glass studio |
| `/liquidglass` | no | Liquid glass experiment |
| `/fitting` | no | Body/swimsuit configurator (standalone) |
| `/poll` | no | Archetype poll |
| `/reader` | no | Reader view |
| `/webaudio` | no | WebAudio experiment |
