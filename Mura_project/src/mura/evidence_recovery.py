from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeGuard

from mura.domain.models import CleanerResult, EvidenceSourceLayer, TranscriptEnvelope


@dataclass(frozen=True)
class EvidenceOffsetRecoveryMetrics:
    already_valid: int = 0
    recovered: int = 0
    ambiguous: int = 0
    missing: int = 0
    wrong_source_layer: int = 0
    unknown_segment: int = 0
    invalid_text: int = 0
    unrecoverable: int = 0
    quarantined_evidence_ids: frozenset[str] = field(default_factory=frozenset, repr=False)
    quarantine_reasons: tuple[tuple[str, str], ...] = field(default_factory=tuple, repr=False)

    @property
    def repaired_evidence_offsets(self) -> int:
        return self.recovered

    def to_dict(self) -> dict[str, int]:
        # New counters are canonical. Legacy integer aliases remain migration-free for dashboards.
        return {
            "already_valid": self.already_valid,
            "recovered": self.recovered,
            "ambiguous": self.ambiguous,
            "missing": self.missing,
            "wrong_source_layer": self.wrong_source_layer,
            "unknown_segment": self.unknown_segment,
            "invalid_text": self.invalid_text,
            "unrecoverable": self.unrecoverable,
            "repaired_evidence_offsets": self.recovered,
            "exact_offsets_accepted": self.already_valid,
            "unique_match_repaired": self.recovered,
            "nearest_match_repaired": 0,
            "ambiguous_offsets_removed": self.ambiguous,
            "missing_text_quarantined": self.missing,
            "unknown_segment_quarantined": self.unknown_segment,
            "non_raw_evidence_skipped": 0,
        }


def _all_occurrences(text: str, substring: str) -> list[int]:
    occurrences: list[int] = []
    cursor = 0
    while True:
        position = text.find(substring, cursor)
        if position < 0:
            return occurrences
        occurrences.append(position)
        cursor = position + 1


def _is_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _offsets_match(
    *,
    segment_text: str,
    evidence_text: str,
    start_char: object,
    end_char: object,
) -> bool:
    if not _is_integer(start_char) or not _is_integer(end_char):
        return False
    return (
        0 <= start_char < end_char <= len(segment_text)
        and end_char - start_char == len(evidence_text)
        and segment_text[start_char:end_char] == evidence_text
    )


def _candidate_id(candidate: dict[str, Any]) -> str | None:
    value = candidate.get("evidence_id")
    return value if isinstance(value, str) and value else None


def recover_evidence_offsets(
    *,
    raw: dict[str, Any],
    transcript: TranscriptEnvelope,
    cleaned: CleanerResult | None = None,
) -> tuple[dict[str, Any], EvidenceOffsetRecoveryMetrics]:
    """Recover only unique exact offsets inside the declared transcript source layer.

    The function never searches the full transcript, never normalizes, case-folds, translates,
    rewrites punctuation, or uses a proposed offset to choose between multiple occurrences.
    """

    raw_text_by_id = {segment.segment_id: segment.text for segment in transcript.segments}
    readable_text_by_id = (
        {segment.segment_id: segment.text for segment in cleaned.readable_segments}
        if cleaned is not None
        else {}
    )
    raw_evidence = raw.get("evidence_spans")
    if not isinstance(raw_evidence, list):
        return dict(raw), EvidenceOffsetRecoveryMetrics()

    counters = {
        "already_valid": 0,
        "recovered": 0,
        "ambiguous": 0,
        "missing": 0,
        "wrong_source_layer": 0,
        "unknown_segment": 0,
        "invalid_text": 0,
        "unrecoverable": 0,
    }
    quarantined_ids: set[str] = set()
    quarantine_reasons: dict[str, str] = {}
    recovered_evidence: list[object] = []

    def quarantine(evidence_id: str | None, reason: str) -> None:
        if evidence_id is None:
            return
        quarantined_ids.add(evidence_id)
        quarantine_reasons[evidence_id] = reason

    for candidate in raw_evidence:
        if not isinstance(candidate, dict):
            counters["unrecoverable"] += 1
            recovered_evidence.append(candidate)
            continue

        recovered_candidate = dict(candidate)
        evidence_id = _candidate_id(candidate)
        source_layer = candidate.get(
            "source_layer",
            EvidenceSourceLayer.RAW_TRANSCRIPT.value,
        )
        segment_id = candidate.get("segment_id")
        evidence_text = candidate.get("text")

        if not isinstance(segment_id, str) or segment_id not in raw_text_by_id:
            counters["unknown_segment"] += 1
            quarantine(evidence_id, "unknown_segment")
            recovered_evidence.append(recovered_candidate)
            continue
        if not isinstance(evidence_text, str) or not evidence_text:
            counters["invalid_text"] += 1
            quarantine(evidence_id, "invalid_text")
            recovered_evidence.append(recovered_candidate)
            continue

        declared_text: str | None
        opposite_text: str | None
        if source_layer == EvidenceSourceLayer.RAW_TRANSCRIPT.value:
            declared_text = raw_text_by_id[segment_id]
            opposite_text = readable_text_by_id.get(segment_id)
        elif source_layer == EvidenceSourceLayer.READABLE_TRANSCRIPT.value:
            declared_text = readable_text_by_id.get(segment_id)
            opposite_text = raw_text_by_id[segment_id]
        else:
            counters["unrecoverable"] += 1
            quarantine(evidence_id, "unrecoverable")
            recovered_evidence.append(recovered_candidate)
            continue

        if declared_text is None:
            counters["wrong_source_layer"] += 1
            quarantine(evidence_id, "wrong_source_layer")
            recovered_evidence.append(recovered_candidate)
            continue

        proposed_start = candidate.get("start_char")
        proposed_end = candidate.get("end_char")
        if _offsets_match(
            segment_text=declared_text,
            evidence_text=evidence_text,
            start_char=proposed_start,
            end_char=proposed_end,
        ):
            counters["already_valid"] += 1
            recovered_evidence.append(recovered_candidate)
            continue

        occurrences = _all_occurrences(declared_text, evidence_text)
        if not occurrences:
            if opposite_text is not None and evidence_text in opposite_text:
                counters["wrong_source_layer"] += 1
            else:
                counters["missing"] += 1
            quarantine(
                evidence_id,
                "wrong_source_layer"
                if opposite_text is not None and evidence_text in opposite_text
                else "missing",
            )
            recovered_evidence.append(recovered_candidate)
            continue

        if len(occurrences) == 1:
            start_char = occurrences[0]
            recovered_candidate["start_char"] = start_char
            recovered_candidate["end_char"] = start_char + len(evidence_text)
            counters["recovered"] += 1
            recovered_evidence.append(recovered_candidate)
            continue

        # Multiple exact occurrences with invalid or absent offsets are intentionally not guessed.
        recovered_candidate["start_char"] = None
        recovered_candidate["end_char"] = None
        counters["ambiguous"] += 1
        quarantine(evidence_id, "ambiguous")
        recovered_evidence.append(recovered_candidate)

    recovered_raw = dict(raw)
    recovered_raw["evidence_spans"] = recovered_evidence
    metrics = EvidenceOffsetRecoveryMetrics(
        **counters,
        quarantined_evidence_ids=frozenset(quarantined_ids),
        quarantine_reasons=tuple(sorted(quarantine_reasons.items())),
    )
    return recovered_raw, metrics
