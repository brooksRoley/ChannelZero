"""Analytics routes — admin dashboard data + connector feedback."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from ..auth.deps import get_current_user_id, require_admin
from ..db import get_conn
from ..ratelimit import limiter

router = APIRouter()

VALID_PROVIDERS = {
    "spotify", "twitter", "google", "strava",
    "steam", "letterboxd", "costar",
    "github", "reddit", "youtube",
}

# All valid client-side analytics events. Allowlist prevents authenticated
# users from injecting noise into the session_events table.
VALID_EVENTS = {
    # self-expression loop
    "journal_session_started",
    "journal_session_completed",
    "checkin_started",
    "checkin_completed",
    "practice_started",
    "zeromind_session_started",
    "zeromind_session_completed",
    # funnel steps
    "registered",
    "completed_poll",
    "connected_any",
    "connected_2plus",
    "completed_psychometrics",
    "had_first_session",
    "streak_active",
    # oracle / portrait
    "has_vibe_vector",
    "portrait_generated",
    "portrait_viewed",
}

# Core self-expression / hypnosis loop events (journal, check-in, zeromind).
# These drive the streak counter and the new funnel steps.
SELF_EXPRESSION_STARTED = [
    "journal_session_started",
    "checkin_started",
    "zeromind_session_started",
]
SELF_EXPRESSION_COMPLETED = [
    "journal_session_completed",
    "checkin_completed",
    "zeromind_session_completed",
]
SELF_EXPRESSION_EVENTS = SELF_EXPRESSION_STARTED + SELF_EXPRESSION_COMPLETED


# ── Feedback models ──────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    provider: str
    rating: int          # 1–5
    tags: list[str] = []


class EventRequest(BaseModel):
    event: str
    metadata: dict = {}


# ── User-facing: log a session event ────────────────────────────────────────

@router.post("/event", status_code=204)
@limiter.limit("60/hour")
async def log_event(
    request: Request,
    body: EventRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """Log a funnel event for the current user."""
    if body.event not in VALID_EVENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown event: {body.event}",
        )
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO session_events (user_id, event, metadata)
            VALUES ($1, $2, $3::jsonb)
            """,
            user_id, body.event, json.dumps(body.metadata),
        )


# ── User-facing: self-expression streak ──────────────────────────────────────

@router.get("/streak")
async def my_streak(user_id: UUID = Depends(get_current_user_id)):
    """Return the current user's consecutive-day self-expression streak.

    A day counts as active if it has any journal / check-in / zeromind event.
    Streak is the run of consecutive calendar days (UTC) ending today, or
    yesterday if today has no activity yet (so the streak isn't shown as broken
    until a full day is missed).
    """
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT (created_at AT TIME ZONE 'UTC')::date AS day
            FROM session_events
            WHERE user_id = $1
              AND event = ANY($2::text[])
              AND created_at >= now() - interval '60 days'
            ORDER BY day DESC
            """,
            user_id, SELF_EXPRESSION_EVENTS,
        )

    active_days = {r["day"] for r in rows}
    today = datetime.now(timezone.utc).date()

    # Start counting from today, or yesterday if nothing logged yet today.
    cursor = today
    if today not in active_days and (today - timedelta(days=1)) in active_days:
        cursor = today - timedelta(days=1)

    streak = 0
    while cursor in active_days:
        streak += 1
        cursor -= timedelta(days=1)

    last_7_days = [
        {"date": (today - timedelta(days=d)).isoformat(),
         "active": (today - timedelta(days=d)) in active_days}
        for d in range(6, -1, -1)
    ]

    return {
        "streak": streak,
        "today_active": today in active_days,
        "last_7_days": last_7_days,
    }


# ── User-facing: submit connector satisfaction ───────────────────────────────

@router.post("/feedback/connector", status_code=204)
async def submit_connector_feedback(
    body: FeedbackRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """Upsert a satisfaction rating for a connected provider."""
    if body.provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown provider: {body.provider}")
    if not (1 <= body.rating <= 5):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rating must be 1–5")

    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO connector_feedback (user_id, provider, rating, tags)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, provider) DO UPDATE SET
                rating     = EXCLUDED.rating,
                tags       = EXCLUDED.tags,
                updated_at = now()
            """,
            user_id, body.provider, body.rating, body.tags,
        )


