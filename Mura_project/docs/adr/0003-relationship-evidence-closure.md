# ADR 0003: Deterministic relationship evidence closure

## Status

Accepted.

## Context

A relationship can be expressed with a pronoun in one segment while the person's canonical
name is established in an earlier segment. DeepSeek occasionally returns the correct endpoint
IDs and relationship roles but cites only the kinship segment. Strict validation then rejects
the claim because one endpoint mention has no source overlap.

Example:

- `seg_001`: `Әкемнің аты Сапар.`
- `seg_002`: `Оның інісі Нұрғали еді.`

The sibling claim may correctly connect Сапар and Нұрғали while citing only `seg_002`.

## Decision

Before semantic validation, Mura completes each relationship's evidence bundle when an
endpoint has no overlap with the relationship evidence:

1. Keep every source segment returned by the extractor.
2. Add that endpoint mention's existing `source_segment_ids`.
3. De-duplicate and order the result by transcript order.
4. Run the unchanged strict semantic validator.

The completion step does not alter endpoint IDs, relationship type, roles, confidence,
assertion mode, or verification status. Unknown endpoint IDs are not repaired and remain a
validation failure.

## Consequences

- Pronoun-based relationships no longer require another paid LLM repair call merely to copy
  an already-known identity segment.
- The returned claim remains fully source-linked.
- Structural and semantic errors are still rejected.
- The processing metadata reports how many relationships required evidence closure.
