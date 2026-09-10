# MURA — Product Bible

**Status of this document.** Written during the Stage-0 assimilation/audit pass on
2026-08-18 and updated the same day after PR-DEBUG-01, PR-05 and the PR-06 archive
cutover. Every
architectural statement below was verified against source, runtime, schema, tests or
git at that date. Findings resolved by PR-DEBUG-01 are marked **[FIXED]** with the
branch that carries the fix rather than deleted, so the history stays readable. Aspirations are labelled **FUTURE TARGET**; things
that could not be checked are labelled **UNVERIFIED**. No secrets appear here.

Verification legend used throughout:
`[V]` verified against code/runtime/schema/git · `[V-RUNTIME]` observed in a running
system · `[PARTIAL]` partly confirmed · `[TARGET]` intended future state, not built ·
`[UNVERIFIED]` not checkable in this pass.

---

## 1. Product mission

MURA turns spoken family memory into a durable, explorable, evidence-grounded family
archive.

Families lose stories. Grandparents hold childhood, migration, relationships,
traditions, places, names and dates — and much of it exists only in spoken memory.
When the person is gone, the information goes with them. MURA exists so a family can
record an ordinary conversation and end up with a structured, sourced archive rather
than an audio file nobody replays.

It is **not** primarily a voice recorder, a transcription service, a genealogy
database, or a chatbot. Those are components. The product is a *living family memory
system*.

The user's mental model should be: **«Я просто разговариваю с бабушкой.»** All
complexity lives underneath.

## 2. Target users

The buyer/operator is typically a younger, non-technical family member preserving the
stories of a grandparent or parent. The experience must be simple, warm, emotionally
safe and trustworthy. The user should feel *"I am preserving something precious,"*
never *"I am configuring an AI pipeline."*

**Language context `[V]`** — MURA targets multilingual families: Russian, Kazakh and
mixed RU/KK code-switching. Names appear in multiple orthographies and
transliterations. Mixed-language speech is normal input, not malformed input. The
backend has dedicated linguistics modules for Russian, Kazakh, English and
multilingual handling (`src/mura/linguistics/`, ~2000 LOC).

## 3. Product principles

These are load-bearing, and the codebase demonstrably implements most of them.

1. **Preserve truth over impressive AI.** Never invent family facts for polish.
2. **Evidence matters.** Extracted facts trace back to recording → transcript →
   evidence span. `[V]`
3. **Uncertainty is a feature.** "Нужно уточнить" beats a confident hallucination.
   `[V]` — the domain model has first-class `AssertionMode`, `EpistemicStatus`,
   and a six-level `EvidenceClass` ladder.
4. **People are not model mentions.** An extracted name is not automatically a
   canonical Person; identity resolution is conservative. `[V]`
5. **User identity ≠ Person identity.** A MURA account is never mapped to an archive
   `person_id`. `[V]` — `currentSpeakerPersonId()` returns `null` unconditionally and
   documents why.
6. **Human review matters.** Users resolve ambiguity without understanding ML.
   `[PARTIAL]` — backend conflict/review APIs exist; no frontend surface yet.
7. **Family privacy is fundamental.** An archive must never be reachable by guessing
   an ID. `[V]`

## 4. Current user journeys (what actually works today)

**Works end-to-end `[V]`:**
sign up / sign in (Clerk) → MURA provisions internal `User` → `GET /v1/families` →
create family if none → select family → record audio → submit to Core → durable job
queued in PostgreSQL → standalone worker claims it under a lease → ASR → DeepSeek
extraction → archive/claims written → result polled back into the UI.

Evidence that this path has genuinely run: one real recording exists in local audio
storage (`family_b8c…/recordings/rec_021…/original.webm`). `[V]`

**Demo only (no backend):** family tree, person profiles, story reading, Ask MURA.

**Backend exists, no frontend at all:** conflicts, profiles, review items,
membership administration.

## 5. Ideal user journey `[TARGET]`

Create account → enter family archive → sit with grandmother → tap Record → talk →
save → leave the app → MURA processes safely → come back → read the story → see who
was mentioned → see relationships → clarify uncertainty → explore the tree → open a
person's memory profile → ask questions → add recordings over months → eventually
generate a family book.

At no point should the user think *"what model is this?"*, *"what is a claim?"*,
*"what is entity resolution?"*, or *"what does confidence 0.73 mean?"*

## 6. Frontend architecture

**Location** `D:\Mura_production\MURA-app` · **Stack `[V]`** Next.js 15.5.20 (App
Router, Turbopack), React 19.1.4, TypeScript 5, Tailwind CSS 4, Framer Motion 12.42,
Clerk `@clerk/nextjs` 7.7.7, Vitest 3.2.7. Package name is still the scaffold default
`react-app`.

**Routes `[V]`** — `/`, `/home`, `/record`, `/processing`, `/settings`, `/sign-in`,
`/sign-up`, `/tree`, `/person/[id]`, `/story/[id]`, `/ask`, plus the proxy
`/api/mura/[...path]`. There is **no** `/family` and **no** `/review` route.

**Shell `[V]`** — `src/app/layout.tsx` wraps everything in
`MuraI18nProvider → MuraSessionProvider` and renders
`<main className="mx-auto w-full max-w-[430px]">`. This single 430px cap is the root
cause of every desktop/tablet layout finding in §16.

