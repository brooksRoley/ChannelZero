-- Migration 027: Drop shelved match_interactions table
-- GET /match (the only consumer) removed in PR #69 (2026-09-16).
-- No application code references match_interactions or mutual_matches.
DROP VIEW IF EXISTS mutual_matches;
DROP TABLE IF EXISTS match_interactions;
