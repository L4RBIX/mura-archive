# Mura ML Core Baseline

Manifest: `benchmarks/manifest.json`

## Pipeline versions

| Component | Version |
|---|---|
| archive_schema | `archive-claim-ledger-v1+conflict-decisions-v1+generic-claims-v1` |
| asr_chunker | `silero-smart-v2-exact-overlap` |
| asr_evaluator | `asr-evaluator-v1-wer-cer-boundary` |
| asr_model | `gigaam-multilingual-large-ctc@ac7c6db08133f83478451a659f8470ee8ab47a2d` |
| asr_vad | `silero-vad-6.2.1` |
| benchmark_schema | `benchmark-v7-offline-e2e+asr-contract+identity-safety` |
| claim_semantics | `claim-semantics-v1` |
| cleaner_prompt | `cleaner-v3-self-correction-semantics` |
| domain_schema | `domain-v5-identity-safety` |
| evaluator | `core-evaluator-v7-offline-e2e-release` |
| evidence_rules | `claim-evidence-v5-ordered-factual-support+bounded-coreference-v3` |
| extraction_orchestration | `focused-extraction-v1-three-pass` |
| extractor_prompt | `extractor-v6-focused-passes` |
| extractor_repair_prompt | `extractor-repair-v4-focused-pass` |
| long_form_executor | `long-form-executor-v1-single-pass-partial` |
| long_form_merge | `long-form-merge-v1` |
| long_form_planner | `long-form-planner-v1` |
| long_form_registry | `recording-mention-registry-v1-conservative` |
| long_form_window_policy | `long-form-window-policy-v1` |
| materializer | `family-materializer-v4-active-state-guard` |
| narrative_rules | `event-story-grounding-v1` |
| pipeline | `mura-core-v0.15.0` |
| relationship_state_rules | `relationship-state-v1` |
| resolver | `mention-resolver-v3-collision-safe` |
| temporal_rules | `temporal-normalizer-v1` |

## Aggregate metrics

- Cases: **6**
- Person mentions: P=1.000, R=1.000, F1=1.000 (TP=14, FP=0, FN=0)
- Relationships: P=1.000, R=1.000, F1=1.000 (TP=6, FP=0, FN=0)
- Expected relationship quarantine: P=1.000, R=1.000, F1=1.000 (TP=1, FP=0, FN=0)
- Expected object quarantine: P=1.000, R=1.000, F1=1.000 (TP=1, FP=0, FN=0)
- Relationship direction accuracy: 1.000 (6/6)
- Provenance completeness: 1.000 (20/20)
- Events: P=1.000, R=1.000, F1=1.000 (TP=0, FP=0, FN=0)
- Descriptions: P=1.000, R=1.000, F1=1.000 (TP=0, FP=0, FN=0)
- Stories: P=1.000, R=1.000, F1=1.000 (TP=0, FP=0, FN=0)
- Event participant accuracy: 1.000 (0/0)
- Narrative factual support: 1.000 (0/0)
- Sensitive story recall: 1.000 (0/0)
- Unsupported event statements: **0**
- Unsupported story statements: **0**
- Sensitivity underclassifications: **0**
- Duplicate semantic events: **0**
- Duplicate semantic stories: **0**
- Unknown segment references: **0**
- Self relationships: **0**
- Provenance violations: **0**
- Objects without evidence: **0**
- Invalid evidence spans: **0**
- Unsafe verification statuses: **0**
- Unsafe story privacy: **0**
- Unknown issue codes: **0**
- Missing required issue codes: **0**
- Fatal contract failures: **0**

## Cases

| Case | Language | Relationships | Quarantine | Accepted | Quarantined |
|---|---|---|---|---|---|
| kk_speaker_anchored_parent | kk | 1.000 | 1.000 | relationship_001 | — |
| kk_named_possessor_spouse | kk | 1.000 | 1.000 | relationship_001 | — |
| ru_inflected_speaker_anchor | ru | 1.000 | 1.000 | relationship_001 | — |
| ru_ambiguous_third_person | ru | 1.000 | 1.000 | — | relationship_001 |
| kk_plural_antecedent_children | kk | 1.000 | 1.000 | relationship_001, relationship_002 | — |
| en_explicit_possessive_spouse | en | 1.000 | 1.000 | relationship_001 | — |

## Interpretation

This report measures the deterministic validation layer against fixed extraction candidates. It does not measure live DeepSeek candidate generation or ASR quality.
