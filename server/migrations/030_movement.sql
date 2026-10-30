-- Movement from Apple Health, posted by the user's own iOS Shortcut.
-- Least data: when a workout started and ended, and its type. No heart rate,
-- no distance, no route or location. Never read by the Oracle, the portrait
-- or any LLM path (see server/app/movement/router.py).

-- One ingest token per user, stored as a SHA-256 hash. The plain token is
-- shown once, pasted into the Shortcut, and works only for POST /movement/workouts.
CREATE TABLE IF NOT EXISTS movement_tokens (
    user_id     UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ
);

-- Keyed on start time so re-running the Shortcut over the same days is an
-- upsert, never a double count. `day` is the local date the workout started
-- on, taken from the offset the phone sent.
CREATE TABLE IF NOT EXISTS movement_workouts (
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at  TIMESTAMPTZ NOT NULL,
    ended_at    TIMESTAMPTZ NOT NULL,
    day         DATE NOT NULL,
    kind        TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, started_at)
);

CREATE INDEX IF NOT EXISTS movement_workouts_user_day_idx ON movement_workouts (user_id, day);
