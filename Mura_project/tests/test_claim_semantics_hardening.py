from __future__ import annotations

import pytest

from mura.claim_semantics import (
    add_temporal_conflicts,
    find_uncertainty_markers,
    harden_claim_semantics,
    infer_relationship_state,
    parse_temporal_expression,
    relationship_is_active_candidate,
)
from mura.domain.models import (
    AssertionMode,
    CleanerResult,
    CorrectionKind,
    DetectedCorrection,
    EpistemicStatus,
    EventDate,
    EvidenceSpan,
    ExtractionResult,
    FamilyEvent,
    PersonMention,
    ReadableSegment,
    RelationshipClaim,
    RelationshipRole,
    RelationshipState,
    RelationshipType,
    TemporalKind,
    TemporalPrecision,
    TranscriptEnvelope,
)
from mura.extraction_sanitizer import process_extraction_candidate


def _transcript(text: str) -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id="rec_semantics",
        duration_seconds=1.0,
        full_text=text,
        segments=[{"segment_id": "seg_1", "start": 0.0, "end": 1.0, "text": text}],
        asr_model="fixture",
        asr_revision="v1",
        chunker_version="v1",
    )


def _cleaned(text: str) -> CleanerResult:
    return CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_1", text=text)],
        full_readable_text=text,
    )


@pytest.mark.parametrize(
    ("text", "surface"),
    [
        ("Кажется, он родился в 1987 году.", "Кажется"),
        ("Шамасы, ол 1987 жылы туған.", "Шамасы"),
        ("Ол болуы мүмкін туыс.", "болуы мүмкін"),
    ],
)
def test_multilingual_uncertainty_markers(text: str, surface: str) -> None:
    assert surface in [item.surface for item in find_uncertainty_markers(text)]


def test_quoted_and_negated_uncertainty_are_not_claim_markers() -> None:
    assert find_uncertainty_markers("Он сказал: «кажется, это правда».") == []
    assert find_uncertainty_markers("Он не кажется больным.") == []
    assert find_uncertainty_markers("Без сомнения, он приехал.") == []


def test_uncertainty_is_local_to_second_clause() -> None:
    text = "Алия родилась в 1987 году, а переехала, кажется, в 2005 году."
    transcript = _transcript(text)
    result = ExtractionResult(
        recording_id=transcript.recording_id,
        speaker_id="speaker",
        speaker_name="Айжан",
        people_mentions=[
            PersonMention(
                mention_id="alia",
                name="Алия",
                source_segment_ids=["seg_1"],
                confidence=1.0,
            )
        ],
        events=[
            FamilyEvent(
                event_id="birth",
                event_type="birth",
                title="Алия родилась",
                participant_mention_ids=["alia"],
                date=EventDate(value="1987", original_expression="1987 году", precision="year"),
                description="Алия родилась в 1987 году",
                source_segment_ids=["seg_1"],
                confidence=1.0,
            ),
            FamilyEvent(
                event_id="move",
                event_type="move",
                title="Алия переехала",
                participant_mention_ids=["alia"],
                date=EventDate(value="2005", original_expression="в 2005 году", precision="year"),
                description="переехала в 2005 году",
                source_segment_ids=["seg_1"],
                confidence=1.0,
            ),
        ],
    )
    hardened, _ = harden_claim_semantics(result, transcript)
    birth, move = hardened.events
    assert birth.uncertainty is None
    assert birth.assertion_mode is AssertionMode.EXPLICIT
    assert move.uncertainty is not None
    assert move.assertion_mode is AssertionMode.UNCERTAIN


@pytest.mark.parametrize(
    ("expression", "kind", "precision"),
    [
        ("12 марта 1987 года", TemporalKind.EXACT_DATE, TemporalPrecision.DAY),
        ("в 1987 году", TemporalKind.YEAR, TemporalPrecision.YEAR),
        ("в марте 1987 года", TemporalKind.MONTH_YEAR, TemporalPrecision.MONTH),
        ("примерно в 1987 году", TemporalKind.APPROXIMATE, TemporalPrecision.YEAR),
        ("в конце девяностых", TemporalKind.DECADE, TemporalPrecision.DECADE),
        ("екі мыңыншы жылдардың басында", TemporalKind.DECADE, TemporalPrecision.DECADE),
        ("до свадьбы", TemporalKind.RELATIVE, TemporalPrecision.UNKNOWN),
        ("когда ему было лет 5", TemporalKind.RELATIVE, TemporalPrecision.UNKNOWN),
    ],
)
def test_temporal_parser_preserves_precision(
    expression: str,
    kind: TemporalKind,
    precision: TemporalPrecision,
) -> None:
    parsed = parse_temporal_expression(expression)
    assert parsed.value is not None
    assert parsed.value.kind is kind
    assert parsed.value.precision is precision
    assert parsed.value.original_expression == expression