# ── Admin: paginated user list with heuristics ───────────────────────────────

@router.get("/users")
async def admin_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _: UUID = Depends(require_admin),
):
    """Return all users with their psychological heuristics. Admin only."""
    offset = (page - 1) * per_page

    async with get_conn() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")

        rows = await conn.fetch(
            """
            SELECT
                u.id,
                u.email,
                u.display_name,
                u.created_at,
                u.is_admin,

                vv.attachment_style,
                vv.defense_mechanism,
                vv.readiness_score,
                vv.poll_theme,

                pt.archetype,
                pt.tone,
                pt.keywords,

                (
                    SELECT array_agg(provider ORDER BY provider)
                    FROM oauth_tokens ot WHERE ot.user_id = u.id
                ) AS connected_providers,

                (SELECT COUNT(*) FROM oauth_tokens ot WHERE ot.user_id = u.id)
                    AS connector_count,

                (SELECT COUNT(*) FROM journal_entries je WHERE je.user_id = u.id)
                    AS journal_entry_count,

                (vv.user_id IS NOT NULL)  AS has_vibe_vector,
                (pm.user_id IS NOT NULL)  AS has_psychometrics,

                (vv.spotify_data     IS NOT NULL) AS has_spotify,
                (vv.twitter_data     IS NOT NULL) AS has_twitter,
                (vv.gcal_data        IS NOT NULL) AS has_gcal,
                (vv.costar_data      IS NOT NULL) AS has_costar,
                (vv.letterboxd_data  IS NOT NULL) AS has_letterboxd,
                (vv.steam_data       IS NOT NULL) AS has_steam,
                (vv.github_data      IS NOT NULL) AS has_github,
                (vv.youtube_data     IS NOT NULL) AS has_youtube,
                (vv.reddit_data      IS NOT NULL) AS has_reddit,
                (vv.instagram_data   IS NOT NULL) AS has_instagram,
                (vv.tiktok_data      IS NOT NULL) AS has_tiktok,
                (vv.strava_data      IS NOT NULL) AS has_strava

            FROM users u
            LEFT JOIN vibe_vectors vv ON vv.user_id = u.id
            LEFT JOIN poll_tokens  pt ON pt.user_id = u.id
            LEFT JOIN user_psychometrics pm ON pm.user_id = u.id
            ORDER BY u.created_at DESC
            LIMIT $1 OFFSET $2
            """,
            per_page, offset,
        )

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "users": [dict(r) for r in rows],
    }


# ── Admin: conversion funnel ─────────────────────────────────────────────────

