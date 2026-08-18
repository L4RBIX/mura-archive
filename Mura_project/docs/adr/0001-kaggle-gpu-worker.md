# ADR 0001: Use Kaggle as a temporary GigaAM worker

- Status: accepted for hackathon MVP
- Date: 2026-07-17

## Context

GigaAM Multilingual `large_ctc` performs strongly on the target Kazakh/Russian speech but requires a GPU. The team already has access to Kaggle T4 sessions and has validated the model there.

## Decision

Run GigaAM inside an authenticated FastAPI service in Kaggle and expose it through a Cloudflare Quick Tunnel. Keep DeepSeek, validation, entity resolution, and persistence in a separate CPU-friendly core API.

## Consequences

Positive:

- no immediate paid GPU hosting;
- one ASR contract for Kaggle and a future GPU host;
- live demo using the validated model.

Negative:

- Quick Tunnel URL changes after restart;
- session and GPU quotas can stop the worker;
- not suitable for 24/7 availability.

Mitigation:

- worker registers its current URL with the core API;
- audio can be queued by the future persistence layer;
- demo includes a preprocessed fallback recording.
