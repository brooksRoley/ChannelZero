-- Migration 029: Drop the BYOK user_api_keys table
-- The key store/list/delete and proxy endpoints were removed in PR #106
-- (2026-10-16); the psychometrics narrative and oracle now use the server LLM.
-- No application code reads or writes user_api_keys. Approved by Brooks 2026-10-16.
DROP INDEX IF EXISTS idx_apikeys_user;
DROP TABLE IF EXISTS user_api_keys;