**Core proxy `[V]`** — `src/app/api/mura/[...path]/proxy.ts` is a strict
method+regex **allowlist**, not a tunnel. It:
- resolves the bearer token server-side only and **discards any client-supplied
  `Authorization` header**;
- never reads a `MURA_CORE_API_KEY` (the frontend has no service credential at all);
- forces `cache: no-store` and `cache-control: no-store, private`;
- never forwards upstream error bodies to the browser;
- applies a 5s budget to `/v1/capabilities` and 30s elsewhere.

Allowlisted: `capabilities`, `me`, `families` (GET/POST), family detail, members
(GET/PATCH/DELETE), recordings (POST/GET), review-items (GET), jobs (GET).
Deliberately absent: `operations/*`, `workers/*`, `jobs/{id}/trace`, `replays`,
`process-transcript`. **Also absent: `profiles` and `conflicts`** — which is why
Tree/Person cannot show real data today.

**State owners `[V]`**
| Owner | Responsibility |
| --- | --- |
| `MuraSessionProvider` | Clerk session ↔ Core principal ↔ family session; re-bootstraps on Clerk session-key change |
| `family-session.ts` | authorized family list, selection, capability checks |
| `memory-store.ts` | local `SavedMemory` (localStorage) + audio (IndexedDB), owner-scoped |
| `recording-workflow.ts` / `use-recorder.ts` | capture → submit → poll |
| `pipeline-state.ts` / `pipeline-result.ts` | job status projection |
| `i18n.tsx` | UI locale **and** the demo people/stories fixtures |
| `use-mascot.ts` / `mascot/machine.ts` | Lastochka mascot state |

**Known duplication `[V]`** — `i18n.tsx` is both the localisation layer and the demo
data provider (it imports `@/data`). Any real Tree/Person/Story work must first
separate these.

## 7. Backend architecture

**Location** `D:\Mura_production\Mura_project` · **Stack `[V]`** Python ≥3.11,
FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2, PostgreSQL, Alembic, PyJWT,
Ruff, mypy. ~27,800 LOC across `src/mura/`, ~2,000 LOC in `apps/`.

This is **not** a REST wrapper around an LLM. Substantial deliberate domain logic
exists and is current `[V]`: evidence + evidence recovery, claim model (1,442 LOC),
claim semantics (1,221 LOC), coreference (language-aware, bounded), entity
resolution, relationship grounding, extraction sanitizer, long-form windowing and
merge, validation, archive ledger, conflict resolution, materialized profiles,
replay, release control, observability, retention, evaluation/scoring harness.

**Processes `[V]`**
- `apps/api` — FastAPI. Submits and reads jobs. `CoreRuntime` deliberately holds **no
  worker**; serving a request can never start processing.
- `apps/worker` — standalone `mura-worker`. Claims and executes jobs. Owns the ASR
  client and the DeepSeek pipeline. Never creates schema (Alembic owns that).

**Full route inventory `[V]`** (28 routes, all classified — see §9).

## 8. Data model

**Migrations `[V]`** — linear Alembic chain, single head `20260719_0010`, ten
revisions, no branches.

**18 tables `[V]`**

| Group | Tables |
| --- | --- |
| Identity | `users`, `families`, `family_memberships` |
| Recording/jobs | `recordings`, `processing_jobs`, `pipeline_results`, `worker_registrations` |
| Archive | `archive_people`, `archive_claims`, `archive_conflicts`, `archive_conflict_decisions`, `archive_corrections`, `family_graph_edges`, `materialized_person_profiles` |
| Ops/release | `processing_trace_events`, `pipeline_replay_runs`, `release_control`, `release_decisions` |

**Core epistemic vocabulary `[V]`** — this is what makes MURA more than a summariser:
- `AssertionMode`: explicit / inferred / uncertain
- `EpistemicStatus`: asserted / uncertain / remembered_imprecisely / reported /
  competing / unresolved
- `EvidenceClass`: `A_explicit`, `B_morphologically_explicit`, `C_speaker_anchored`,
  `D_context_resolved`, `E_inferred`, `U_uncertain` — **E and U are never sufficient
  for automatic graph materialization**
- `EvidenceSourceLayer`: raw_transcript / readable_transcript
- `CoreferenceStatus`: resolved / ambiguous / unresolved / rejected
- `ClaimObjectType`: person_mention / relationship / event / description / story /
  question

## 9. Auth & security

**Authentication `[V]`** — provider-neutral OIDC behind `src/mura/identity/auth.py`.
PyJWT appears only there. The deployed identity provider is **Supabase Auth** with
Google as the sign-in method; Clerk and the local development issuer remain behind
the same seam, and neither provider ever stands in for another's missing
configuration.

Supabase signs user tokens with **ES256**, not RS256. That is a configuration
change (`AUTH_ALLOWED_ALGORITHMS=ES256`), not a weakening: the invariant forbids
*symmetric* verification, because mixing symmetric and public-key verification is
how key-confusion attacks happen. ES256 is public-key and carries the same trust
property as RS256. HS\* and `none` are still rejected.

