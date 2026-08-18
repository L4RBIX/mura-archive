# Evidence and Claim Model v2

## Purpose

Mura must not turn a fluent model answer directly into a family graph. A recording produces a set of source-linked claims. Those claims may be explicit, morphologically licensed, speaker-anchored, context-resolved, inferred, uncertain, or mutually conflicting.

`extraction-v2` separates five concerns that were previously compressed into `source_segment_ids` and a confidence score:

1. immutable evidence spans;
2. extracted claims;
3. provenance activities;
4. identity and coreference proposals;
5. conflict metadata.

The model follows the same broad separation used by W3C PROV between entities and the activities that generated or validated them. Evidence spans also follow the annotation pattern of attaching a structured body to a precise source target. Pipeline and schema versions are carried explicitly so a stored result can be replayed against the same contract.

## Trust boundary

The language model may propose:

- evidence spans;
- name variants;
- coreference links;
- claims;
- conflict sets.

It may not authoritatively declare:

- which model or prompt generated a claim;
- which pipeline version validated it;
- who the narrator was;
- that a claim was human-confirmed;
- that an unresolved conflict has a winner.

The backend replaces model-provided provenance activities with authoritative ASR, extractor, and sanitizer activities. Every accepted claim receives a `ClaimProvenance` record containing the recording, narrator, evidence IDs, generation activity, validation activity, and version set.

## Evidence spans

An `EvidenceSpan` is an immutable annotation over a raw transcript segment.

Required invariants:

- `segment_id` exists in the recording;
- `source_layer` is `raw_transcript` for claim evidence;
- `text` occurs exactly in the cited raw segment;
- optional character offsets reproduce exactly the same text;
- referenced mention IDs exist;
- the creating provenance activity exists.

When an older extractor candidate only supplies `source_segment_ids`, the sanitizer creates deterministic full-segment evidence spans. This compatibility bridge prevents legacy callers from losing data while ensuring every persisted v2 claim has evidence IDs.

## Evidence classes

| Class | Meaning | Automatic graph eligibility |
|---|---|---|
| `A_explicit` | Identities and claim are literally present in the cited text. | Yes |
| `B_morphologically_explicit` | A grammatical form licenses the identity or relation without discourse guessing. | Yes |
| `C_speaker_anchored` | First-person language deterministically refers to the supplied narrator. | Yes |
| `D_context_resolved` | One or more endpoints depend on a separately represented resolved coreference link. | No by default |
| `E_inferred` | Plausible interpretation not licensed by A–D. | No |
| `U_uncertain` | Incomplete, unclear, or competing support. | No |

Only A–C are locally grounded and eligible for automatic materialization. D is retained as a structured claim but requires the constrained discourse policy introduced in PR 17 or human review. E and U must not silently become family-graph edges.

The current relationship validator can retain a D-class relationship only when its missing endpoint is covered by an explicit resolved `CoreferenceLink` whose source segments are included in the relationship evidence. A bare pronoun or a model confidence score is not enough.

## Structured name variants

`NameVariant` replaces an undifferentiated alias string with a source-linked object:

- primary name;
- explicit alias;
- nickname or diminutive;
- patronymic or surname;
- married name;
- transliteration or script variant;
- ASR variant;
- inflected form;
- unknown variant.

Each variant stores its surface, deterministic normalized form, type, language/script hints, source segments, evidence IDs, confidence, and review state. The resolver may use these surfaces, but similarity alone still cannot merge two people.

The legacy `aliases` field remains temporarily for API compatibility. The sanitizer materializes supported primary and alias values into structured variants, and downstream matching reads both representations.

## Coreference links

A `CoreferenceLink` represents the anaphor separately from any relationship that depends on it.

Important fields:

- exact anaphor text and source segments;
- evidence IDs;
- status: resolved, ambiguous, unresolved, or rejected;
- method: explicit naming, speaker anchor, morphology, deterministic discourse, model proposal, or human review;
- grammatical number;
- selected antecedent IDs;
- candidate antecedent IDs;
- evidence class and rationale.

Validation rules include:

- resolved links require antecedents;
- singular resolved links require exactly one antecedent;
- ambiguous links require at least two candidates;
- unresolved, ambiguous, and rejected links cannot contain selected antecedents;
- every candidate and antecedent must refer to an existing mention;
- the anaphor must occur in the cited transcript evidence.

PR 14 introduces the contract, not the full discourse resolver. Deterministic antecedent selection remains the responsibility of PR 17.

## Conflicts

A `ConflictSet` groups incompatible claim references without destroying either claim.

An open conflict has:

- a conflict type;
- at least two unique claim references;
- optional evidence IDs;
- a detection method;
- a rationale;
- no preferred claim.

A preferred claim is legal only after the conflict is marked resolved, and a resolved conflict requires a resolution note. The sanitizer removes conflict sets that reference missing claims or evidence, then cross-links accepted conflict IDs back onto every participating claim.

This means a later correction, date disagreement, identity dispute, or competing kinship statement can be represented as evidence-bearing history rather than a destructive overwrite.

## Provenance activities

Each output contains authoritative activities for:

- ASR: model, revision, and chunker version;
- extraction: prompt version and pipeline version;
- sanitization: evidence-rule and domain-schema version.

Claims record which activity generated them and which activity validated them. `derived_from_claim_ids` is reserved for later deterministic materialization and correction workflows.

## Compatibility and migration

`ExtractionResult.schema_version` defaults to `extraction-v1` so old fixtures and direct constructors remain parseable. The sanitizer always emits `extraction-v2`.

Migration path:

1. parse the legacy candidate;
2. run existing object-level schema and semantic quarantine;
3. validate any model-proposed v2 evidence, coreference, and conflict objects;
4. generate fallback evidence where needed;
5. inject authoritative provenance;
6. materialize structured primary name variants;
7. validate the complete v2 contract.

This ordering preserves the PR 13 benchmark behavior. PR 14 changes observability and data integrity, not the Kazakh, Russian, English, or discourse acceptance rules scheduled for PRs 15–17.