def test_temporal_parser_rejects_invalid_calendar_date() -> None:
    parsed = parse_temporal_expression("31 февраля 1987 года")
    assert parsed.value is None
    assert "temporal_value_invalid" in [item.value for item in parsed.issues]


def test_temporal_parser_handles_leap_years() -> None:
    assert parse_temporal_expression("29 февраля 2024 года").value is not None
    assert parse_temporal_expression("29 февраля 2023 года").value is None


def test_numeric_date_remains_locale_ambiguous() -> None:
    parsed = parse_temporal_expression("03/04/1987")
    assert parsed.value is not None
    assert parsed.value.kind is TemporalKind.UNKNOWN
    assert parsed.value.normalized_value is None


@pytest.mark.parametrize(
    ("text", "state"),
    [
        ("Ерлан её бывший муж.", RelationshipState.FORMER),
        ("Олар ажырасты.", RelationshipState.ENDED),
        ("Он мне не брат.", RelationshipState.NEGATED),
        ("Он мне как брат, но мы не родственники.", RelationshipState.FIGURATIVE),
        ("Ол её бұрынғы күйеуі.", RelationshipState.FORMER),
        ("Олар қазір бірге емес.", RelationshipState.ENDED),
    ],
)
def test_relationship_state_detection(text: str, state: RelationshipState) -> None:
    assert infer_relationship_state(text) is state


def test_non_current_relationship_is_not_active_candidate() -> None:
    relationship = RelationshipClaim(
        relationship_id="rel",
        relationship_type=RelationshipType.SPOUSE,
        relationship_state=RelationshipState.FORMER,
        subject_mention_id="a",
        subject_role=RelationshipRole.SPOUSE,
        object_mention_id="b",
        object_role=RelationshipRole.SPOUSE,
        source_segment_ids=["seg_1"],
        confidence=1.0,
    )
    assert relationship_is_active_candidate(relationship) is False


def test_sanitizer_removes_invalid_date_but_preserves_event() -> None:
    text = "Алия родилась 31 февраля 1987 года."
    transcript = _transcript(text)
    raw = {
        "recording_id": transcript.recording_id,
        "speaker_id": "speaker",
        "speaker_name": "Айжан",
        "languages": ["ru"],
        "provenance_activities": [],
        "evidence_spans": [
            {
                "evidence_id": "ev_person",
                "segment_id": "seg_1",
                "text": "Алия",
                "source_layer": "raw_transcript",
                "start_char": None,
                "end_char": None,
                "evidence_class": "A_explicit",
                "purposes": ["identity"],
                "mention_ids": ["alia"],
            },
            {
                "evidence_id": "ev_event",
                "segment_id": "seg_1",
                "text": text,
                "source_layer": "raw_transcript",
                "start_char": None,
                "end_char": None,
                "evidence_class": "A_explicit",
                "purposes": ["claim"],
                "mention_ids": ["alia"],
            },
        ],
        "coreference_links": [],
        "conflict_sets": [],
        "people_mentions": [
            {
                "mention_id": "alia",
                "name": "Алия",
                "source_segment_ids": ["seg_1"],
                "evidence_ids": ["ev_person"],
                "confidence": 1.0,
            }
        ],
        "relationship_claims": [],
        "events": [
            {
                "event_id": "birth",
                "event_type": "birth",
                "title": "Алия родилась",
                "participant_mention_ids": ["alia"],
                "date": {
                    "value": "1987-02-31",
                    "precision": "day",
                    "kind": "exact_date",
                    "original_expression": "31 февраля 1987 года",
                },
                "description": "Алия родилась 31 февраля 1987 года",
                "source_segment_ids": ["seg_1"],
                "evidence_ids": ["ev_event"],
                "confidence": 1.0,
            }
        ],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }
    outcome = process_extraction_candidate(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker",
        speaker_name="Айжан",
        cleaned=_cleaned(text),
    )
    assert len(outcome.result.events) == 1
    assert outcome.result.events[0].date is None
    assert "temporal_value_invalid" in {item["code"] for item in outcome.issues}