The frontend integration deliberately does not use Supabase's SDK, which keeps the
session in `localStorage`. Tokens live in an `httpOnly` cookie, the PKCE exchange
runs server-side, and the browser never holds a credential. `/api/auth/session`
tells the client only whether a session exists and an opaque key that changes with
the account; a trust-boundary test fails if a token ever appears in that response.

Verification enforces: `require: [exp, iss, aud, sub]`, signature, expiry,
nbf, issuer, audience, 30s default skew, JWKS URL from **server configuration only**
(a token can never steer key fetching → no SSRF). Failures are deliberately uniform
so an attacker cannot distinguish unknown-key from bad-signature.

`AuthMode.DISABLED` exists for local/test and is **rejected in staging/production** by
config validation. There is no debug header that can authenticate a request.

**Frontend session boundary `[V]`**
`browser → Clerk session → Next.js server (proxy) → bearer → Core`.
The browser never receives or stores a MURA bearer token. Verified: no
`localStorage`/`sessionStorage` token writes, no client `Authorization` override, and
the proxy discards caller-supplied `Authorization`.

**Clerk token strategy `[V]`** — `token-strategy.ts` documents measured behaviour:
session token ≈0ms but no `aud`; `mura-core` template ≈550ms via Backend API. The
adapter prefers the session token *whenever it already carries the required
audience*, checked locally, and falls back to the template. If the Clerk Dashboard is
configured to put `aud` on session tokens, the round trip disappears with no code
change. **Whether that Dashboard setting is currently active is `[UNVERIFIED]`** —
it is not observable from the repository. Token minting is cached per session and
de-duplicated via `mintOnce`.

**Authorization `[V]`** — MURA owns authorization; it is **not** delegated to Clerk
Organizations. Chain:
`bearer → Principal → internal User → FamilyMembership → Capability → resource`.

Roles and capabilities (`src/mura/identity/policy.py`), one table, no role-string
comparisons in routes:
- **viewer** — read family/recordings/jobs/review/profiles/conflicts/members
- **editor** — viewer + `create_recording`, `resolve_conflicts`
- **owner** — editor + `update_family`, `manage_members`

No family id, role or person id is ever baked into the JWT — membership is read from
PostgreSQL on every request, so a role change takes effect immediately.

**BOLA/IDOR protection `[V]`** — `apps/api/authz.py` fixes status semantics once:
**401** no usable identity · **404** *both* "not your family" and "no such family"
(so a response can never confirm a private family exists) · **403** only for a
confirmed member lacking a capability.

**Route classification `[V]`** — `src/mura/identity/route_classification.py` is
authoritative data, and a test walks the live OpenAPI surface and fails if any route
is unclassified. Five classes: `PUBLIC_INFRA`, `USER_APP`, `SERVICE_INTERNAL`,
`OPERATIONS`, `WORKER`. `PENDING_SWITCH_TO_PRINCIPAL` is **empty** and a test asserts
emptiness — reintroducing a service-token route on the user surface must be a
deliberate, visible act.

**Credential separation `[V]`** — `CORE_API_KEY` (service-internal),
`OPERATIONS_API_KEY` (destructive operator routes), `WORKER_REGISTRATION_TOKEN`
(ASR transport). All ≥32 chars. Config **rejects** `OPERATIONS_API_KEY == CORE_API_KEY`
in production-like environments. `get_auth_verifier` explicitly refuses to fall back
to `CORE_API_KEY` — "an operational gap must never become an authentication bypass."

**Transport hardening `[V]`** — CORS is an explicit origin allowlist (`*` rejected in
staging/production, at least one origin required), methods limited to GET/POST,
`allow_credentials=False`, `TrustedHostMiddleware`, request-id middleware, API docs
off by default outside local/test, `DATABASE_AUTO_CREATE` forbidden in
production-like environments, PostgreSQL required (SQLite explicitly rejected),
`AUDIO_STORAGE_DIR` must be absolute.

## 10. Recording & audio lifecycle

**Three states that must never be conflated `[V]`**

| State | Where | Lifetime |
| --- | --- | --- |
| A. Unsent client draft | MediaRecorder chunks, Blob, object URLs | discarded on navigation |
| B. Local SavedMemory | `localStorage` (metadata) + IndexedDB (audio), **owner-scoped** | until that account signs out |
| C. Canonical Core recording | `recordings` row + `AudioStorage` + job + pipeline result | permanent server data |

**Logout privacy semantics `[V]`** — implemented exactly as specified, in
`memory-store.ts`, with the reasoning documented in-source:
- departing account's local list **and** audio blobs → deleted;
- legacy *unscoped* keys (pre-ownership, attribution unknowable) → deleted;
- **another** account's dormant namespace → deliberately preserved (someone else
  signing in is not a reason to destroy a third party's data; scoped reads already
  make it unreachable);
- canonical Core recordings → untouched;
- a deleted local-only recording does **not** return on re-login.
Reads and writes are keyed `mura-saved-memories-v1::<user_id>` and `<user_id>::<id>`;
with no owner, reads return empty and writes **throw** rather than write unattributed
data.

**Capture vs processing `[V]`** — deliberately separated in
`recording-availability.ts`. Capture depends on the *user* (signed in, family,
`create_recording` capability, browser support, mic permission). Processing depends on
the *deployment* (`ready` / `degraded_queueable` / `unconfigured` / `unavailable` /
`unknown`). Because Core queues durably, a degraded recogniser still permits capture
and submission; submission is refused **only** when nothing could ever process the
result. `unknown` is treated as degraded — silence is never taken for health.

