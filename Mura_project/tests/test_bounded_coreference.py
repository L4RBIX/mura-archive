from __future__ import annotations

from typing import Any

from mura.domain.models import (
    CoreferenceMethod,
    CoreferenceStatus,
    EvidenceClass,
    GrammaticalNumber,
    RawSegment,
    TranscriptEnvelope,
)
from mura.extraction_sanitizer import sanitize_extraction_output


def _transcript(*segments: tuple[str, str], languages: list[str]) -> TranscriptEnvelope:
    raw_segments = [
        RawSegment(
            segment_id=segment_id,
            start=float(index * 10),
            end=float((index + 1) * 10),
            text=text,
        )
        for index, (segment_id, text) in enumerate(segments)
    ]
    return TranscriptEnvelope(
        recording_id="rec_coreference",
        duration_seconds=float(len(raw_segments) * 10),
        language_hints=languages,
        full_text=" ".join(segment.text for segment in raw_segments),
        segments=raw_segments,
        asr_model="benchmark-fixture",
        asr_revision="fixture-v1",
        chunker_version="fixture-v1",
    )


def _person(mention_id: str, name: str, *segment_ids: str) -> dict[str, Any]:
    return {
        "mention_id": mention_id,
        "name": name,
        "category": "family_member",
        "source_segment_ids": list(segment_ids),
        "confidence": 1.0,
    }


def _parent_claim(
    relationship_id: str,
    parent_id: str,
    child_id: str,
    segment_id: str,
    *,
    coreference_link_ids: list[str] | None = None,
) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "relationship_id": relationship_id,
        "relationship_type": "parent_child",
        "subject_mention_id": parent_id,
        "subject_role": "parent",
        "object_mention_id": child_id,
        "object_role": "child",
        "source_segment_ids": [segment_id],
        "confidence": 1.0,
    }
    if coreference_link_ids is not None:
        candidate["coreference_link_ids"] = coreference_link_ids
    return candidate


def _raw(
    *,
    languages: list[str],
    people: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    evidence_spans: list[dict[str, Any]] | None = None,
    coreference_links: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "recording_id": "rec_coreference",
        "speaker_id": "speaker_1",
        "speaker_name": "Күләш",
        "languages": languages,
        "evidence_spans": evidence_spans or [],
        "coreference_links": coreference_links or [],
        "people_mentions": people,
        "relationship_claims": relationships,
        "events": [],
        "descriptions": [],
        "stories": [],
        "unresolved_questions": [],
    }


def test_kazakh_singular_anaphor_resolves_one_preceding_person() -> None:
    transcript = _transcript(
        ("seg_001", "Ерлан инженер."),
        ("seg_002", "Оның ұлы Нұрлан."),
        languages=["kk"],
    )
    raw = _raw(
        languages=["kk"],
        people=[
            _person("mention_erlan", "Ерлан", "seg_001"),
            _person("mention_nurlan", "Нұрлан", "seg_002"),
        ],
        relationships=[
            _parent_claim(
                "relationship_parent",
                "mention_erlan",
                "mention_nurlan",
                "seg_002",
            )
        ],
    )

    result, issues, closure_count = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert issues == []
    assert closure_count == 1
    assert len(result.relationship_claims) == 1
    relationship = result.relationship_claims[0]
    assert relationship.evidence_class is EvidenceClass.D_CONTEXT_RESOLVED
    assert relationship.source_segment_ids == ["seg_001", "seg_002"]
    assert len(relationship.coreference_link_ids) == 1

    link = result.coreference_links[0]
    assert link.status is CoreferenceStatus.RESOLVED
    assert link.method is CoreferenceMethod.DETERMINISTIC_DISCOURSE
    assert link.grammatical_number is GrammaticalNumber.SINGULAR
    assert link.antecedent_mention_ids == ["mention_erlan"]
    assert "discourse.singular.unique_antecedent.v1" in link.reason
    assert set(link.evidence_ids).issubset(relationship.evidence_ids)


def test_russian_competing_antecedents_create_ambiguous_link_and_quarantine_claim() -> None:
    transcript = _transcript(
        ("seg_001", "Ерлан встретил Болата."),
        ("seg_002", "Его сын Нурлан."),
        languages=["ru"],
    )
    raw = _raw(
        languages=["ru"],
        people=[
            _person("mention_erlan", "Ерлан", "seg_001"),
            _person("mention_bolat", "Болат", "seg_001"),
            _person("mention_nurlan", "Нурлан", "seg_002"),
        ],
        relationships=[
            _parent_claim(
                "relationship_ambiguous",
                "mention_erlan",
                "mention_nurlan",
                "seg_002",
            )
        ],
    )

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert result.relationship_claims == []
    assert len(result.coreference_links) == 1
    link = result.coreference_links[0]
    assert link.status is CoreferenceStatus.AMBIGUOUS
    assert link.antecedent_mention_ids == []
    assert set(link.candidate_mention_ids) == {"mention_erlan", "mention_bolat"}
    assert "discourse.ambiguous_competing_antecedents.v1" in link.reason
    issue = next(item for item in issues if item["object_id"] == "relationship_ambiguous")
    assert issue["code"] == "relationship_grounding_rejected"


