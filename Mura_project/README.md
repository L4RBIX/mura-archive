# Mura · Мұра

> Family voices become a source-linked archive — in Kazakh, Russian, or both.

Mura accepts a family recording, preserves the original transcript, cleans it with DeepSeek, and extracts people, relationships, events, stories, and review questions. Every fact keeps a link to the exact transcript segment it came from.

## What is production-ready

- Russian, Kazakh, and mixed-language transcripts.
- A bounded long-form pipeline: deterministic windows, overlap, partial recovery, and a strict LLM-call budget.
- Stable global IDs and conservative person deduplication across windows.
- Evidence, reference, and semantic validation before anything reaches the archive.
- Durable PostgreSQL jobs, retryable Kaggle ASR, and explicit human-review items.
- Immutable raw ASR text; cleaned text is stored separately.

## Architecture

```text
Web / mobile client
        │
        ▼
FastAPI Core ── PostgreSQL jobs and results
        │
        ├── Kaggle GPU worker: FFmpeg → Silero VAD → GigaAM ASR
        │
        └── DeepSeek: faithful cleanup → structured extraction
                                      │
                                      ▼
                    validate → merge → resolve → review
```

Short transcripts use one extraction pass. Long transcripts are split into stable overlapping windows; each window can fail independently, successful results are merged with globally remapped IDs, and the final document is validated again. The planner targets 3–6 extraction windows for the checked-in 18-segment long-form fixture.

## Quick start

Requirements: Python 3.11+, PostgreSQL for a deployed environment, and a DeepSeek API key.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Set the required secrets in `.env`:

```dotenv
DEEPSEEK_API_KEY=sk-your-real-key
CORE_API_KEY=generate-an-independent-random-value
WORKER_REGISTRATION_TOKEN=generate-another-random-value
KAGGLE_ASR_API_KEY=generate-a-third-random-value
```

Then start the API:

```bash
alembic upgrade head
uvicorn apps.api.main:app --reload --port 8001
```

For a local hackathon run, `DATABASE_AUTO_CREATE=true` is convenient. Production should run migrations explicitly and set it to `false`. API docs are available at `http://localhost:8001/docs`.

## API flow

All application endpoints require `Authorization: Bearer <CORE_API_KEY>`.

```text
POST /v1/recordings                    upload audio, receive job_id
GET  /v1/jobs/{job_id}                 poll pipeline progress
GET  /v1/recordings/{recording_id}     read the completed archive result
GET  /v1/recordings/{id}/review-items  read ambiguous items only
```

Job states are `queued`, `transcribing`, `cleaning`, `extracting`, `resolving`, `completed`, and `failed`. If Kaggle is offline, the job remains queued at `waiting_for_asr` and resumes after worker registration.

## Kaggle ASR worker

1. Create a Kaggle notebook with a T4 GPU and Internet enabled.
2. Add `KAGGLE_ASR_API_KEY` and, if needed, `HF_TOKEN` as Kaggle secrets.
3. Set `CORE_BACKEND_URL` and `WORKER_REGISTRATION_TOKEN`.
4. Follow [`notebooks/KAGGLE.md`](notebooks/KAGGLE.md).

The tunnel URL is temporary; the Core API stores the latest registered worker URL in PostgreSQL.

## Quality gates

```bash
pytest
ruff check .
ruff format --check .
mypy src apps services scripts
python -m compileall -q src apps services scripts
```

The deterministic benchmark does not need a GPU or API key:

```bash
mura-evaluate-core \
  --manifest benchmarks/manifest.json \
  --json-output /tmp/mura-core-report.json \
  --markdown-output /tmp/mura-core-report.md
```

Frozen results live in [`docs/baselines/current_main.md`](docs/baselines/current_main.md). The mixed RU/KK long-form fixture is in [`benchmarks/long_form_mixed_ru_kk_v1.json`](benchmarks/long_form_mixed_ru_kk_v1.json).

## Repository map

```text
apps/api/                 FastAPI Core
services/kaggle_asr/      GPU ASR worker
src/mura/deepseek/        DeepSeek client, prompts, cleaner, extractor
src/mura/orchestration/   Recording and job orchestration
src/mura/storage/         SQLAlchemy models and repositories
src/mura/domain/          Stable Pydantic contracts
src/mura/evaluation/      Deterministic evaluation tools
benchmarks/               Versioned evaluation fixtures
migrations/               Alembic migrations
tests/                    Unit, integration, and contract tests
```

## Safety by design

- Secrets, model weights, audio, and runtime data are never committed.
- New stories are private by default.
- LLM confidence is never treated as human verification.
- Invalid isolated objects are quarantined instead of poisoning the result.
- Ambiguous identity matches stay separate and become review items.