@router.get("/funnel")
async def admin_funnel(_: UUID = Depends(require_admin)):
    """Return step-by-step conversion counts across the user funnel."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                                                  AS total_registered,
                COUNT(*) FILTER (WHERE pt.user_id IS NOT NULL)            AS completed_poll,
                COUNT(*) FILTER (WHERE vv.user_id IS NOT NULL)            AS has_vibe_vector,
                COUNT(*) FILTER (WHERE ot.provider_count > 0)             AS connected_any,
                COUNT(*) FILTER (WHERE ot.provider_count >= 2)            AS connected_2plus,
                COUNT(*) FILTER (WHERE pm.user_id IS NOT NULL)            AS completed_psychometrics,
                COUNT(*) FILTER (WHERE se_open.user_id IS NOT NULL)       AS opened_self_expression_view,
                COUNT(*) FILTER (WHERE se_done.user_id IS NOT NULL)       AS completed_session,
                COUNT(*) FILTER (WHERE se_return.user_id IS NOT NULL)     AS returned_next_day
            FROM users u
            LEFT JOIN poll_tokens pt ON pt.user_id = u.id
            LEFT JOIN vibe_vectors vv ON vv.user_id = u.id
            LEFT JOIN user_psychometrics pm ON pm.user_id = u.id
            LEFT JOIN (
                SELECT user_id, COUNT(DISTINCT provider) AS provider_count
                FROM oauth_tokens GROUP BY user_id
            ) ot ON ot.user_id = u.id
            -- Self-expression / hypnosis core loop (journal, check-in, zeromind)
            LEFT JOIN (
                SELECT DISTINCT user_id FROM session_events
                WHERE event = ANY($1::text[]) AND user_id IS NOT NULL
            ) se_open ON se_open.user_id = u.id
            LEFT JOIN (
                SELECT DISTINCT user_id FROM session_events
                WHERE event = ANY($2::text[]) AND user_id IS NOT NULL
            ) se_done ON se_done.user_id = u.id
            LEFT JOIN (
                SELECT user_id FROM session_events
                WHERE event = ANY($3::text[]) AND user_id IS NOT NULL
                GROUP BY user_id
                HAVING COUNT(DISTINCT (created_at AT TIME ZONE 'UTC')::date) >= 2
            ) se_return ON se_return.user_id = u.id
            """,
            SELF_EXPRESSION_STARTED,
            SELF_EXPRESSION_COMPLETED,
            SELF_EXPRESSION_EVENTS,
        )

    data = dict(row)
    total = data["total_registered"] or 1  # avoid division by zero

    steps = [
        ("registered",            data["total_registered"]),
        ("completed_poll",        data["completed_poll"]),
        ("connected_any",         data["connected_any"]),
        ("connected_2plus",       data["connected_2plus"]),
        ("has_vibe_vector",       data["has_vibe_vector"]),
        ("completed_psychometrics", data["completed_psychometrics"]),
        # Core-loop steps (sourced from session_events)
        ("opened_self_expression_view", data["opened_self_expression_view"]),
        ("completed_session",           data["completed_session"]),
        ("returned_next_day",           data["returned_next_day"]),
    ]

    return [
        {"step": name, "count": count, "pct": round(count / total * 100, 1)}
        for name, count in steps
    ]


# ── Admin: per-connector stats ───────────────────────────────────────────────

@router.get("/connectors")
async def admin_connectors(_: UUID = Depends(require_admin)):
    """Return connection rate, drop rate, and avg satisfaction per provider."""
    async with get_conn() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")

        connection_rows = await conn.fetch(
            """
            SELECT provider, COUNT(DISTINCT user_id) AS connected_count
            FROM oauth_tokens
            GROUP BY provider
            ORDER BY provider
            """
        )

        feedback_rows = await conn.fetch(
            """
            SELECT
                provider,
                COUNT(*)                          AS feedback_count,
                ROUND(AVG(rating)::numeric, 2)    AS avg_rating
            FROM connector_feedback
            GROUP BY provider
            ORDER BY provider
            """
        )

        # Tags are unnested rather than array_agg'd: Postgres refuses to
        # accumulate arrays of differing lengths, and the column defaults to '{}'.
        tag_rows = await conn.fetch(
            """
            SELECT provider, tag, COUNT(*) AS n
            FROM connector_feedback, unnest(tags) AS tag
            GROUP BY provider, tag
            ORDER BY provider, n DESC, tag
            """
        )

    connected = {r["provider"]: r["connected_count"] for r in connection_rows}
    fb_map = {r["provider"]: dict(r) for r in feedback_rows}
    tags_by_provider: dict[str, list[str]] = {}
    for r in tag_rows:
        tags_by_provider.setdefault(r["provider"], []).append(r["tag"])

    all_providers = sorted(VALID_PROVIDERS)
    results = []
    for p in all_providers:
        conn_count = connected.get(p, 0)
        fb = fb_map.get(p, {})
        results.append({
            "provider": p,
            "connected_count": conn_count,
            "connection_rate_pct": round(conn_count / (total_users or 1) * 100, 1),
            "feedback_count": fb.get("feedback_count", 0),
            "avg_rating": float(fb["avg_rating"]) if fb.get("avg_rating") is not None else None,
            "top_tags": tags_by_provider.get(p, []),
        })

    return results


# ── Admin: recent session events ─────────────────────────────────────────────

