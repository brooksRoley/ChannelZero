# Adding a connector

Every OAuth2 connector shares one flow in `server/app/oauth_base.py`. A new
one is a provider spec and a function that fetches and distills the
provider's data. Nothing else is needed.

## 0. Read the provider's terms first

Strava was retired on 2026-10-30 because its API Policy forbids any AI use of
API data. The Oracle, the portrait and the correlations all put connector
data into a model's context. Before writing code, answer these from the
provider's developer terms and write the answers in the router's docstring:

- **AI use.** May API data go into an LLM's context? If not, the provider
  can't feed `_DATA_COLUMNS`, the portrait or the Oracle. Use
  `providers.RETIRED_PROVIDERS` / `ai_columns`, or don't build it.
- **Cost.** Is API access free for a personal app, or does it need a paid tier
  (as X does for `tweet.read`, and Strava for all access)?
- **Caching.** How long may data be stored? `vibe_vectors.<provider>_data`
  keeps it until the user disconnects.
- **Display.** May data be shown only to the user it belongs to?

If the provider has no API you can use, an export the user brings, or an
iOS Shortcut (movement: `docs/APPLE_HEALTH_SHORTCUT.md`), is often the
honest route.

## 1. The spec

```python
from ..oauth_base import OAuthProvider, authorize_url, finish_callback

ACME = OAuthProvider(
    name="acme",                      # oauth_tokens.provider
    label="Acme",                     # shown in messages
    auth_url="https://acme.example/oauth/authorize",
    token_url="https://acme.example/oauth/token",
    scopes="read:profile",            # least that works
    client_id=lambda s: s.acme_client_id,
    client_secret=lambda s: s.acme_client_secret,
    redirect_uri=lambda s: s.acme_redirect_uri,
    # Optional:
    # token_auth="basic"              # client credentials as HTTP Basic (Reddit, X, Spotify)
    # pkce=True                       # verifier is generated and kept encrypted in the state (X)
    # client_id_param="client_key"    # TikTok's name for it
    # authorize_params={"access_type": "offline", "prompt": "consent"}   # Google refresh tokens
    # token_headers={"User-Agent": "channelzero/1.0"}                   # Reddit requires one
    # default_expires_in=None         # tokens that never expire (GitHub OAuth apps)
)
```

Add the three settings to `config.py` and the provider's `<name>_data`
column to `_PROVIDER_DATA_COLUMNS` (with a migration).

## 2. The routes

```python
@router.get("/connect")
async def acme_connect(user_id: UUID = Depends(get_current_user_id)):
    return {"auth_url": authorize_url(ACME, str(user_id))}


@router.get("/callback")
async def acme_callback(code: str, state: str):
    grant = await finish_callback(ACME, code, state)   # state checked, tokens stored
    async with httpx.AsyncClient(timeout=20.0) as client:
        profile = _distill(await _fetch(client, grant.access_token))
    await store_provider_data(grant.user_id, "acme_data", profile)
    return {"status": "connected"}
```

A redirect-style connect that takes a one-use `?ct=` connect token (Spotify,
Calendar) calls `require_configured(ACME)` **before**
`validate_connect_token(ct)`, so an unconfigured server doesn't spend the token.

Later reads use `refresh_if_needed(user_id, "acme", token_url, client_id,
client_secret)`. It answers 409 `reauth_required`, never 401: the frontend
logs the user out on any 401.

## What the flow guarantees

- One-use state (nonce + replay check), 10-minute expiry.
- A PKCE verifier never appears readable in the state.
- The scope stored is the one the user **granted**, not the one requested.
- A refused exchange, or a 200 without a token, answers 400
  `{code: "token_exchange_failed", message}`. The provider's body goes to the
  log, never to the client.
- An unconfigured provider answers 503 `{code: "not_configured", message}`.

## Tests

`tests/test_oauth_flow.py` covers the flow with `httpx.MockTransport` and
guards every router: no copied state helpers, no `INSERT INTO oauth_tokens`,
no provider body or exception text in a `detail`. A new connector adds tests
for its distill function and its 503 guard (patch
`app.oauth_base.get_settings`).

## Not on the shared flow

- **Instagram**: a GET exchange on Facebook, then a long-lived token exchange
  on graph.instagram.com. It shares state and storage only. Its
  `ig_exchange_token` step comes from the Instagram Basic Display API, which
  Meta shut down in December 2024, so check it before relying on it.
- **Steam** (OpenID 2.0) and **Letterboxd** (signed requests): no OAuth2 code
  exchange. They share the state helpers.
