"""Journal request/response models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class JournalEntryCreate(BaseModel):
    id: UUID | None = None  # client supplies for idempotent sync; server generates when absent
    text: str = Field(default="", max_length=50_000)
    drawings: list[dict] = Field(default_factory=list, max_length=500)
    mood: str | None = Field(default=None, max_length=100)
    poll_token_id: UUID | None = None
    created_at: datetime | None = None  # allow client to set (for sync)


class JournalEntryUpdate(BaseModel):
    text: str | None = None
    drawings: list[dict] | None = None
    mood: str | None = None


class JournalEntryResponse(BaseModel):
    id: UUID
    user_id: UUID
    text: str
    drawings: list[dict]
    mood: str | None
    poll_token_id: UUID | None
    created_at: datetime
    updated_at: datetime


class JournalSyncRequest(BaseModel):
    """Bulk sync: client sends all local entries with timestamps."""
    entries: list[JournalEntryCreate] = Field(max_length=200)
    last_sync: datetime | None = None  # entries changed since this time


class JournalSyncResponse(BaseModel):
    """Server responds with merged state."""
    entries: list[JournalEntryResponse]
    server_time: datetime
