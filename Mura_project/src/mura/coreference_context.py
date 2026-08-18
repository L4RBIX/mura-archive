from __future__ import annotations

from dataclasses import dataclass

from mura.coreference_boundaries import quote_scope_for_span
from mura.coreference_language import (
    AnaphorOccurrence,
    KinshipOccurrence,
    find_anaphors,
    nearest_kinship,
)
from mura.coreference_units import (
    TextUnit,
    candidate_context_unit,
    candidate_ids,
    context_units,
    ordered_units,
    person_occurrences,
    target_ids,
    unit_index_for_anaphor,
)
from mura.domain.models import GrammaticalNumber, PersonMention, TranscriptEnvelope
from mura.explicit_pair_grounding import find_explicit_pair_matches


@dataclass(frozen=True)
class BoundedCoreferenceContext:
    segment_id: str
    anaphor: AnaphorOccurrence
    kinship: KinshipOccurrence
    candidate_ids: list[str]
    target_ids: list[str]
    candidate_context: TextUnit
    resolved: bool


def _is_explicit_pair(
    *,
    candidates: list[str],
    candidate_context: TextUnit,
    people_by_id: dict[str, PersonMention],
) -> bool:
    if len(candidates) != 2:
        return False
    endpoint_people = [people_by_id[item] for item in candidates if item in people_by_id]
    return len(endpoint_people) == 2 and bool(
        find_explicit_pair_matches(candidate_context.text, endpoint_people)
    )


def bounded_coreference_contexts(
    *,
    people: list[PersonMention],
    transcript: TranscriptEnvelope,
) -> list[BoundedCoreferenceContext]:
    units = ordered_units(transcript)
    people_by_id = {person.mention_id: person for person in people}
    segment_text_by_id = {segment.segment_id: segment.text for segment in transcript.segments}
    occurrences_by_segment = {
        segment.segment_id: person_occurrences(
            segment.text,
            people,
            segment_id=segment.segment_id,
        )
        for segment in transcript.segments
    }
    contexts: list[BoundedCoreferenceContext] = []
    for segment in transcript.segments:
        occurrences = occurrences_by_segment[segment.segment_id]
        for anaphor in find_anaphors(segment.text):
            unit_index = unit_index_for_anaphor(
                units,
                segment_id=segment.segment_id,
                anaphor=anaphor,
            )
            if unit_index is None:
                continue
            current_unit = units[unit_index]
            kinship = nearest_kinship(segment.text, anaphor)
            if kinship is None or not (
                current_unit.start <= kinship.start and kinship.end <= current_unit.end
            ):
                continue
            anaphor_scope = quote_scope_for_span(segment.text, anaphor.start, anaphor.end)
            kinship_scope = quote_scope_for_span(segment.text, kinship.start, kinship.end)
            if (
                anaphor_scope.scope_id != "outside"
                or anaphor_scope.malformed
                or kinship_scope.scope_id != anaphor_scope.scope_id
                or kinship_scope.malformed
            ):
                continue
            targets = target_ids(
                occurrences,
                kinship_end=kinship.end,
                unit_end=current_unit.end,
                quote_scope=anaphor_scope.scope_id,
            )
            selected_units = context_units(units, current_index=unit_index)
            candidates = candidate_ids(
                selected_units=selected_units,
                current_unit=current_unit,
                anaphor=anaphor,
                excluded_ids=set(targets),
                occurrences_by_segment=occurrences_by_segment,
                segment_text_by_id=segment_text_by_id,
            )
            if not candidates:
                continue
            candidate_context = candidate_context_unit(
                selected_units=selected_units,
                candidates=candidates,
                occurrences_by_segment=occurrences_by_segment,
            )
            if candidate_context is None:
                continue
            resolved = (
                len(candidates) == 1
                if anaphor.grammatical_number is GrammaticalNumber.SINGULAR
                else _is_explicit_pair(
                    candidates=candidates,
                    candidate_context=candidate_context,
                    people_by_id=people_by_id,
                )
            )
            contexts.append(
                BoundedCoreferenceContext(
                    segment_id=segment.segment_id,
                    anaphor=anaphor,
                    kinship=kinship,
                    candidate_ids=candidates,
                    target_ids=targets,
                    candidate_context=candidate_context,
                    resolved=resolved,
                )
            )
    return contexts