**Durable jobs `[V]`** — PostgreSQL `processing_jobs` with
`SELECT … FOR UPDATE SKIP LOCKED`, `lease_owner`, `lease_expires_at`, heartbeat
renewal, expiry-based reclaim, attempt counts and backoff. `LeaseOwnershipLost` stops
a stale worker from overwriting the state or archive result of the worker that
legitimately reclaimed the job. Worker ids are random (`worker_<uuid4hex>`) and carry
no hostname/username/PID. Defaults: 300s lease, 60s heartbeat, and config **rejects**
a heartbeat ≥ lease or a lease shorter than 3 heartbeats.

**Audio storage `[V]`** — `AudioStorage` Protocol (`save`/`exists`/`delete`/`open`/
`materialize`) with `LocalAudioStorage` the only implementation. Opaque
`storage_key` built from family+recording+extension; SHA-256, size, MIME validation
and magic-byte container sniffing. Domain code never addresses audio by arbitrary
filesystem path.

## 11. ASR & DeepSeek status

**ASR — current `[V]`** — the deployed provider is **Whisper**
(`ASR_PROVIDER=whisper`), reached over an OpenAI-compatible transcription API.
`build_asr_client` in `src/mura/asr/factory.py` is the single place that decides
this; nothing else reads `asr_provider`.

Two rules are enforced in code, and both come from what MURA records:

* only `/audio/transcriptions` is ever called, never `/audio/translations` — a
  translated transcript destroys the record the archive exists to keep;
* the `language` parameter is never sent. Recordings switch between Kazakh and
  Russian inside one sentence, so pinning the decoder mangles the other language.
  The interface language never reaches the recogniser: what someone set the UI to
  says nothing about what they spoke.

Whisper reports one language per request, which cannot describe «Менің әжем
Алматыда тұрды, потом мы поехали к ней летом». `mura.asr.language` therefore reads
the produced text and reports every language present, from the nine graphemes that
exist in Kazakh Cyrillic but not Russian plus closed-class function words from
both. Each recording stores `detected_language`, `transcript_languages` and
`mixed_language`. Markers that are also ordinary Russian words are deliberately
excluded: «да», «те» and «та» once made unambiguous Russian report as
code-switched, and claiming a language that was never spoken is the one thing
language reporting must not do.

Clients declare `requires_registered_worker`. A tunnelled GPU worker must announce
itself in `worker_registrations`; a hosted recogniser is addressed directly, and
deferring its jobs to wait for a row that will never be written would park every
recording forever. The flag defaults to true, so an undeclared client takes the
conservative path.

**ASR — Kaggle `[V]`** — still selectable (`ASR_PROVIDER=kaggle`): a tunnelled GPU
worker that registers itself. Acknowledged transitional debt, no longer the default.

**ASR — Replicate/GigaAM, PR-04, NOT promoted and no longer the active plan `[V]`** —
superseded in production by Whisper, which shipped because GigaAM has no hosted
API and running it needs a GPU deployment nobody had provisioned. The branch
remains valid work and the factory seam it introduced is what Whisper now uses.
The original description follows.


`ASRClient` protocol, `ReplicateASRClient`, `KaggleASRClient`, a single `build_asr_client`
factory, strict `GigaAMPrediction` output validation, prediction polling, and worker
integration. Target model is **GigaAM Multilingual** (MIT), chosen because Russian and
Kazakh are central product languages. The Cog service (`services/replicate_gigaam/`)
splits long audio on silence with Silero VAD so a split lands in a pause — fixed
windows would cut mid-word, and "the words most likely to be cut are the names and
dates this archive exists to keep."

Status is **REPLICATE_CONFIGURATION_PENDING**, by explicit design. The commit states:
*"Kaggle stays the default. Replicate is not production until it has been validated
live against real Russian and Kazakh audio."* Selecting `replicate` without
`REPLICATE_API_TOKEN` + `REPLICATE_DEPLOYMENT` fails at **startup**, not when a
family recording is already queued.

GigaAM exposes **no language parameter** — one shared character vocabulary, no
documented per-call language selection — so MURA leaves `audio_language_applied`
false rather than claiming a language was honoured. No language detection and no
confidence scores are fabricated.

**DeepSeek `[V]`** — real extraction logic exists (`src/mura/deepseek/`, ~2,100 LOC:
client, service, prompts, anchors, anchor prompts, focused extraction, telemetry).
Configured via `DEEPSEEK_API_KEY` with a primary + fallback model. **No live DeepSeek
call was made during this pass**, and no key value was read or printed.

Its purpose is **not** summarisation. It builds structured archive knowledge —
people, relationships, events, places, dates, claims, stories, questions, conflicts,
evidence — while preserving the original transcript and provenance.

**Long-form `[V]`** — `long_form.py` + `long_form_merge.py` plan windows, preserve
global segment ids, merge people conservatively, isolate failed windows, validate the
merged result globally and respect call budgets.

## 12. Archive & evidence model

Recording → transcript (`TranscriptEnvelope`) → evidence spans → claims → archive.

