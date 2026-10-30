"""
Providers ChannelZero no longer connects to, and why.

A retired provider: new connections are refused, it's marked unavailable (the
frontend disables its buttons), and its stored data never reaches an LLM
(Oracle, portrait, correlations, narratives). A user can still see their own
stored snapshot.

Strava (retired 2026-10-30): the API now requires a paid Strava subscription
on the developer account, and Strava's API Policy §5.3 forbids using API data
to "develop, train, evaluate or operate any AI application", including
putting it in a model's context. ChannelZero's Strava connector did exactly
that. The planned replacement reads the user's own Strava data export on the
device, never uploaded.

Instagram (retired 2026-10-30): since the Basic Display API ended, Instagram's
only API serves Business and Creator accounts, so personal accounts can't
connect. The user's own data export is read on the device instead
(src/composables/instagramExport.ts).
"""

from __future__ import annotations

RETIRED_PROVIDERS: dict[str, str] = {
    "strava": (
        "Strava's API now needs a paid subscription and forbids any AI use of its data, "
        "so ChannelZero no longer connects to it."
    ),
    "instagram": (
        "Instagram's API only serves Business and Creator accounts now, so a personal "
        "account can't connect. Import your own Instagram data export instead: it stays on this device."
    ),
}


def is_retired(provider: str) -> bool:
    return provider in RETIRED_PROVIDERS


def ai_columns(columns: dict[str, str]) -> dict[str, str]:
    """A provider → column map without retired providers: what an LLM may read."""
    return {k: v for k, v in columns.items() if not is_retired(k)}
