# Mura ML release evaluation

Mura has two separate release decisions. They must not be collapsed into one green badge.

## Level A: deterministic offline release candidate

Run:

```bash
mura-evaluate-ml-release \
  --manifest benchmarks/release/ml_release_manifest.json \
  --json-output ml-release-report.json \
  --markdown-output ml-release-report.md
```

This composite gate executes and preserves the independent reports for:

- deterministic extraction and provenance safety;
- bounded coreference and entity-resolution safety;
- frozen-hypothesis ASR accounting and chunk-boundary behavior;
- the real cleaner, focused extraction, sanitizer, provenance, coreference, and resolver orchestration with frozen external provider responses.

A pass means the commit is an **offline release candidate**. It does not measure live GigaAM accuracy, DeepSeek variability, GPU performance, provider latency, or real-family-corpus quality.

## Level B: controlled live promotion gate

The live workflow is manual and must run on an approved self-hosted GPU runner:

```bash
mura-evaluate-e2e-live \
  --manifest /approved/dataset/e2e-live-manifest.json \
  --release-gates benchmarks/e2e_live_release_gates.json \
  --json-output e2e-live-report.json \
  --markdown-output e2e-live-report.md \
  --device cuda:0
```

The manifest must contain at least 12 approved cases: at least four Russian, four Kazakh, and four mixed-speech recordings. Every file must have public-license or explicit-consent metadata and must be referenced by a relative path inside the manifest directory.

The live report stores aggregate metrics and technical metadata, not source audio, transcripts, extracted family text, names, or evidence spans. It records the source commit, pinned ASR identity and artifact digests, provider model identifiers, latency, token usage, and safety metrics.

Production promotion requires both:

1. the offline composite gate to pass for the exact source commit;
2. the live gate to pass for that same commit and approved dataset.

A live result from another commit is not transferable. A missing dataset, unknown model revision, missing artifact digest, malformed report, absent language group, or insufficient case count fails closed.

## Current limits

The repository provides the evaluation mechanism, not an approved private corpus. Thresholds must be revisited when a sufficiently large consented corpus exists. Perfect results on synthetic fixtures are regression evidence, not a claim of production accuracy.