Claims are evidence-backed and provenanced. Conflicting family memories are
**preserved as conflicts, never silently overwritten** — `archive_conflicts` +
`archive_conflict_decisions` + a `resolve`/`dismiss`/`reopen` API exist and are
capability-guarded. `EvidenceClass` E and U can never auto-materialize into the family
graph. Frontend projection must not destroy evidence metadata merely because nothing
displays it today.

**FUTURE TARGET** — a user should be able to ask *«Почему MURA считает, что это его
брат?»* and reach the story/recording/excerpt behind the claim. The UI should render
conflicts humanely, e.g. *«В рассказах есть разные версии этой даты.»*

## 13. REAL vs DEMO surface matrix `[V-RUNTIME]`

Observed at `localhost:3000`, signed out, 1440×900.

| Surface | Data source | Auth gate | Status | Functional | Backend gap |
| --- | --- | --- | --- | --- | --- |
| `/` landing | static | none | **REAL** | yes | — |
| `/sign-in`, `/sign-up` | Clerk | public | **REAL** | yes | — |
| `/home` | Core `archive` overview + local drafts | auth strip | **REAL** | yes | — |
| `/record` | Core (`capabilities`, `families`, `recordings`) | **FamilyGate** | **REAL** | yes | — |
| `/processing` | Core (`jobs`, `recordings`) | **FamilyGate** | **REAL** | yes | — |
| `/settings` | Core (`me`, `families`, members) | none (auth strip) | **REAL** | yes | — |
| `/tree` | Core `people` + `relationships` | **FamilyGate** | **REAL** | yes | — |
| `/person/[person_id]` | Core `people`/`profiles`/`stories` | **FamilyGate** | **REAL** | yes | — |
| `/stories` | Core `stories` (paged) | **FamilyGate** | **REAL** | yes | — |
| `/story/[story_id]` | Core `stories/{id}` + audio | **FamilyGate** | **REAL** | yes | — |
| `/story/local-*` | local SavedMemory | **FamilyGate** | **REAL** (own draft) | yes | — |
| `/review` | Core `review-items` | **FamilyGate** | **REAL** (read-only) | yes | resolve/dismiss UI |
| `/ask` | scripted `mustafaDemoMemory` | none | **DEMO — labelled** | scripted | no Ask backend exists |

**The fixture family is gone.** `src/data` (nine invented relatives, their stories and
localized biographies), `InitialsAvatar`, the mock `AudioPlayer` and `use-mock-playback`
were deleted after proving zero consumers. `src/lib/i18n.tsx` no longer provides family
data at all — it is localisation only.

**Identity is an id.** Person is addressed by canonical `person_id`; a story attaches to
someone because the archive resolved its mentions through `person_mention` claims, never
because a name matched. `src/lib/demo-boundary.test.ts` (25 tests) enforces that real
surfaces cannot import fixtures, that Ask keeps declaring itself, and that the
name-matching join stays gone.

## 14. Technical debt & findings## 14. Technical debt & findings

Severity is deliberately conservative. **No P0 findings.** No credential leak, no
authentication bypass, no cross-account data leak, and no data-loss path was found.
The security posture is genuinely strong.

### P1 — correctness / product-blocking

**P1-1 [FIXED · frontend `main`] · `/tree` presented fabricated family facts as the
user's own family.**
`tree-view.tsx` reads only `useMuraI18n()` demo fixtures; the page has no
`FamilyGate` and no Core call. An authenticated user sees 9 invented relatives titled
«Ваша семья». Violates §3.1 and the "never fake family facts" rule.
*Bug + missing feature.*

**P1-2 [FIXED · frontend `main`] · `/ask` fabricated a grounded answer.** `ask-view.tsx` runs a timer
(`ANSWER_AT = 1300`) and returns `mustafaDemoMemory` regardless of the question. There
is no retrieval, no archive grounding and no Ask backend. Presented ungated and
unlabelled. *Bug (presentation) + missing feature (grounded Ask).*

**P1-3 [NOT A DEFECT] · Backend appeared unable to start.** `Mura_project/.env` has
no `DATABASE_URL`, but `DATABASE_URL` and `TEST_POSTGRES_URL` both exist at **User**
scope on this machine and simply were not inherited by the audit shell. Both point at
`mura_leases_test` on `127.0.0.1:5432` — a disposable test database. Core starts and
reports `{"status":"ready","database":"ready"}`. Credentials are deliberately **not**
committed to the repo. *Environment inheritance, not a code defect.*

**P1-4 [RESOLVED] · PostgreSQL-gated tests now actually run.** With
`TEST_POSTGRES_URL` exported, the five gated modules
(`test_authorization_matrix`, `test_family_authorization`, `test_identity_families`,
`test_postgres_atomicity`, `test_postgres_job_leases`) execute **215 tests with 0
skips**, and the full suite runs **938 tests, 0 failures, 0 skips**. The strongest
BOLA, membership and lease-concurrency proofs are confirmed against real PostgreSQL
18.4. The risk was never the tests — it was running them without the variable and
reading green as coverage.

**P1-5 [FIXED · `feat/replicate-gigaam-asr` only] · `/v1/capabilities` was hard-coded
to the Kaggle provider.** On PR-04 the endpoint now asks the configured recogniser via
`ASRAvailability`, and registration age travels through an optional `since` field so no
provider name reaches the endpoint. On canonical `production/core-v1` the `kaggle-asr`
lookup is **correct and unchanged**: that branch has no provider concept at all, and
changing it to anticipate Replicate would be speculative.

