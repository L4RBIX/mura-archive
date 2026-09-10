# MURA · Мұра

A voice-first family memory archive for Kazakh and Russian households.

Someone talks — a grandmother, at a table, in whatever mix of languages she
actually speaks. MURA turns that recording into a durable, evidence-grounded
archive: transcript, then the people, places, dates and relationships the story
contains, then a family graph that grows with every recording.

The user's mental model is «Я просто разговариваю с бабушкой.» Everything below
this line stays underneath it.

## Live

| | URL |
| --- | --- |
| App | https://mura-rho.vercel.app |
| Core API | https://mura-api-production.up.railway.app |

## Architecture

```
Browser ──▶ Next.js (Vercel)
              │  proxy: strict route allowlist, server-side bearer only
              ▼
            Core API (Railway)  ──▶  PostgreSQL (Supabase)
              │  submits and reads jobs; never processes them
              ▼
            Worker (Railway)
              ├─▶ Whisper        transcript, language preserved
              └─▶ DeepSeek       people · places · dates · claims · conflicts
```

Two processes, one rule: `apps/api` submits and reads jobs, `apps/worker`
claims and executes them. Serving a request never starts processing.

**Durable jobs.** Work is claimed with `SELECT … FOR UPDATE SKIP LOCKED` under a
lease with a heartbeat. A worker that crashes loses nothing: the lease expires
and another worker reclaims the job. The user can close the tab the moment they
press save.

**Evidence before facts.** Extraction produces graded claims, not prose. Only
sufficiently grounded claims materialise into the family graph, and conflicting
memories are preserved as conflicts rather than silently overwritten. An
extracted name is not automatically a person.

**Identity is separate from authorization.** Supabase says who someone is; MURA
decides what they may do. The chain is `bearer → Principal → User →
FamilyMembership → Capability`, and membership is read from PostgreSQL on every
request — never baked into a token.

## Stack

**Frontend** — Next.js 15 (App Router), React 19, TypeScript, Tailwind 4,
Framer Motion, Vitest.
**Backend** — Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PyJWT.
**Data** — PostgreSQL. **Auth** — Supabase (OIDC). **Hosting** — Vercel, Railway.

## Language handling

Recordings routinely switch languages inside one sentence:

> «Менің әжем Алматыда тұрды, потом мы поехали к ней летом»

Two rules are enforced in code. Only `/audio/transcriptions` is called, never
`/audio/translations`, so nothing is rendered into English. And the `language`
parameter is never sent, because pinning a decoder mangles the other language.

Whisper reports one language per request. `mura.asr.language` separately reads
the produced text and reports every language actually present, using the nine
graphemes that exist in Kazakh Cyrillic but not Russian, plus closed-class
function words from both. Each recording stores `detected_language`,
`transcript_languages` and `mixed_language`.

The interface language never reaches the recogniser. What someone set the UI to
says nothing about what they spoke into the microphone.

## Local setup

Requires Python 3.11+, Node 20+, and a local PostgreSQL.

```bash
# Backend
cd Mura_project
python -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env          # then fill in the values below
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m uvicorn apps.api.main:app --port 8001
.venv/bin/mura-worker         # separate terminal

# Frontend
cd MURA-app
npm install
npm run dev
```

## Environment

### Core (`Mura_project/.env`)

| Variable | Notes |
| --- | --- |
| `MURA_ENVIRONMENT` | `local`, `test`, `staging`, `production` |
| `DATABASE_URL` | PostgreSQL. SQLite is rejected outside local |
| `CORE_API_KEY` | Service-internal. Never reaches the browser |
| `OPERATIONS_API_KEY` | Operator routes. Must differ from `CORE_API_KEY` |
| `WORKER_REGISTRATION_TOKEN` | ASR transport |
| `AUTH_MODE` | `oidc` in production; `disabled` is local/test only |
| `AUTH_ISSUER` / `AUTH_AUDIENCE` | Must match the provider's tokens exactly |
| `AUTH_JWKS_URL` | Server configuration only — a token never picks it |
| `AUTH_ALLOWED_ALGORITHMS` | Asymmetric only. `ES256` for Supabase |
| `ASR_PROVIDER` | `whisper` or `kaggle` |
| `WHISPER_API_KEY` / `WHISPER_BASE_URL` / `WHISPER_MODEL` | Any OpenAI-compatible transcription host |
| `DEEPSEEK_API_KEY` | Structured extraction |
| `AUDIO_STORAGE_DIR` | Absolute path in production |
| `CORS_ALLOWED_ORIGINS` | Explicit list. `*` is rejected in production |

### App (`MURA-app/.env.local`)

| Variable | Notes |
| --- | --- |
| `MURA_API_URL` | Core's base URL |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<ref>.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Public by design; authorises nothing alone |

There is deliberately no service credential in the frontend. The bearer token
exists only server-side, and the proxy discards any `Authorization` header a
caller supplies.

## Database

One linear Alembic chain, single head, 18 tables.

```bash
cd Mura_project && .venv/bin/python -m alembic upgrade head
```

Schema is owned by Alembic alone. The worker never creates tables, and
`DATABASE_AUTO_CREATE` is rejected in production.

## Tests

```bash
cd MURA-app     && npx vitest run     # 437 tests
cd Mura_project && pytest             # 1032 tests
```

The backend suite needs `TEST_POSTGRES_URL` pointing at a disposable database.
Without it, the PostgreSQL-gated authorization cases skip silently — the
strongest BOLA and membership proofs — and a green run means considerably less
than it appears to.

## Deployment

**Frontend** — Vercel, project root `MURA-app`. Framework preset must be
`nextjs`; `vercel.json` pins it.

**Core and worker** — Railway, from `Mura_project/Dockerfile`. Both processes
ship as one image and differ only in entrypoint, so they cannot drift apart
between deploys. Migrations run at container start.

**Auth callbacks** — add `https://<your-app>/api/auth/callback` to the Supabase
project's redirect allowlist, and set the same origin as the authorised redirect
URI on the Google OAuth client.

## Security

These are implemented, and the job is not to regress them.

- The proxy is an allowlist, not a tunnel. Operator, worker, trace and replay
  routes are never exposed to the browser.
- RS256 or ES256 only. `HS*` and `none` are rejected by config validation:
  mixing symmetric and public-key verification is how key confusion happens.
- **BOLA:** `404` for both "not your family" and "no such family" — a response
  must never confirm that a private family exists. `403` only for a confirmed
  member lacking a capability. `401` only for no usable identity.
- A MURA account is not an archive person. Nothing maps a user to a `person_id`.
- Family scope comes from the authorized list Core returns. A remembered family
  id is a UI preference, never authorization.
- Tokens, keys, `DATABASE_URL` and full transcripts are never logged.

## Licence

MIT.
