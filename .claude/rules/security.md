# Security & privacy invariants

Family recordings contain names, addresses, dates, health details, disputes and
private stories. Treat the archive as sensitive personal data. These invariants are
already implemented — the job is to **not regress them**.

## Token & credential boundary

- The frontend holds **no** service credential. `MURA_CORE_API_KEY` is not read
  anywhere in `MURA-app`, and must never be introduced.
- The MURA bearer token exists **only** server-side, resolved in
  `src/lib/auth/server-session.ts` → `providers/clerk/adapter.ts`. It must never reach
  the browser, `localStorage`, `sessionStorage`, or client state.
- The proxy **discards any `Authorization` header the caller supplied**. A client
  must never be able to present its own bearer and have it forwarded.
- There is **no fallback** from a missing user session to `CORE_API_KEY`. An
  operational gap must never become an authentication bypass.
- Separate credentials stay separate: `CORE_API_KEY` (service-internal),
  `OPERATIONS_API_KEY` (destructive operator routes), `WORKER_REGISTRATION_TOKEN`
  (ASR transport). Config rejects `OPERATIONS_API_KEY == CORE_API_KEY` in
  production-like environments.

## The proxy is an allowlist, not a tunnel

`MURA-app/src/app/api/mura/[...path]/proxy.ts` pins each route to its methods.

Allowed: `v1/capabilities`, `v1/me`, `v1/families` (GET/POST), family detail, members
(GET/PATCH/DELETE), recordings (POST/GET), review-items (GET), jobs (GET).

**Never expose:** `v1/operations/*`, `v1/workers/*`, `v1/jobs/{id}/trace`,
`v1/families/{id}/replays`, `v1/process-transcript`. Core classifies these as
service-internal or operator surfaces; exposing them hands the browser release control
and retention deletion.

Adding a route means updating the allowlist **and**
`src/mura/identity/route_classification.py` — a test walks the live OpenAPI surface
and fails on any unclassified route.

## Authentication

Provider-neutral OIDC in `src/mura/identity/auth.py`; PyJWT appears only there.

- **RS256 only.** HS\* and `none` are rejected by config validation — mixing symmetric
  and public-key verification is how key-confusion attacks happen.
- Require and verify `exp`, `iss`, `aud`, `sub`; verify signature and `nbf`.
- The JWKS URL comes from **server configuration only**. A token must never influence
  where keys are fetched — that is what stops a forged `iss` becoming SSRF.
- Failures stay uniform. Unknown key, bad signature and expiry are one answer;
  distinguishing them helps only an attacker.
- `AUTH_MODE=disabled` is local/test only and is rejected in staging/production.
  There is deliberately no debug header that can authenticate a request.

## Authorization

MURA owns authorization. It is **not** delegated to Clerk Organizations.

`bearer → Principal → internal User → FamilyMembership → Capability → resource`

- Roles: `owner` ⊃ `editor` ⊃ `viewer`. Routes ask for a **capability**; they never
  compare role strings. The table lives in `src/mura/identity/policy.py`.
- Never bake `family_id`, role or `person_id` into a JWT — it would be stale the
  moment an owner changed a role. Membership is read from PostgreSQL per request.

## BOLA / IDOR

Status semantics are fixed once in `apps/api/authz.py`:

- **401** — no usable identity.
- **404** — *both* "not a member" and "family does not exist". Never distinguish them;
  a response must never confirm that a private family exists.
- **403** — only a confirmed member lacking a capability. Membership is already
  established, so this leaks nothing new.

A valid user in family A must never reach family B by guessing `family_id`,
`recording_id`, `job_id`, `person_id` or `conflict_id`.

## Identity separation

**A MURA account is not an archive Person.** Never map `user_id`, email or display
name to `person_id` / `speaker_person_id`. `currentSpeakerPersonId()` returns `null`
unconditionally — Core mints canonical `person_<32hex>` ids through entity resolution,
and the browser must never manufacture one.

## Family scope

No hardcoded family scope. `TRANSITIONAL_FAMILY_ID` and `family_mura_app` were
deliberately removed — never restore them, and never derive family scope from an
arbitrary localStorage value. Scope comes from the authorized list Core returns. A
remembered family id is a **UI preference, not authorization**.

## Local recording privacy

Three states, never conflated: unsent client draft · local `SavedMemory`
(localStorage + IndexedDB, **owner-scoped**) · canonical Core recording.

On sign-out, `purgeLocalRecordingsFor()` removes:
- the departing account's list entries **and** audio blobs;
- legacy *unscoped* keys, whose ownership is unknowable.

It deliberately does **not** remove another account's namespace — someone else signing
in is not a reason to destroy a third party's data, and scoped reads already make it
unreachable. Canonical Core recordings are never touched. A deleted local-only
recording does not return on re-login.

With no owner, reads return empty and writes **throw** rather than persist
unattributed data.

## Transport

Explicit CORS origin allowlist (`*` rejected in staging/production, at least one
origin required), GET/POST only, `allow_credentials=False`, `TrustedHostMiddleware`,
API docs off outside local/test, `DATABASE_AUTO_CREATE` forbidden in production,
PostgreSQL required. Proxy responses are `no-store, private` — a shared cache entry
would be one family's memories served to whoever asked next. Upstream error bodies are
never forwarded to the browser.

## Never log or print

Tokens, API keys, `DATABASE_URL`, full private transcripts, or config validation
errors that can echo supplied secrets. Do not send family content to external services
during testing.
