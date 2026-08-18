from __future__ import annotations

from mura.coreference import augment_bounded_coreference
from mura.domain.models import (
    ExtractionResult,
    PersonMention,
    RelationshipClaim,
    TranscriptEnvelope,
)
from mura.relationship_evidence import (
    contains_surface,
    has_first_person_reference,
    normalize_evidence,
    person_name_surfaces,
)


def _ordered_unique_segment_ids(
    segment_ids: list[str], transcript: TranscriptEnvelope
) -> list[str]:
    """Return unique IDs in transcript order, preserving unknown IDs at the end."""

    requested = set(segment_ids)
    ordered = [
        segment.segment_id for segment in transcript.segments if segment.segment_id in requested
    ]

    seen = set(ordered)
    for segment_id in segment_ids:
        if segment_id in seen:
            continue
        ordered.append(segment_id)
        seen.add(segment_id)
    return ordered


def _segment_text_by_id(transcript: TranscriptEnvelope) -> dict[str, str]:
    return {segment.segment_id: segment.text for segment in transcript.segments}


def _best_identity_segment(
    person: PersonMention,
    transcript: TranscriptEnvelope,
) -> str | None:
    text_by_id = _segment_text_by_id(transcript)
    surfaces = person_name_surfaces(person)
    for segment in transcript.segments:
        if segment.segment_id not in person.source_segment_ids:
            continue
        text = text_by_id[segment.segment_id]
        if any(contains_surface(text, surface) for surface in surfaces):
            return segment.segment_id
    return next(
        (segment_id for segment_id in person.source_segment_ids if segment_id in text_by_id),
        None,
    )


def _source_text(source_ids: list[str], transcript: TranscriptEnvelope) -> str:
    text_by_id = _segment_text_by_id(transcript)
    return " ".join(text_by_id[item] for item in source_ids if item in text_by_id)


def _is_speaker(person: PersonMention, speaker_name: str) -> bool:
    normalized_speaker = normalize_evidence(speaker_name)
    return any(
        normalize_evidence(surface) == normalized_speaker
        for surface in person_name_surfaces(person)
    )


def _complete_relationship(
    relationship: RelationshipClaim,
    *,
    people_by_id: dict[str, PersonMention],
    speaker_name: str,
    transcript: TranscriptEnvelope,
) -> tuple[RelationshipClaim, bool]:
    source_ids = list(relationship.source_segment_ids)
    source_set = set(source_ids)
    changed = False

    for mention_id in (
        relationship.subject_mention_id,
        relationship.object_mention_id,
    ):
        person = people_by_id.get(mention_id)
        if person is None:
            continue

        source_text = _source_text(source_ids, transcript)
        explicitly_named = any(
            contains_surface(source_text, surface) for surface in person_name_surfaces(person)
        )
        if explicitly_named:
            continue

        is_speaker = _is_speaker(person, speaker_name)
        speaker_referenced = is_speaker and has_first_person_reference(source_text)
        has_overlap = bool(source_set.intersection(person.source_segment_ids))
        if speaker_referenced and has_overlap:
            continue

        # Only the supplied speaker can be resolved from first-person forms. Third-person
        # endpoints require a trusted CoreferenceLink created by the bounded resolver.
        if not is_speaker:
            continue

        identity_segment = _best_identity_segment(person, transcript)
        if identity_segment is None or identity_segment in source_set:
            continue

        source_ids.append(identity_segment)
        source_set.add(identity_segment)
        changed = True

    if not changed:
        return relationship, False

    return relationship.model_copy(
        update={"source_segment_ids": _ordered_unique_segment_ids(source_ids, transcript)}
    ), True


def complete_relationship_evidence(
    result: ExtractionResult,
    transcript: TranscriptEnvelope,
) -> tuple[ExtractionResult, int]:
    """Complete only deterministic speaker and bounded discourse evidence.

    First-person forms may resolve to the supplied speaker. Third-person possessives are handled
    by the bounded resolver, which considers only the current segment and one preceding segment.
    A singular form requires one candidate; a plural form requires one explicit pair. Ambiguous
    links are retained for review but never authorize a relationship.
    """

    augmentation = augment_bounded_coreference(result, transcript)
    result = augmentation.result
    people_by_id = {person.mention_id: person for person in result.people_mentions}
    completed: list[RelationshipClaim] = []
    changed_count = augmentation.changed_relationship_count

    for relationship in result.relationship_claims:
        updated, changed = _complete_relationship(
            relationship,
            people_by_id=people_by_id,
            speaker_name=result.speaker_name,
            transcript=transcript,
        )
        completed.append(updated)
        changed_count += int(changed)

    if not any(
        updated is not original
        for updated, original in zip(completed, result.relationship_claims, strict=True)
    ):
        return result, changed_count

    return result.model_copy(update={"relationship_claims": completed}), changed_count