def test_self_corrected_spouse_is_non_current() -> None:
    text = "Ерлан её муж... нет, бывший муж."
    transcript = _transcript(text)
    result = ExtractionResult(
        recording_id=transcript.recording_id,
        speaker_id="speaker",
        speaker_name="Айжан",
        people_mentions=[
            PersonMention(
                mention_id="erlan", name="Ерлан", source_segment_ids=["seg_1"], confidence=1.0
            ),
            PersonMention(
                mention_id="alia", name="Алия", source_segment_ids=["seg_1"], confidence=1.0
            ),
        ],
        relationship_claims=[
            RelationshipClaim(
                relationship_id="rel",
                relationship_type=RelationshipType.SPOUSE,
                subject_mention_id="erlan",
                subject_role=RelationshipRole.SPOUSE,
                object_mention_id="alia",
                object_role=RelationshipRole.SPOUSE,
                source_segment_ids=["seg_1"],
                confidence=1.0,
            )
        ],
    )
    hardened, issues = harden_claim_semantics(result, transcript, cleaned=_cleaned(text))
    assert hardened.relationship_claims[0].relationship_state is RelationshipState.FORMER
    assert not relationship_is_active_candidate(hardened.relationship_claims[0])
    assert "relationship_former_not_active" in {issue.code.value for issue in issues}


def test_temporal_self_correction_uses_corrected_value_and_preserves_correction() -> None:
    text = "Он родился в 1987... нет, в 1988 году."
    transcript = _transcript(text)
    cleaned = CleanerResult(
        readable_segments=[ReadableSegment(segment_id="seg_1", text=text)],
        detected_corrections=[
            DetectedCorrection(
                kind=CorrectionKind.SPEAKER_SELF_CORRECTION,
                subject="год рождения",
                original_value="1987",
                corrected_value="1988",
                source_segment_ids=["seg_1"],
                explanation="speaker corrected the year",
                confidence=1.0,
            )
        ],
        full_readable_text=text,
    )
    result = ExtractionResult(
        recording_id=transcript.recording_id,
        speaker_id="speaker",
        speaker_name="Айжан",
        events=[
            FamilyEvent(
                event_id="birth",
                event_type="birth",
                title="Он родился",
                date=EventDate(
                    value="1987",
                    original_expression="1987",
                    precision="year",
                ),
                description="Он родился в 1987 году",
                source_segment_ids=["seg_1"],
                confidence=1.0,
            )
        ],
    )

    hardened, issues = harden_claim_semantics(result, transcript, cleaned=cleaned)

    assert hardened.events[0].date is not None
    assert hardened.events[0].date.normalized_value == "1988"
    assert hardened.events[0].date.original_expression == "1988"
    assert cleaned.detected_corrections[0].original_value == "1987"
    assert cleaned.detected_corrections[0].corrected_value == "1988"
    assert "self_correction_applied" in {issue.code.value for issue in issues}


def test_relationship_state_is_owned_by_the_named_pair_in_shared_segment() -> None:
    text = "Ерлан — бывший муж Алии. Нурлан — муж Мадины."
    transcript = _transcript(text)
    people = [
        PersonMention(mention_id="erlan", name="Ерлан", source_segment_ids=["seg_1"], confidence=1),
        PersonMention(mention_id="alia", name="Алия", source_segment_ids=["seg_1"], confidence=1),
        PersonMention(
            mention_id="nurlan", name="Нурлан", source_segment_ids=["seg_1"], confidence=1
        ),
        PersonMention(
            mention_id="madina", name="Мадина", source_segment_ids=["seg_1"], confidence=1
        ),
    ]
    evidence = [
        EvidenceSpan(evidence_id="ev_former", segment_id="seg_1", text=text),
        EvidenceSpan(evidence_id="ev_current", segment_id="seg_1", text=text),
    ]
    result = ExtractionResult(
        recording_id=transcript.recording_id,
        speaker_id="speaker",
        speaker_name="Айжан",
        evidence_spans=evidence,
        people_mentions=people,
        relationship_claims=[
            RelationshipClaim(
                relationship_id="former",
                relationship_type=RelationshipType.SPOUSE,
                subject_mention_id="erlan",
                subject_role=RelationshipRole.SPOUSE,
                object_mention_id="alia",
                object_role=RelationshipRole.SPOUSE,
                source_segment_ids=["seg_1"],
                evidence_ids=["ev_former"],
                confidence=1,
            ),
            RelationshipClaim(
                relationship_id="current",
                relationship_type=RelationshipType.SPOUSE,
                subject_mention_id="nurlan",
                subject_role=RelationshipRole.SPOUSE,
                object_mention_id="madina",
                object_role=RelationshipRole.SPOUSE,
                source_segment_ids=["seg_1"],
                evidence_ids=["ev_current"],
                confidence=1,
            ),
        ],
    )

    hardened, _ = harden_claim_semantics(result, transcript)

    states = {
        item.relationship_id: item.relationship_state for item in hardened.relationship_claims
    }
    assert states == {
        "former": RelationshipState.FORMER,
        "current": RelationshipState.CURRENT,
    }


