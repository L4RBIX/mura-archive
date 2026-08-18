from __future__ import annotations

from typing import Any

from mura.domain.models import ExtractionResult, TranscriptEnvelope
from mura.relationship_evidence import analyze_relationship_evidence

_ACCEPTED_COUNTERS = {
    "speaker_anchor": "speaker_anchor_accepted",
    "named_possessor": "named_possessor_accepted",
    "explicit_spouse": "explicit_spouse_accepted",
    "explicit_parent_child": "explicit_parent_child_accepted",
    "explicit_sibling": "explicit_sibling_accepted",
}


def relationship_grounding_counters(
    *,
    result: ExtractionResult,
    transcript: TranscriptEnvelope,
    extraction_issues: list[dict[str, Any]],
) -> dict[str, int]:
    """Compute deterministic aggregate counters without mutating the service class or result."""

    counters = {
        "speaker_anchor_accepted": 0,
        "named_possessor_accepted": 0,
        "explicit_spouse_accepted": 0,
        "explicit_parent_child_accepted": 0,
        "explicit_sibling_accepted": 0,
        "ambiguous_grounding_rejected": 0,
        "conflict_linked_preserved": 0,
    }
    for relationship in result.relationship_claims:
        analysis = analyze_relationship_evidence(
            relationship=relationship,
            transcript=transcript,
            people=result.people_mentions,
            speaker_name=result.speaker_name,
        )
        if (
            relationship.conflict_ids
            and analysis.grounding_decision == "insufficient_deterministic_signal"
        ):
            counters["conflict_linked_preserved"] += 1
            continue
        if not analysis.auto_accept_eligible:
            continue
        counter = _ACCEPTED_COUNTERS.get(analysis.grounding_decision)
        if counter is not None:
            counters[counter] += 1

    rejected_ids = {
        issue.get("object_id")
        for issue in extraction_issues
        if issue.get("object_type") == "relationship"
        and issue.get("code") == "relationship_grounding_rejected"
        and isinstance(issue.get("object_id"), str)
    }
    counters["ambiguous_grounding_rejected"] = len(rejected_ids)
    return counters
