"""
Movement: workouts from Apple Health, posted by the user's own iOS Shortcut.

Apple Health has no web API. A Shortcut on the phone finds the day's
workouts and POSTs them here with a per-user ingest token
(docs/APPLE_HEALTH_SHORTCUT.md). It replaced the Strava connector
(app/providers.py).

Least data: start, end and type. No heart rate, distance or location.
Movement is evidence the user reads, never a score, and it never reaches an
LLM: it isn't a connector column, so the Oracle, the portrait and the
correlations can't see it (tests/test_movement.py checks).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from ..auth.deps import get_current_user_id
from ..db import get_conn
from ..ratelimit import limiter

router = APIRouter()

MAX_WORKOUT = timedelta(hours=24)
KEEP_DAYS = 400  # older workouts are dropped on each ingest


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Workout(BaseModel):
    start: datetime
    end: datetime
    type: str = Field(min_length=1, max_length=60)

    @field_validator("start", "end")
    @classmethod
    def _needs_offset(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("needs a UTC offset (Shortcuts' ISO 8601 format has one)")
        return v

    @field_validator("type")
    @classmethod
    def _tidy(cls, v: str) -> str:
        return " ".join(v.split())


class WorkoutBatch(BaseModel):
    workouts: list[Workout] = Field(max_length=100)


def _check(w: Workout, now: datetime) -> str | None:
    """Why a workout is refused, or None."""
    if w.end <= w.start:
        return "ends before it starts"
    if w.end - w.start > MAX_WORKOUT:
        return "longer than 24 hours"
    if w.start > now + timedelta(minutes=5):
        return "starts in the future"
    return None


async def _user_for_token(authorization: str | None) -> UUID:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, {"code": "no_token", "message": "Missing ingest token."})
    token = authorization.split(" ", 1)[1].strip()
    async with get_conn() as conn:
        user_id = await conn.fetchval(
            "UPDATE movement_tokens SET last_used_at = now() WHERE token_hash = $1 RETURNING user_id",
            _hash(token),
        )
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, {"code": "bad_token", "message": "Unknown ingest token."})
    return user_id


# ── From the phone ───────────────────────────────────────────────────────────


@router.post("/workouts")
@limiter.limit("60/hour")
async def receive_workouts(request: Request, body: WorkoutBatch, authorization: str | None = Header(default=None)):
    """The Shortcut's endpoint. Idempotent: the same workout twice is one row."""
    user_id = await _user_for_token(authorization)
    now = datetime.now(timezone.utc)
    rows, refused = [], []
    for i, w in enumerate(body.workouts):
        why = _check(w, now)
        if why:
            refused.append({"index": i, "why": why})
        else:
            # The local date it started on, from the phone's own offset.
            rows.append((user_id, w.start, w.end, w.start.date(), w.type))
    async with get_conn() as conn:
        if rows:
            await conn.executemany(
                """
                INSERT INTO movement_workouts (user_id, started_at, ended_at, day, kind)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id, started_at)
                DO UPDATE SET ended_at = EXCLUDED.ended_at, day = EXCLUDED.day,
                              kind = EXCLUDED.kind, received_at = now()
                """,
                rows,
            )
        await conn.execute(
            "DELETE FROM movement_workouts WHERE user_id = $1 AND day < $2",
            user_id, (now - timedelta(days=KEEP_DAYS)).date(),
        )
    return {"saved": len(rows), "refused": refused}


# ── From the app ─────────────────────────────────────────────────────────────


@router.post("/token")
@limiter.limit("5/minute")
async def issue_token(request: Request, user_id: UUID = Depends(get_current_user_id)):
    """Mint (or replace) the ingest token. The plain token is returned once."""
    token = secrets.token_urlsafe(32)
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO movement_tokens (user_id, token_hash) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE
            SET token_hash = EXCLUDED.token_hash, created_at = now(), last_used_at = NULL
            """,
            user_id, _hash(token),
        )
    return {"token": token}


@router.delete("/token")
async def revoke_token(user_id: UUID = Depends(get_current_user_id)):
    async with get_conn() as conn:
        await conn.execute("DELETE FROM movement_tokens WHERE user_id = $1", user_id)
    return {"revoked": True}


@router.get("/status")
async def movement_status(user_id: UUID = Depends(get_current_user_id)):
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "SELECT created_at, last_used_at FROM movement_tokens WHERE user_id = $1", user_id,
        )
    return {
        "has_token": row is not None,
        "last_received_at": row["last_used_at"].isoformat() if row and row["last_used_at"] else None,
    }


@router.get("/days")
async def movement_days(
    days: int = Query(default=14, ge=1, le=KEEP_DAYS),
    user_id: UUID = Depends(get_current_user_id),
):
    """Minutes moved per day, newest first. Days with nothing logged are absent."""
    since: date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT day, kind, SUM(EXTRACT(EPOCH FROM ended_at - started_at)) AS seconds
            FROM movement_workouts
            WHERE user_id = $1 AND day >= $2
            GROUP BY day, kind
            ORDER BY day DESC, seconds DESC
            """,
            user_id, since,
        )
    out: dict[str, dict] = {}
    for r in rows:
        d = out.setdefault(r["day"].isoformat(), {"date": r["day"].isoformat(), "minutes": 0, "kinds": []})
        mins = round(float(r["seconds"]) / 60)
        d["minutes"] += mins
        d["kinds"].append({"kind": r["kind"], "minutes": mins})
    return {"days": list(out.values())}


@router.delete("")
async def delete_movement(user_id: UUID = Depends(get_current_user_id)):
    """Delete every stored workout and the token."""
    async with get_conn() as conn:
        await conn.execute("DELETE FROM movement_workouts WHERE user_id = $1", user_id)
        await conn.execute("DELETE FROM movement_tokens WHERE user_id = $1", user_id)
    return {"deleted": True}
