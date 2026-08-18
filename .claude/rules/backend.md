# Backend rules — `Mura_project`

Python 3.11+ · FastAPI · Pydantic v2 + pydantic-settings · SQLAlchemy 2 · PostgreSQL ·
Alembic · PyJWT. ~27,800 LOC in `src/mura/`, ~2,000 in `apps/`.

⚠️ The working tree is currently on **`feat/replicate-gigaam-asr` @ `989f820`** (the
unpromoted PR-04 branch), not `production/core-v1` @ `ea310f9`. Know which tree you
are reading.

## Two processes, one rule

- `apps/api` — FastAPI. **Submits and reads jobs only.** `CoreRuntime` deliberately
  holds no worker; serving a request must never start processing.
- `apps/worker` — standalone `mura-worker`. Claims and executes jobs. Owns the ASR
  client and DeepSeek pipeline. **Never creates schema** — Alembic owns that.

## Durable jobs & leases — preserve this

`processing_jobs` in PostgreSQL, claimed with `SELECT … FOR UPDATE SKIP LOCKED`.

- `lease_owner` + `lease_expires_at`, renewed by a heartbeat thread.
- A crashed worker loses nothing: the lease simply expires and another worker
  reclaims the job. Safety rests on the lease, **not** on shutdown bookkeeping. Never
  mark in-flight work completed or failed just because a process is stopping.
- `LeaseOwnershipLost` stops a stale worker from overwriting the state or archive
  result of the worker that legitimately reclaimed the job.
- Terminal jobs are not reclaimed. Attempt counts and backoff are tracked.
- Defaults: 300s lease, 60s heartbeat. Config **rejects** heartbeat ≥ lease, or a
  lease shorter than 3 heartbeats — a transient DB blip must not lose a lease.
- Worker ids are random `worker_<uuid4hex>`: no hostname, username or PID, because
  worker ids reach traces and operator tooling.

Heartbeat renewal must stay independent of the ASR poll loop. A prediction can sit in
a provider queue through a cold start; tying renewal to polling would let a lease lapse
mid-prediction and hand the job to a second worker — paying for the same audio twice.

## Audio storage

`AudioStorage` Protocol (`save` / `exists` / `delete` / `open` / `materialize`);
`LocalAudioStorage` is the only implementation. Address audio by **opaque
`storage_key`** built from family + recording + extension — never by arbitrary
filesystem path from domain code. Uploads are validated: size cap, MIME check and
magic-byte container sniffing, with SHA-256 and size recorded.

Local filesystem storage is a **known production gap** (blocks horizontal scaling),
not a bug. Do not pretend local disk is sufficient for scaled deployment; do not
implement cloud storage without an explicit decision.

## ASR

`build_asr_client(settings, registry)` in `src/mura/asr/factory.py` is the **single**
place that decides the provider. Never ask `settings.asr_provider` elsewhere — that is
how a cutover turns into a hunt through the codebase and how one forgotten branch
keeps calling the retired provider.

- **`kaggle`** — current default. Tunnelled GPU worker that registers itself in
  `worker_registrations`. Acknowledged transitional debt.
- **`replicate`** — GigaAM Multilingual, PR-04, **not promoted**. Status:
  `REPLICATE_CONFIGURATION_PENDING`. It stays unpromoted until validated live against
  real Russian and Kazakh audio; retiring the working recogniser first would leave
  nothing to fall back to. Selecting it without `REPLICATE_API_TOKEN` +
  `REPLICATE_DEPLOYMENT` fails at **startup**, by design.

Provider output is validated strictly (`GigaAMPrediction`): an empty transcript is a
**failed job**, not an empty success; spans must be ordered and non-negative;
arbitrary provider payload is refused rather than persisted.

GigaAM has **no language parameter** — one shared character vocabulary, no documented
per-call language selection — so `audio_language_applied` stays false. Never fabricate
language detection or confidence scores the model does not report.

**Known drift:** `/v1/capabilities` still reads `WorkerRegistrationRow("kaggle-asr")`
in `apps/api/main.py`. PR-04 did not update it, so a Replicate deployment would report
`UNAVAILABLE`. Fix this before promoting PR-04.

## Evidence, claims & archive — do not simplify away

This is the product's substance, not incidental complexity.

- `EvidenceClass`: `A_explicit`, `B_morphologically_explicit`, `C_speaker_anchored`,
  `D_context_resolved`, `E_inferred`, `U_uncertain`. **E and U are never sufficient
  for automatic graph materialization.**
- `AssertionMode`: explicit / inferred / uncertain.
- `EpistemicStatus`: asserted / uncertain / remembered_imprecisely / reported /
  competing / unresolved.
- `CoreferenceStatus`: resolved / ambiguous / unresolved / rejected.
- Conflicting memories are **preserved as conflicts**, never silently overwritten.
- An extracted name is not automatically a canonical Person. Entity resolution stays
  conservative.

Long-form extraction plans windows, preserves global segment ids, merges people
conservatively, isolates failed windows, validates the merged result globally and
enforces call budgets. Keep those guarantees.

Never destroy evidence/provenance metadata just because nothing displays it today.

## Configuration fails closed

`CoreSettings` rejects, in staging/production: `AUTH_MODE != oidc`; HS\* or `none` in
allowed algorithms; a non-HTTPS JWKS URL; `DATABASE_AUTO_CREATE=true`; a non-PostgreSQL
or SQLite `DATABASE_URL`; `OPERATIONS_API_KEY == CORE_API_KEY`; a relative
`AUDIO_STORAGE_DIR`; empty or `*` CORS origins. Keep it that way — an unconfigured
provider must fail at startup, never fall back to something permissive.

Config validation errors can echo supplied secrets: never log them verbatim (the API
raises a bare 503 "not configured" and the worker logs a refusal without detail).

## Migrations

Linear Alembic chain, single head `20260719_0010`, 18 tables. Do not create branches
or auto-create schema. Do not run migrations during an audit or investigation pass.

## Tests

87 test modules. ⚠️ `test_authorization_matrix.py` and `test_family_authorization.py`
**silently skip 24 PostgreSQL-gated cases** without `TEST_POSTGRES_URL` — the strongest
BOLA and membership proofs. Green without that variable does **not** mean covered. Set
it (pointing at a disposable test database) before trusting an authorization change.

Cheap targeted run:
`pytest tests/test_route_classification.py tests/test_authorization_matrix.py tests/test_family_authorization.py tests/test_auth_verifier.py tests/test_security_controls.py tests/test_operations_security.py`

Local `.env` currently has **no `DATABASE_URL`**, so `CoreSettings()` fails and Core
will not start as-is.

## DeepSeek

Real extraction logic lives in `src/mura/deepseek/`. Its job is structured archive
knowledge — people, relationships, events, places, dates, claims, stories, questions,
conflicts, evidence — **not** a summary. Do not make live calls casually, and never
send real family content to an external service during testing.