### Found and fixed in PR-DEBUG-01 (beyond the original P1 list)

- **Terminal job polling never stopped.** `processing-view.tsx` started a 1.5s
  interval and cleared it only on unmount. On `failed` — a screen a user can sit on
  indefinitely — it polled a job whose answer cannot change, forever; on `completed`
  it re-fetched the whole recording result every tick until navigation. `POLLING_STATES`
  already encoded the correct rule and the component never consulted it. *P2, fixed.*
- **Proxy error envelopes were cacheable.** The success path set
  `no-store, private`; 401/404/503 envelopes set nothing. A cached 401 outlives the
  sign-in that fixes it. *P2, fixed.*
- **405 answered `internal_error`.** `_CODE_BY_STATUS` had no 405 entry and defaults
  to `INTERNAL_ERROR`, so a wrong verb was reported as a server fault and a real 500
  became indistinguishable from a routing mistake. *P3, fixed, with a test pinning the
  whole table.*
- **A supply-chain test failed on Windows for a non-reason.** The cloudflared test
  asserted a POSIX execute bit on NTFS. The assertion now runs where the bit can exist;
  the checksum half runs everywhere. *Test-harness defect, fixed without weakening the
  Linux invariant.*
- **Settings promised a demo archive that was not below it.** *P3, fixed.*

**Still open, deliberately:** `PersonView` joins the viewer's real local recordings to
demo people **by name**, so a real memory mentioning «Марат» attaches to the fixture
Марат. The surface is now labelled, which closes the truthfulness gap, but the join
itself only disappears when the real profile API is wired. *P2 — belongs to the Tree/
Person data cutover, not to a debugging pass.*

### P2 — production hardening

- **P2-1** Audio storage is local filesystem only (`LocalAudioStorage`). Blocks
  horizontal scaling. Known and documented; **not** a bug.
- **P2-2** `KAGGLE_ASR_API_KEY` is unconditionally required (min 32 chars) even when
  `ASR_PROVIDER=replicate`, so a pure-Replicate deployment still needs a dead Kaggle
  credential.
- **P2-3** Clerk is a **development** instance (`picked-mole-1417.clerk.accounts.dev`);
  the console warns about development keys and usage limits. Its sign-in UI is also the
  only place the app renders English.
- **P2-4** No worker heartbeat to Core, so `/v1/capabilities` can only report "a
  worker once registered", never liveness. Correctly and honestly modelled
  (`live_health_verified: false`), but a real observability gap.
- **P2-5** Clerk's sign-in/sign-up UI renders in **English** inside an otherwise
  Russian product.
- **P2-6** No account deletion, family deletion, export, backup/restore testing, rate
  limiting or error tracking.

### P3 — cleanup / polish

- ~~**P3-1** Root `<html lang="ru">` is hard-coded even when the UI locale is
  Kazakh.~~ **[WITHDRAWN — the original finding was wrong.]** `MuraI18nProvider`
  already runs `document.documentElement.lang = locale` on every locale change. Only
  the server render is `ru`; the client corrects it. Not a defect.
- **P3-2** `package.json` name is still the scaffold default `react-app`.
- **P3-3** `/settings` reuses «Ниже — демонстрационный архив…» copy where no demo
  archive follows.
- **P3-4** Narrator name is the hard-coded demo string «Айсұлу»
  (`TRANSITIONAL_DEMO_NARRATOR`); every recording is labelled with it. The *person id*
  is correctly `null` — only the display label is demo.
- **P3-5** `i18n.tsx` doubles as the demo-data provider; localisation and fixtures
  should be separated before Tree/Person become real.
- **P3-6** `/story` renders a waveform + play button for audio that does not exist
  (`use-mock-playback.ts`). The page now carries a demo notice, so it no longer implies
  the audio is the viewer's; removing the mock player belongs to the Story cutover.
- **P3-7** Next reports `/mascot/part-mouth.png` as LCP and suggests `priority`. The
  mascot is a layered composite that already marks `part-base` and `part-head`
  priority; marking every layer would defeat the point. Left alone deliberately.

### Bug vs gap vs blocker — the distinction matters

| Category | Items |
| --- | --- |
| **Bug** | P1-1, P1-2 (unlabelled fabrication) · P1-5 drift · P3-3 — **all fixed** |
| **Missing feature** | grounded Ask, real Tree/Person, review/conflict UI, tablet & desktop layouts |
| **Demo feature** | `src/data` fixtures, `mustafaDemoMemory`, mock playback |
| **External infra pending** | Replicate deployment + live RU/KK validation, production Clerk instance, object storage, production database |
| **Environment gap** | P1-3 / P1-4 — **both resolved**; credentials live at User scope, never in the repo |
| **Polish** | remaining P3 |

Replicate being unconfigured is **not** a bug. A missing Ask backend is **not** a CSS
issue.

### Archive API added in PR-06

All family-scoped, Principal-native, capability-guarded, and covered by the BOLA matrix
on real PostgreSQL:

| Route | Capability |
| --- | --- |
| `GET /v1/families/{id}/archive` | `read_family` |
| `GET /v1/families/{id}/people` | `read_profiles` |
| `GET /v1/families/{id}/relationships` | `read_profiles` |
| `GET /v1/families/{id}/stories` (paged) | `read_recordings` |
| `GET /v1/families/{id}/stories/{story_id}` | `read_recordings` |
| `GET /v1/families/{id}/review-items` | `read_review` |
| `GET /v1/families/{id}/recordings/{id}/audio` | `read_recordings` |

Two rules the projection keeps. **The trust decision stays in Core** — which
relationship claims may be drawn as edges was already settled by evidence class when
the graph was materialized, and the API reads that rather than re-deriving it.
**Lists are bounded** — page size is clamped and list excerpts are trimmed, so a list
endpoint cannot become a way to pull every transcript in the family at once.

## 15. External blockers

1. Replicate deployment of GigaAM Multilingual + live validation against real Russian
   and Kazakh audio. Until then `ASR_PROVIDER` stays `kaggle`.
2. Production Clerk instance and its `aud`/JWT-template configuration.
3. Cloud object storage for audio.
4. Managed production PostgreSQL, backups and restore testing.
5. Local `DATABASE_URL` / `TEST_POSTGRES_URL` for full local verification.

## 16. Visual direction

**Should feel:** premium, warm, human, quiet, trustworthy, timeless, personal,
modern, intentional. Editorial warmth + modern interaction quality. References: family
album, oral history, journal, memoir, letters, recorded conversation — without cheesy
antique-paper pastiche.

**Must not feel:** generic SaaS, admin dashboard, CRM, crypto app, developer console,
analytics dashboard, cartoon. Avoid purple/blue "AI" gradients, neon, glowing robots,
floating-card soup and "AI magic" copy.

**What is already right `[V-RUNTIME]`** — the warm sand palette, the grain overlay,
the type scale, and especially `/story`, whose editorial typography and
«ЛЕТО 1963 · ПРИБЛИЗИТЕЛЬНО» uncertainty label are close to the target feel.

**Mascot `[V]`** — the Lastochka swallow is present and contributes warmth. It must
not dominate serious family content.

**MURA MUST REMAIN SILENT `[V]`** — the Alina/Ariana voice system was intentionally
removed in commit `3bc39da` ("Remove the assistant voice"). Do **not** reintroduce
auto voice-over, TTS assistants, voice pickers or autoplay speech. Microphone
*recording* is a separate capability and stays.

**Responsive reality `[V]`** — the app is a **fixed 430px mobile UI centred in
whatever viewport it gets**. Measured breakpoint usage across all `.tsx`:
`sm:` 0 · `md:` 1 · `lg:` 1 · `xl:` 0 · `2xl:` 0 — and the only file with any
breakpoint is `ui/button.tsx`. Containers are `max-w-[430px]`, `[360px]`, `[330px]`,
`[320px]`, `[300px]`, `[260px]`.

- **Desktop 1440px `[V-RUNTIME]`** — exactly the "phone UI floating in a 1440px page"
  anti-pattern. `/tree` is worse: the canvas is clipped by the 430px column, so person
  cards are visibly cut off at both edges (e.g. "Мара[т]").
- **Tablet 768px** — **`[UNVERIFIED]` at runtime**; browser resizing was declined
  during this pass. Statically certain: no tablet layout exists, so 768px renders the
  same 430px column.
- **Mobile 390px** — **`[UNVERIFIED]` at runtime** for the same reason. This is the
  one viewport the design actually targets and is expected to be closest to correct.

**Console/network `[V-RUNTIME]`** — clean. Zero errors, zero failed requests, no 4xx/5xx,
no repeated calls or polling loops on the surfaces visited. Only React DevTools info,
Clerk telemetry notices and the expected Clerk development-keys warning. Signed out,
`/api/mura/*` is correctly never called.

**Accessibility `[V]`** — `MotionConfig reducedMotion="user"` is set globally, so
reduced-motion is respected. Semantic HTML is used. Gaps: hard-coded `lang`, and
unverified focus/contrast behaviour.

## 17. Definition of production-ready

Visual polish is **not** production-ready. All of the following must hold:

- [ ] Cloud/object audio storage (not local disk) — **the binding constraint.**
      Because audio sits on a local disk, the API and worker must share one
      container: split across two services they get two filesystems, and a
      Railway volume mounts to only one. This is why horizontal scaling is
      currently impossible.
- [ ] Backups **and tested restore**
- [x] Worker deployed — supervision is still missing: the worker runs beside the
      API and nothing restarts it if it exits on its own.
- [ ] Monitoring, error tracking, rate limiting
- [ ] Account deletion, family deletion, export, retention
- [ ] Provider cost controls
- [x] Production PostgreSQL (Supabase) and a production identity provider
      (Supabase Auth with Google)
- [ ] ASR validated live on real RU/KK audio — Whisper is deployed and the
      pipeline runs end to end, but it has only been exercised on synthesised
      speech. Quality on real Kazakh is **unmeasured**.
- [x] Security regression suite running against **PostgreSQL**, not SQLite —
      1032 tests, 0 skipped, with `TEST_POSTGRES_URL` set
- [ ] Load testing
- [ ] Real Tree/Person/Story/Ask or honest "not ready" states — `/ask` is still
      the one demonstration surface and must keep saying so