@router.get("/events")
async def admin_events(
    event: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    _: UUID = Depends(require_admin),
):
    """Return recent session events, optionally filtered by event type."""
    async with get_conn() as conn:
        if event:
            rows = await conn.fetch(
                """
                SELECT se.id, se.user_id, u.email, u.display_name,
                       se.event, se.metadata, se.created_at
                FROM session_events se
                LEFT JOIN users u ON u.id = se.user_id
                WHERE se.event = $1
                ORDER BY se.created_at DESC LIMIT $2
                """,
                event, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT se.id, se.user_id, u.email, u.display_name,
                       se.event, se.metadata, se.created_at
                FROM session_events se
                LEFT JOIN users u ON u.id = se.user_id
                ORDER BY se.created_at DESC LIMIT $1
                """,
                limit,
            )

    return [dict(r) for r in rows]


# ── Admin: per-event stats (site sections view) ────────────────────────────

@router.get("/event-stats")
async def admin_event_stats(_: UUID = Depends(require_admin)):
    """Return per-event volume so the admin Sections view can show which parts
    of the site are instrumented, used, or dark. `valid_events` lets the client
    flag events it sends that the server would reject."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT
                event,
                COUNT(*)                                                       AS total,
                COUNT(DISTINCT user_id)                                        AS users,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '7 days') AS last_7d,
                MAX(created_at)                                                AS last_at
            FROM session_events
            GROUP BY event
            ORDER BY event
            """
        )
    return {
        "events": [
            {
                "event": r["event"],
                "total": r["total"],
                "users": r["users"],
                "last_7d": r["last_7d"],
                "last_at": r["last_at"].isoformat() if r["last_at"] else None,
            }
            for r in rows
        ],
        "valid_events": sorted(VALID_EVENTS),
    }


# ── Admin: Spotify profiles (paginated) ─────────────────────────────────────

@router.get("/spotify-profiles")
async def admin_spotify_profiles(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _: UUID = Depends(require_admin),
):
    """Return users with Spotify profile data. Admin only."""
    offset = (page - 1) * per_page

    async with get_conn() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM vibe_vectors WHERE spotify_data IS NOT NULL"
        )
        rows = await conn.fetch(
            """
            SELECT
                u.id, u.email, u.display_name,
                vv.spotify_data
            FROM vibe_vectors vv
            JOIN users u ON u.id = vv.user_id
            WHERE vv.spotify_data IS NOT NULL
            ORDER BY u.created_at DESC
            LIMIT $1 OFFSET $2
            """,
            per_page, offset,
        )

    profiles = []
    for r in rows:
        data = r["spotify_data"]
        parsed = json.loads(data) if isinstance(data, str) else data
        profiles.append({
            "user_id": str(r["id"]),
            "email": r["email"],
            "display_name": r["display_name"],
            "top_artists": parsed.get("top_artists", []),
            "genres": parsed.get("genres", []),
            "audio_avg": parsed.get("audio_avg", {}),
        })

    return {"total": total, "page": page, "per_page": per_page, "profiles": profiles}


# ── Admin: archetype distribution ────────────────────────────────────────────

@router.get("/archetypes")
async def admin_archetypes(_: UUID = Depends(require_admin)):
    """Return archetype distribution across all users."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT pt.archetype, COUNT(*) AS count
            FROM poll_tokens pt
            WHERE pt.archetype IS NOT NULL
            GROUP BY pt.archetype
            ORDER BY count DESC
            LIMIT 8
            """
        )
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM poll_tokens WHERE archetype IS NOT NULL"
        )
    return {
        "total": total or 0,
        "archetypes": [{"archetype": r["archetype"], "count": r["count"]} for r in rows],
    }


# ── Admin: attachment style breakdown ────────────────────────────────────────

@router.get("/attachment-styles")
async def admin_attachment_styles(_: UUID = Depends(require_admin)):
    """Return attachment style breakdown across all users."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT attachment_style, COUNT(*) AS count
            FROM vibe_vectors
            WHERE attachment_style IS NOT NULL
            GROUP BY attachment_style
            ORDER BY count DESC
            """
        )
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM vibe_vectors WHERE attachment_style IS NOT NULL"
        )
    return {
        "total": total or 0,
        "styles": [{"style": r["attachment_style"], "count": r["count"]} for r in rows],
    }


# ── Admin: connector depth histogram ────────────────────────────────────────

@router.get("/connector-depth")
async def admin_connector_depth(_: UUID = Depends(require_admin)):
    """Return histogram of users by number of connected providers."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT bucket, COUNT(*) AS count FROM (
                SELECT u.id,
                    LEAST(COALESCE(ot.provider_count, 0), 3) AS bucket
                FROM users u
                LEFT JOIN (
                    SELECT user_id, COUNT(DISTINCT provider) AS provider_count
                    FROM oauth_tokens GROUP BY user_id
                ) ot ON ot.user_id = u.id
            ) sub
            GROUP BY bucket
            ORDER BY bucket
            """
        )
    # Ensure all buckets 0-3 present
    histogram = {0: 0, 1: 0, 2: 0, 3: 0}
    for r in rows:
        histogram[r["bucket"]] = r["count"]
    return {"histogram": [{"connectors": k, "count": v} for k, v in sorted(histogram.items())]}


# ── Admin: Psychometric profiles (paginated) ────────────────────────────────

@router.get("/psychometrics")
async def admin_psychometrics(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _: UUID = Depends(require_admin),
):
    """Return users with psychometric data. Admin only."""
    offset = (page - 1) * per_page

    async with get_conn() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM user_psychometrics")
        rows = await conn.fetch(
            """
            SELECT
                u.id, u.email, u.display_name,
                pm.love_language, pm.sociosexual_orientation,
                pm.values_cluster, pm.narrative,
                pm.ipip_neo_scores, pm.ecr_r_scores,
                pm.created_at
            FROM user_psychometrics pm
            JOIN users u ON u.id = pm.user_id
            ORDER BY pm.created_at DESC
            LIMIT $1 OFFSET $2
            """,
            per_page, offset,
        )

    profiles = []
    for r in rows:
        ipip = r["ipip_neo_scores"]
        ecr = r["ecr_r_scores"]
        profiles.append({
            "user_id": str(r["id"]),
            "email": r["email"],
            "display_name": r["display_name"],
            "love_language": r["love_language"],
            "sociosexual_orientation": r["sociosexual_orientation"],
            "values_cluster": r["values_cluster"],
            "narrative": r["narrative"],
            "ipip_neo_scores": json.loads(ipip) if isinstance(ipip, str) else ipip,
            "ecr_r_scores": json.loads(ecr) if isinstance(ecr, str) else ecr,
            "created_at": str(r["created_at"]),
        })

    return {"total": total, "page": page, "per_page": per_page, "profiles": profiles}


# ── Admin: per-user connector data detail ────────────────────────────────────

@router.get("/users/{user_id}/connectors")
async def admin_user_connectors(
    user_id: UUID,
    _: UUID = Depends(require_admin),
):
    """Return all connector JSONB data for a specific user. Admin only."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                vv.spotify_data,
                vv.twitter_data,
                vv.strava_data,
                vv.gcal_data,
                vv.costar_data,
                vv.letterboxd_data,
                vv.steam_data,
                vv.github_data,
                vv.youtube_data,
                vv.reddit_data,
                vv.instagram_data,
                vv.tiktok_data
            FROM vibe_vectors vv
            WHERE vv.user_id = $1
            """,
            user_id,
        )

    if not row:
        return {"connectors": {}}

    def parse(val):
        if val is None:
            return None
        return json.loads(val) if isinstance(val, str) else val

    return {
        "connectors": {
            "spotify": parse(row["spotify_data"]),
            "twitter": parse(row["twitter_data"]),
            "strava": parse(row["strava_data"]),
            "gcal": parse(row["gcal_data"]),
            "costar": parse(row["costar_data"]),
            "letterboxd": parse(row["letterboxd_data"]),
            "steam": parse(row["steam_data"]),
            "github": parse(row["github_data"]),
            "youtube": parse(row["youtube_data"]),
            "reddit": parse(row["reddit_data"]),
            "instagram": parse(row["instagram_data"]),
            "tiktok": parse(row["tiktok_data"]),
        }
    }