def test_kazakh_plural_anaphor_resolves_explicit_married_pair() -> None:
    transcript = _transcript(
        ("seg_001", "Ерлан мен Динара үйленді."),
        ("seg_002", "Олардың ұлы Нұрлан."),
        languages=["kk"],
    )
    raw = _raw(
        languages=["kk"],
        people=[
            _person("mention_erlan", "Ерлан", "seg_001"),
            _person("mention_dinara", "Динара", "seg_001"),
            _person("mention_nurlan", "Нұрлан", "seg_002"),
        ],
        relationships=[
            _parent_claim(
                "relationship_erlan_parent",
                "mention_erlan",
                "mention_nurlan",
                "seg_002",
            ),
            _parent_claim(
                "relationship_dinara_parent",
                "mention_dinara",
                "mention_nurlan",
                "seg_002",
            ),
        ],
    )

    result, issues, closure_count = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert issues == []
    assert closure_count == 2
    assert {item.relationship_id for item in result.relationship_claims} == {
        "relationship_erlan_parent",
        "relationship_dinara_parent",
    }
    assert all(
        item.evidence_class is EvidenceClass.D_CONTEXT_RESOLVED
        for item in result.relationship_claims
    )
    link = result.coreference_links[0]
    assert link.status is CoreferenceStatus.RESOLVED
    assert link.grammatical_number is GrammaticalNumber.PLURAL
    assert set(link.antecedent_mention_ids) == {"mention_erlan", "mention_dinara"}
    assert "discourse.plural.explicit_pair.v1" in link.reason


def test_english_singular_anaphor_is_supported() -> None:
    transcript = _transcript(
        ("seg_001", "Erlan is an engineer."),
        ("seg_002", "His son is Nurlan."),
        languages=["en"],
    )
    raw = _raw(
        languages=["en"],
        people=[
            _person("mention_erlan", "Erlan", "seg_001"),
            _person("mention_nurlan", "Nurlan", "seg_002"),
        ],
        relationships=[
            _parent_claim(
                "relationship_parent",
                "mention_erlan",
                "mention_nurlan",
                "seg_002",
            )
        ],
    )

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert issues == []
    assert result.relationship_claims[0].evidence_class is EvidenceClass.D_CONTEXT_RESOLVED
    assert result.coreference_links[0].anaphor_text == "His"


def test_plural_anaphor_without_pair_cue_stays_ambiguous() -> None:
    transcript = _transcript(
        ("seg_001", "Erlan and Dinara visited the city."),
        ("seg_002", "Their son is Nurlan."),
        languages=["en"],
    )
    raw = _raw(
        languages=["en"],
        people=[
            _person("mention_erlan", "Erlan", "seg_001"),
            _person("mention_dinara", "Dinara", "seg_001"),
            _person("mention_nurlan", "Nurlan", "seg_002"),
        ],
        relationships=[
            _parent_claim(
                "relationship_parent",
                "mention_erlan",
                "mention_nurlan",
                "seg_002",
            )
        ],
    )

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert result.relationship_claims == []
    assert result.coreference_links[0].status is CoreferenceStatus.AMBIGUOUS
    assert any(item["object_id"] == "relationship_parent" for item in issues)


def test_model_proposal_resolved_link_cannot_authorize_ambiguous_claim() -> None:
    transcript = _transcript(
        ("seg_001", "Erlan met Bolat."),
        ("seg_002", "His son is Nurlan."),
        languages=["en"],
    )
    evidence = [
        {
            "evidence_id": "evidence_model_pronoun",
            "segment_id": "seg_002",
            "text": "His",
            "source_layer": "raw_transcript",
            "evidence_class": "D_context_resolved",
            "purposes": ["coreference"],
            "mention_ids": ["mention_erlan"],
            "confidence": 0.9,
        }
    ]
    coreference_links = [
        {
            "coreference_id": "coreference_model",
            "anaphor_text": "His",
            "source_segment_ids": ["seg_002"],
            "evidence_ids": ["evidence_model_pronoun"],
            "status": "resolved",
            "method": "model_proposal",
            "grammatical_number": "singular",
            "antecedent_mention_ids": ["mention_erlan"],
            "candidate_mention_ids": ["mention_erlan", "mention_bolat"],
            "evidence_class": "D_context_resolved",
            "confidence": 0.9,
            "reason": "Model guessed Erlan.",
        }
    ]
    raw = _raw(
        languages=["en"],
        evidence_spans=evidence,
        coreference_links=coreference_links,
        people=[
            _person("mention_erlan", "Erlan", "seg_001"),
            _person("mention_bolat", "Bolat", "seg_001"),
            _person("mention_nurlan", "Nurlan", "seg_002"),
        ],
        relationships=[
            _parent_claim(
                "relationship_parent",
                "mention_erlan",
                "mention_nurlan",
                "seg_002",
                coreference_link_ids=["coreference_model"],
            )
        ],
    )

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert result.relationship_claims == []
    assert any(
        link.status is CoreferenceStatus.AMBIGUOUS
        and link.method is CoreferenceMethod.DETERMINISTIC_DISCOURSE
        for link in result.coreference_links
    )
    assert any(item["object_id"] == "relationship_parent" for item in issues)


def test_resolver_does_not_skip_over_an_intervening_segment() -> None:
    transcript = _transcript(
        ("seg_001", "Erlan is an engineer."),
        ("seg_002", "The weather was cold."),
        ("seg_003", "His son is Nurlan."),
        languages=["en"],
    )
    raw = _raw(
        languages=["en"],
        people=[
            _person("mention_erlan", "Erlan", "seg_001"),
            _person("mention_nurlan", "Nurlan", "seg_003"),
        ],
        relationships=[
            _parent_claim(
                "relationship_parent",
                "mention_erlan",
                "mention_nurlan",
                "seg_003",
            )
        ],
    )

    result, issues, _ = sanitize_extraction_output(
        raw=raw,
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )

    assert result.relationship_claims == []
    assert result.coreference_links == []
    assert any(item["object_id"] == "relationship_parent" for item in issues)
