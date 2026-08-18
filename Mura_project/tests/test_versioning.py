from mura.versioning import CURRENT_PIPELINE_VERSIONS, get_pipeline_versions


def test_pipeline_versions_are_explicit_and_copy_safe() -> None:
    versions = get_pipeline_versions()

    assert versions.pipeline == "mura-core-v0.15.0"
    assert versions.domain_schema == "domain-v5-identity-safety"
    assert versions.cleaner_prompt == "cleaner-v3-self-correction-semantics"
    assert versions.extractor_prompt == "extractor-v6-focused-passes"
    assert versions.extractor_repair_prompt == "extractor-repair-v4-focused-pass"
    assert (
        versions.evidence_rules
        == "claim-evidence-v5-ordered-factual-support+bounded-coreference-v3"
    )
    assert versions.extraction_orchestration == "focused-extraction-v1-three-pass"
    assert versions.narrative_rules == "event-story-grounding-v1"
    assert versions.claim_semantics == "claim-semantics-v1"
    assert versions.temporal_rules == "temporal-normalizer-v1"
    assert versions.relationship_state_rules == "relationship-state-v1"
    assert versions.resolver == "mention-resolver-v3-collision-safe"
    assert (
        versions.archive_schema == "archive-claim-ledger-v1+conflict-decisions-v1+generic-claims-v1"
    )
    assert versions.materializer == "family-materializer-v4-active-state-guard"
    assert versions.evaluator == "core-evaluator-v7-offline-e2e-release"
    assert versions.benchmark_schema == "benchmark-v7-offline-e2e+asr-contract+identity-safety"
    assert (
        versions.asr_model
        == "gigaam-multilingual-large-ctc@ac7c6db08133f83478451a659f8470ee8ab47a2d"
    )
    assert versions.asr_vad == "silero-vad-6.2.1"
    assert versions.asr_chunker == "silero-smart-v2-exact-overlap"
    assert versions.asr_evaluator == "asr-evaluator-v1-wer-cer-boundary"
    assert versions.long_form_planner == "long-form-planner-v1"
    assert versions.long_form_window_policy == "long-form-window-policy-v1"
    assert versions.long_form_executor == "long-form-executor-v1-single-pass-partial"
    assert versions.long_form_merge == "long-form-merge-v1"
    assert versions.long_form_registry == "recording-mention-registry-v1-conservative"
    assert versions is not CURRENT_PIPELINE_VERSIONS
