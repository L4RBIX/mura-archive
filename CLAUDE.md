# MURA — project instructions

Full verified context: **`docs/MURA_PRODUCT_BIBLE.md`**. Read it before product,
architecture or security work. This file is only what is needed every session.

## What MURA is

A family-memory preservation product. Spoken family stories become a durable,
explorable, **evidence-grounded** archive: recording → transcript → evidence → claims
→ people/relationships/events → tree, stories, review, and eventually a family book.

The user's mental model is «Я просто разговариваю с бабушкой.» Complexity stays
underneath. Users must never need to know what a claim, a lease, an entity resolver or
a confidence score is. Primary languages: **Russian and Kazakh**, including
code-switching.

## Repositories

| | Path | Canonical ref |
| --- | --- | --- |
| Frontend | `D:\Mura_production\MURA-app` | `main` @ `e14eb4d` |
| Backend | `D:\Mura_production\Mura_project` | `production/core-v1` @ `ec514dc` |

⚠️ **`feat/replicate-gigaam-asr` @ `0335167`** is the **unpromoted** PR-04
Replicate/GigaAM branch. It still branches from the older `ea310f9`, so it needs a
rebase onto `ec514dc` at cutover. Replicate stays unvalidated and is not the default.
Know which tree you are reading. Do not promote, merge, reset, delete branches, or push
without an explicit decision from the user.

Neither canonical branch is pushed: `main` is 18 ahead of `origin/main`,
`production/core-v1` is 1 ahead of its remote.

Frontend: Next.js 15 App Router, React 19, TypeScript, Tailwind 4, Framer Motion,
Clerk, Vitest.
Backend: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, PostgreSQL, Alembic, PyJWT.
Two processes: `apps/api` (submits/reads jobs) and `apps/worker` (claims/executes
them). The API must never process jobs itself.

## Resource policy (this is a personal machine — keep I/O low)

- **Reuse** `MURA-app/node_modules` and `Mura_project/.venv`. Never `npm install`,
  `npm ci`, `pip install`, or recreate `node_modules` / `.venv`.
- Preserve `.next/cache` and all other caches. Never clean caches as routine
  troubleshooting.
- Prefer targeted tests over full suites while iterating. Full `pytest` / `npm run
  build` only at a real verification checkpoint.
- No Docker builds/pulls, no lockfile regeneration, no `git clean -fdx`, no mass
  reformatting, no large recursive scans. Exclude `.git`, `node_modules`, `.next`,
  `.venv`, `dist`, `build`.
- Don't leave duplicate dev servers or watchers running. Stop what you start.
- Ask before generating/downloading anything over ~250 MB.

## Absolutely no local ML

Never download or run **GigaAM** locally. No Cog build, no `cog push`, no multi-GB
weights, no CUDA stack, no Hugging Face/pyannote/torch model downloads, no Common
Voice corpus, no local inference. GigaAM deployment is **remote (Replicate)** only.
Do not make live DeepSeek calls casually, and never send real family content to an
external service during testing.

## Security invariants — never weaken

- **No `MURA_CORE_API_KEY` in the frontend.** It has no service-internal consumer.
- **No JWT in `localStorage`/`sessionStorage`.** The bearer token exists only
  server-side; the proxy discards any client-supplied `Authorization` header.
- The Core proxy (`src/app/api/mura/[...path]/proxy.ts`) is a **strict allowlist**.
  Never expose `operations/*`, `workers/*`, `jobs/{id}/trace`, `replays`, or
  `process-transcript` to the browser.
- JWT verification: **RS256 only**, verify `iss`/`aud`/`exp`/`nbf`/`sub`, JWKS URL from
  server config only. Never fall back to `CORE_API_KEY` for user auth.
- Authorization is MURA's, not Clerk's:
  `bearer → Principal → User → FamilyMembership → Capability`. Membership is read from
  PostgreSQL per request; never bake family/role/person into a token.
- **BOLA:** `404` for both "not your family" and "no such family". `403` only for a
  confirmed member lacking a capability. `401` only for no usable identity.
- Keep `CORE_API_KEY` / `OPERATIONS_API_KEY` / `WORKER_REGISTRATION_TOKEN` separate.
- **User ≠ Person.** Never map an account to `person_id` / `speaker_person_id`.
- No hardcoded family scope. `TRANSITIONAL_FAMILY_ID` and `family_mura_app` are gone —
  never restore them. Family scope comes from the server's authorized list; a
  remembered family id is a UI preference, never authorization.
- Local recordings are owner-scoped; sign-out purges only the departing account's data
  plus legacy unowned data, never another account's namespace, never server data.
- Never print tokens, API keys, `DATABASE_URL`, or full private transcripts.
- Keep MURA **silent**: no TTS, no Alina/Ariana, no autoplay speech. Mic *recording* is
  separate and stays.

## Truthfulness — the product rule

Never fake: ASR status, successful processing, family facts, relationships, grounded
Ask answers, language detection, provider support, upload success, a completed job, or
an authenticated family. **An honest "not ready yet" always beats a false success.**

Every surface is REAL, DEMO, HYBRID, or MISSING-BACKEND — know which before you touch
it. After PR-06 nearly everything is **REAL**: home, record, processing, settings, auth,
tree, person, stories, story and review all read Core. **`/ask` is the only
demonstration left** and must keep saying so. The fixture family (`src/data`) is
deleted; `i18n.tsx` is localisation only. `src/lib/demo-boundary.test.ts` enforces that
real screens cannot import fixtures — keep it passing.

**Identity is an id.** Address people by canonical `person_id`. Never join people or
stories by name: two relatives share a name, one relative has several across Russian and
Kazakh spelling, and a string comparison silently merges different people.

Distinguish **bug** vs **missing feature** vs **demo feature** vs **external infra
pending**. Replicate being unconfigured is not a bug.

## Validation discipline

- Frontend cheap: `npx vitest run` (203 tests, ~2.5s), then `npx tsc --noEmit`.
- Before declaring frontend work done, run `npm run build` once: its lint stage
  catches things `tsc` and Vitest do not.
- Backend full: `pytest` = **938 tests, 0 failures, 0 skips** — but only with
  `TEST_POSTGRES_URL` exported. ⚠️ Without it, five PostgreSQL-gated modules skip
  silently and green means nothing. Export it before touching authorization.
- `DATABASE_URL` and `TEST_POSTGRES_URL` live at **User** environment scope (both point
  at the disposable `mura_leases_test`). They are deliberately **not** in `.env` — do
  not write credentials into repository files. A shell that did not inherit them will
  make Core look broken; load them from User scope instead.
- For meaningful **UI behaviour or visual changes**, code + tests are not enough —
  verify in a browser. Claude-in-Chrome for authenticated journeys; Glance for
  systematic screenshots, a11y, console and network. Not required for non-UI backend
  changes.

## Working style

Modify surgically: small patches, no whole-file rewrites, no touching generated files,
no unrequested refactors. Inspect `git diff` before broad changes. Source of truth
order: **runtime > current code > tests/schema > git history > any prompt or doc,
including this one.** If a document disagrees with the code, say so — do not silently
bend the code to match the document.

Detailed rules: `.claude/rules/`.