- [ ] Intentional mobile / tablet / desktop layouts

Do not describe MURA as production-ready while these are open.

## 17b. Deployment `[V-RUNTIME]`

MURA is deployed and publicly reachable.

| | |
| --- | --- |
| App | https://mura-rho.vercel.app — Vercel, project root `MURA-app` |
| Core API + worker | https://mura-api-production.up.railway.app — Railway, one container |
| PostgreSQL + Auth | Supabase, region eu-central-1 |

Core reaches PostgreSQL through Supabase's **session pooler**
(`aws-0-eu-central-1...:5432`). The direct `db.<ref>.supabase.co` host is IPv6-only
and unreachable from Railway.

The API and the worker ship as one image and differ only in entrypoint, so they
cannot drift apart between deploys. Migrations run at container start; Alembic
owns the schema and the worker never creates tables.

Verified against the live deployment: a Supabase token authenticates to Core and
mints an internal user; a second account receives `404` on the first account's
family, indistinguishable from a family that does not exist; and a recording
uploads, transcribes, extracts a person and materialises a story.

## 18. Non-goals & forbidden shortcuts

**Never fake:** live ASR status, successful AI processing, family facts,
relationships, book generation, grounded Ask answers, language detection, provider
support, upload success, a completed job, or an authenticated family. *A beautiful,
honest "not ready yet" is always preferable to a false success.*

**Never reintroduce:** `MURA_CORE_API_KEY` in the frontend · JWT in
localStorage/sessionStorage · browser-supplied `Authorization` passthrough · fake auth
· `TRANSITIONAL_FAMILY_ID` / `family_mura_app` / any hardcoded or localStorage-derived
family scope · User→Person implicit mapping · family BOLA · wildcard CORS ·
auto schema creation in production · service routes on the browser proxy · the Alina/
Ariana assistant voice.

**No architecture fashion.** Do not propose rewriting the backend in Node, replacing
PostgreSQL with Firebase, swapping durable jobs for Celery, replacing Next.js or
Clerk, adding Redux, or splitting into microservices. The current architecture
reflects real, deliberate engineering investment.

## 19. Validation strategy

| Cost | Command | Notes |
| --- | --- | --- |
| Cheap | `npx vitest run` (frontend) | **203 tests / 19 files, all passing, ~2.5s** `[V-RUNTIME]` |
| Cheap | targeted `pytest` security modules | all pass `[V-RUNTIME]` |
| **Required** | `export TEST_POSTGRES_URL=...` before any authorization work | without it the five PostgreSQL-gated modules skip silently and green means nothing `[V-RUNTIME]` |
| Moderate | full `pytest` with `TEST_POSTGRES_URL` | **938 tests, 0 failures, 0 skips** `[V-RUNTIME]` |
| Cheap | `npm run lint`, `ruff`, `mypy` | targeted |
| Moderate | `ruff check` · `ruff format --check` · `mypy src apps` | all clean (113 source files) `[V-RUNTIME]` |
| Expensive | `npm run build` | passes; **run it before declaring frontend work done** — its lint stage catches what `tsc` and Vitest do not `[V-RUNTIME]` |
| Browser | Claude-in-Chrome (authenticated journeys) / Glance (visual, a11y, console, network) | required for UI changes |

Reuse `MURA-app/node_modules` and `Mura_project/.venv`. Never reinstall or recreate
them. Glance's viewport is fixed at 1440×900 in `.mcp.json`; changing viewport
requires editing that file and restarting the MCP server.

## 20. Repository & ref map `[V]`

**Frontend** — `D:\Mura_production\MURA-app` · `github.com/L4RBIX/MURA-app`
- `main` @ **`0dbdfe0`** after PR-05. PR-06 lands on
  `feat/real-family-archive-cutover` (`8fdf6ac`).
- Milestone commits: PR-DEBUG-01 `5010e6c`, `e14eb4d` · PR-05 `b429394`, `ccd3bd6`,
  `8a64947`, `0dbdfe0` · PR-06 `8fdf6ac` (archive cutover)
- Other local branches: `feat/authenticated-family-session`,
  `feat/canonical-core-api-client`
- Working tree: **clean**

**Backend** — `D:\Mura_production\Mura_project` · `github.com/erbo-dev/Mura_project`
- `production/core-v1` @ **`ec514dc`** after PR-DEBUG-01. PR-06 lands on
  `feat/real-family-archive-cutover` (`1b20d2f` archive read models and family APIs,
  `3cf9c79` development seed).
- **No migration was required for PR-06.** People, the evidence-gated relationship
  graph, stories, events, questions and conflicts were all already persisted; what was
  missing was a product-shaped way to read them.
- **`feat/replicate-gigaam-asr` @ `0335167`** — still **unpromoted**, now 3 commits:
  `592f687` → `989f820` → `0335167` (provider-neutral capabilities + conditional
  Kaggle credential). It branches from the **old** `ea310f9`, so it will need a rebase
  onto `ec514dc` at cutover.
- Recovery branches present and preserved: `recovery/mura-core-integrated`,
  `recovery/mura-core-longform`
- ~40 remote `agent/*`, `feat/*`, `fix/*` branches from earlier ML work
- Working tree: **clean**

Do not promote PR-04, delete branches, reset, or push without an explicit decision.
