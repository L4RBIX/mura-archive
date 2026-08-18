# Mura Core v1.0 RC testing

This guide provides three progressively deeper checks. Start with Level 1. It needs no Docker, GPU, Kaggle session, DeepSeek key, or PostgreSQL server.

## Level 1 — one-command offline smoke test

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
mura-release-smoke --json-output release-smoke.json
```

### macOS or Linux

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
mura-release-smoke --json-output release-smoke.json
```

The command exits with code `0` only when every release check passes. The JSON report must contain:

```json
{
  "release_id": "mura-core-v1.0.0-rc1",
  "passed": true,
  "checks": {
    "job_completed": true,
    "budget_passed": true,
    "trace_available": true,
    "replay_passed": true,
    "rollback_requires_restart": true,
    "release_restored": true,
    "retention_preview_found_data": true,
    "retention_deleted_data": true
  }
}
```

This smoke test creates a temporary SQLite database and synthetic recording. It validates the release-control path without touching a real family archive.

## Level 2 — full deterministic quality suite

```powershell
ruff check .
ruff format --check .
mypy src/mura apps services scripts
pytest -ra
mura-evaluate-core `
  --manifest benchmarks/release_manifest.json `
  --release-gates benchmarks/release_gates.json `
  --json-output benchmark-report.json `
  --markdown-output benchmark-report.md
```

On macOS or Linux, replace PowerShell backticks with backslashes.

This level verifies the domain contracts, linguistic rules, coreference, entity resolution, archive materialization, conflict handling, replay, release control, retention, and benchmark release gates. It still does not call GigaAM or DeepSeek.

## Level 3 — PostgreSQL migration and atomicity check

Start a disposable PostgreSQL container:

```powershell
docker run --name mura-postgres-rc `
  -e POSTGRES_USER=postgres `
  -e POSTGRES_PASSWORD=mura_test `
  -e POSTGRES_DB=mura_test `
  -p 5432:5432 `
  -d postgres:17.5-alpine3.22
```

Set the test database URLs and apply every migration:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres:mura_test@localhost:5432/mura_test"
$env:TEST_POSTGRES_URL = $env:DATABASE_URL
alembic upgrade head
pytest tests/test_postgres_atomicity.py -q
```

Clean up afterward:

```powershell
docker rm -f mura-postgres-rc
```

The PostgreSQL test verifies that archive state, pipeline result, job completion, trace events, and budget metadata commit or roll back together.

## Optional protected API checks

After starting the Core API, use the same bearer token configured as `CORE_API_KEY`.

```http
GET  /v1/operations/release
POST /v1/operations/release/rollback
POST /v1/operations/release/activate
POST /v1/families/{family_id}/replays
GET  /v1/families/{family_id}/replays
GET  /v1/operations/retention
POST /v1/operations/retention/apply
```

Rollback changes the desired release and writes an audit decision. It does not hot-swap Python code inside the current process. When the selected release differs from the running release, the response sets `restart_required=true`.

Retention is preview-first and requires the exact confirmation string:

```text
DELETE_EXPIRED_OPERATIONAL_DATA
```

It deletes only expired operational trace events and replay reports. Recordings, audio paths, transcripts, pipeline results, people, claims, conflicts, human decisions, graph edges, profiles, and release audit records are preserved.

## What this RC does not prove

The offline smoke test and deterministic benchmark do not measure live GigaAM accuracy, live DeepSeek variability, Cloudflare tunnel reliability, or production traffic latency. Those require a separate real-audio end-to-end run with the external services enabled.
