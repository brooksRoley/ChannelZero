-- Index on user_id for ON DELETE CASCADE performance when a user is removed.
-- Migration 025 created the connect_tokens table with only an expires_at index.
CREATE INDEX IF NOT EXISTS connect_tokens_user_id_idx ON connect_tokens (user_id);