def test_reported_relationship_is_review_only_even_without_uncertainty_marker() -> None:
    text = "Бабушка сказала: «Ерлан муж Алии»."
    transcript = _transcript(text)
    result = ExtractionResult(
        recording_id=transcript.recording_id,
        speaker_id="speaker",
        speaker_name="Айжан",
        people_mentions=[
            PersonMention(
                mention_id="erlan",
                name="Ерлан",
                source_segment_ids=["seg_1"],
                confidence=1,
            ),
            PersonMention(
                mention_id="alia",
                name="Алия",
                source_segment_ids=["seg_1"],
                confidence=1,
            ),
        ],
        relationship_claims=[
            RelationshipClaim(
                relationship_id="reported",
                relationship_type=RelationshipType.SPOUSE,
                subject_mention_id="erlan",
                subject_role=RelationshipRole.SPOUSE,
                object_mention_id="alia",
                object_role=RelationshipRole.SPOUSE,
                source_segment_ids=["seg_1"],
                confidence=1,
            )
        ],
    )

    hardened, issues = harden_claim_semantics(result, transcript)
    relationship = hardened.relationship_claims[0]

    assert relationship.uncertainty is not None
    assert relationship.uncertainty.status is EpistemicStatus.REPORTED
    assert relationship.assertion_mode is AssertionMode.UNCERTAIN
    assert relationship_is_active_candidate(relationship) is False
    assert "reported_speech_requires_review" in {issue.code.value for issue in issues}


def test_double_negation_is_unresolved_instead_of_forced_negative() -> None:
    assert infer_relationship_state("Он мне не не брат.") is RelationshipState.UNRESOLVED


def test_widow_wording_marks_relationship_ended_without_calling_it_divorce() -> None:
    assert infer_relationship_state("Алия — вдова Ерлана.") is RelationshipState.ENDED
    assert infer_relationship_state("Ерлан умер.") is RelationshipState.CURRENT


def test_relative_year_bounds_allow_one_sided_before_and_after_ranges() -> None:
    before = parse_temporal_expression("до 1987 года").value
    after = parse_temporal_expression("после 1987 года").value

    assert before is not None
    assert before.upper_bound == "1986-12-31"
    assert before.lower_bound is None
    assert after is not None
    assert after.lower_bound == "1988"
    assert after.upper_bound is None


def test_temporal_conflict_is_limited_to_single_occurrence_events() -> None:
    birth_a = FamilyEvent(
        event_id="birth_a",
        event_type="birth",
        title="Рождение",
        participant_mention_ids=["alia"],
        date=EventDate(
            value="1987",
            normalized_value="1987",
            original_expression="1987",
            kind=TemporalKind.YEAR,
            precision=TemporalPrecision.YEAR,
        ),
        description="Рождение в 1987",
        source_segment_ids=["seg_1"],
        confidence=1,
    )
    birth_b = birth_a.model_copy(
        update={
            "event_id": "birth_b",
            "date": EventDate(
                value="1988",
                normalized_value="1988",
                original_expression="1988",
                kind=TemporalKind.YEAR,
                precision=TemporalPrecision.YEAR,
            ),
        }
    )
    move_a = birth_a.model_copy(
        update={"event_id": "move_a", "event_type": "move", "title": "Переезд"}
    )
    move_b = birth_b.model_copy(
        update={"event_id": "move_b", "event_type": "move", "title": "Переезд"}
    )

    birth_result, birth_issues = add_temporal_conflicts(
        ExtractionResult(
            recording_id="rec",
            speaker_id="speaker",
            speaker_name="Айжан",
            events=[birth_a, birth_b],
        )
    )
    move_result, move_issues = add_temporal_conflicts(
        ExtractionResult(
            recording_id="rec",
            speaker_id="speaker",
            speaker_name="Айжан",
            events=[move_a, move_b],
        )
    )

    assert len(birth_result.conflict_sets) == 1
    assert {issue.code.value for issue in birth_issues} == {"temporal_conflict_detected"}
    assert move_result.conflict_sets == []
    assert move_issues == []
