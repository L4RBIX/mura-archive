from __future__ import annotations

from typing import Any

from mura.domain.models import (
    AssertionMode,
    CoreferenceStatus,
    EvidenceClass,
    ExtractionResult,
    KnownPerson,
    NameVariant,
    NameVariantType,
    PersonCategory,
    PersonMention,
    RawSegment,
    RelationshipClaim,
    RelationshipRole,
    RelationshipState,
    RelationshipType,
    ResolutionStatus,
    TranscriptEnvelope,
)
from mura.entity_resolution import EntityResolutionContext, KnownPersonProfile
from mura.extraction_sanitizer import sanitize_extraction_output
from mura.resolution import resolve_mentions_with_report


def _transcript(*texts: str, languages: list[str] | None = None) -> TranscriptEnvelope:
    return TranscriptEnvelope(
        recording_id="rec_identity_v3",
        duration_seconds=float(len(texts) * 10),
        language_hints=languages or ["ru", "kk"],
        full_text=" ".join(texts),
        segments=[
            RawSegment(
                segment_id=f"seg_{index:03d}",
                start=float((index - 1) * 10),
                end=float(index * 10),
                text=text,
            )
            for index, text in enumerate(texts, start=1)
        ],
        asr_model="fixture",
        asr_revision="v1",
        chunker_version="v1",
    )


def _person(mention_id: str, name: str, *segment_ids: str) -> dict[str, Any]:
    return {
        "mention_id": mention_id,
        "name": name,
        "category": "family_member",
        "source_segment_ids": list(segment_ids),
        "confidence": 1.0,
    }


def _relationship(
    relationship_id: str,
    subject_id: str,
    object_id: str,
    segment_id: str,
) -> dict[str, Any]:
    return {
        "relationship_id": relationship_id,
        "relationship_type": "parent_child",
        "subject_mention_id": subject_id,
        "subject_role": "parent",
        "object_mention_id": object_id,
        "object_role": "child",
        "source_segment_ids": [segment_id],
        "confidence": 1.0,
    }


def _sanitize(
    transcript: TranscriptEnvelope,
    people: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
):
    return sanitize_extraction_output(
        raw={
            "recording_id": transcript.recording_id,
            "speaker_id": "speaker_1",
            "speaker_name": "Күләш",
            "languages": transcript.language_hints,
            "people_mentions": people,
            "relationship_claims": relationships,
            "events": [],
            "descriptions": [],
            "stories": [],
            "unresolved_questions": [],
        },
        transcript=transcript,
        speaker_id="speaker_1",
        speaker_name="Күләш",
    )


def test_quoted_pronoun_never_authorizes_narrator_relationship() -> None:
    transcript = _transcript("Ерлан инженер.", "Она сказала: «Его сын Нурлан».")
    result, issues, _ = _sanitize(
        transcript,
        [_person("erlan", "Ерлан", "seg_001"), _person("nurlan", "Нурлан", "seg_002")],
        [_relationship("r_parent", "erlan", "nurlan", "seg_002")],
    )

    assert result.coreference_links == []
    assert result.relationship_claims == []
    assert any(item["object_id"] == "r_parent" for item in issues)


def test_adversative_clause_preserves_ambiguity_instead_of_using_recency() -> None:
    transcript = _transcript("Ерлан встретил Болата, но его сын Нурлан.")
    result, _, _ = _sanitize(
        transcript,
        [
            _person("erlan", "Ерлан", "seg_001"),
            _person("bolat", "Болат", "seg_001"),
            _person("nurlan", "Нурлан", "seg_001"),
        ],
        [_relationship("r_parent", "erlan", "nurlan", "seg_001")],
    )

    assert result.relationship_claims == []
    assert len(result.coreference_links) == 1
    link = result.coreference_links[0]
    assert link.status is CoreferenceStatus.AMBIGUOUS
    assert set(link.candidate_mention_ids) == {"erlan", "bolat"}


def test_kazakh_case_form_resolves_only_unique_outside_quote_antecedent() -> None:
    transcript = _transcript("Ерлан ауылда тұрды.", "Онымен бірге ұлы Нұрлан тұрды.")
    result, issues, _ = _sanitize(
        transcript,
        [_person("erlan", "Ерлан", "seg_001"), _person("nurlan", "Нұрлан", "seg_002")],
        [_relationship("r_parent", "erlan", "nurlan", "seg_002")],
    )

    assert issues == []
    assert result.relationship_claims[0].evidence_class is EvidenceClass.D_CONTEXT_RESOLVED
    assert result.coreference_links[0].anaphor_text == "Онымен"
    assert result.coreference_links[0].antecedent_mention_ids == ["erlan"]


def test_russian_compound_case_form_resolves_unique_antecedent() -> None:
    transcript = _transcript("Алия учитель.", "С ней дочь Мадина.")
    result, issues, _ = _sanitize(
        transcript,
        [_person("aliya", "Алия", "seg_001"), _person("madina", "Мадина", "seg_002")],
        [_relationship("r_parent", "aliya", "madina", "seg_002")],
    )

    assert issues == []
    assert result.coreference_links[0].anaphor_text == "С ней"
    assert result.coreference_links[0].antecedent_mention_ids == ["aliya"]


def _mention(
    mention_id: str,
    name: str,
    *,
    relation: str | None = None,
    assertion_mode: AssertionMode = AssertionMode.EXPLICIT,
    variants: list[NameVariant] | None = None,
) -> PersonMention:
    return PersonMention(
        mention_id=mention_id,
        name=name,
        category=PersonCategory.FAMILY_MEMBER,
        relation_to_speaker=relation,
        assertion_mode=assertion_mode,
        source_segment_ids=["seg_001"],
        name_variants=variants or [],
        confidence=1.0,
    )


def _profile(
    person_id: str,
    canonical_name: str,
    *,
    aliases: list[str] | None = None,
    verified_aliases: list[str] | None = None,
    relation: str | None = None,
    generation: int | None = None,
    spouses: list[str] | None = None,
) -> KnownPersonProfile:
    return KnownPersonProfile(
        family_id="family_a",
        person=KnownPerson(
            person_id=person_id,
            canonical_name=canonical_name,
            aliases=aliases or [],
            category=PersonCategory.FAMILY_MEMBER,
            relation_to_speaker=relation,
        ),
        verified_aliases=verified_aliases or [],
        generation_relative_to_speaker=generation,
        spouse_person_ids=spouses or [],
    )


def test_duplicate_verified_alias_routes_to_review_even_with_one_context_conflict() -> None:
    mention = _mention("m_ereke", "Ереке", relation="son")
    context = EntityResolutionContext(
        family_id="family_a",
        profiles=[
            _profile(
                "p_erlan_son",
                "Ерлан",
                aliases=["Ереке"],
                verified_aliases=["Ереке"],
                relation="son",
                generation=1,
            ),
            _profile(
                "p_erlan_uncle",
                "Ерлан аға",
                aliases=["Ереке"],
                verified_aliases=["Ереке"],
                relation="brother",
                generation=0,
            ),
        ],
    )

    run = resolve_mentions_with_report(
        ExtractionResult(
            recording_id="rec_alias_collision",
            speaker_id="speaker",
            speaker_name="Күләш",
            people_mentions=[mention],
        ),
        context,
    )

    assert run.resolutions[0].status is ResolutionStatus.NEEDS_REVIEW
    assert run.metrics.verified_alias_collisions == 1
    assert "resolution.guard.verified_alias_collision.v1" in run.traces[0].rule_ids


def test_unverified_structured_alias_is_candidate_only() -> None:
    variant = NameVariant(
        variant_id="variant_ereke",
        surface="Ереке",
        normalized="ереке",
        variant_type=NameVariantType.NICKNAME,
        source_segment_ids=["seg_001"],
        evidence_ids=["evidence_alias"],
    )
    mention = _mention("m_erlan", "Белгісіз", variants=[variant])
    context = EntityResolutionContext(
        family_id="family_a",
        profiles=[_profile("p_erlan", "Ерлан", aliases=["Ереке"])],
    )

    run = resolve_mentions_with_report(
        ExtractionResult(
            recording_id="rec_unverified_alias",
            speaker_id="speaker",
            speaker_name="Күләш",
            people_mentions=[mention],
        ),
        context,
    )

    assert run.resolutions[0].status is ResolutionStatus.NEEDS_REVIEW
    assert "resolution.name.structured_unverified_alias.v3" in run.traces[0].rule_ids


def test_structured_transliteration_matching_unique_canonical_name_resolves() -> None:
    variant = NameVariant(
        variant_id="variant_erlan",
        surface="Ерлан",
        normalized="ерлан",
        variant_type=NameVariantType.TRANSLITERATION,
        source_segment_ids=["seg_001"],
        evidence_ids=["evidence_name"],
    )
    mention = _mention("m_erlan", "Erlan", variants=[variant])
    context = EntityResolutionContext(
        family_id="family_a",
        profiles=[_profile("p_erlan", "Ерлан")],
    )

    run = resolve_mentions_with_report(
        ExtractionResult(
            recording_id="rec_transliteration",
            speaker_id="speaker",
            speaker_name="Күләш",
            people_mentions=[mention],
        ),
        context,
    )

    assert run.resolutions[0].status is ResolutionStatus.RESOLVED
    assert run.resolutions[0].person_id == "p_erlan"
    assert "resolution.name.structured_canonical_variant.v3" in run.traces[0].rule_ids


def test_former_relationship_cannot_corroborate_identity_merge() -> None:
    erlan = _mention("m_erlan", "Ерлан")
    dina = _mention("m_dina", "Дина")
    extraction = ExtractionResult(
        recording_id="rec_former_guard",
        speaker_id="speaker",
        speaker_name="Күләш",
        people_mentions=[erlan, dina],
        relationship_claims=[
            RelationshipClaim(
                relationship_id="r_former",
                relationship_type=RelationshipType.SPOUSE,
                relationship_state=RelationshipState.FORMER,
                subject_mention_id="m_erlan",
                subject_role=RelationshipRole.SPOUSE,
                object_mention_id="m_dina",
                object_role=RelationshipRole.SPOUSE,
                source_segment_ids=["seg_001"],
                evidence_ids=["evidence_former"],
                evidence_class=EvidenceClass.A_EXPLICIT,
                confidence=1.0,
            )
        ],
    )
    context = EntityResolutionContext(
        family_id="family_a",
        profiles=[
            _profile("p_erlan", "Ерлан", spouses=["p_dinara"]),
            _profile(
                "p_dinara",
                "Динара",
                aliases=["Дина"],
                verified_aliases=["Дина"],
                spouses=["p_erlan"],
            ),
        ],
    )

    run = resolve_mentions_with_report(extraction, context)
    by_id = {item.mention_id: item for item in run.resolutions}

    assert by_id["m_dina"].status is ResolutionStatus.RESOLVED
    assert by_id["m_erlan"].status is ResolutionStatus.NEEDS_REVIEW
    assert run.metrics.inactive_relationships_ignored == 1


def test_distinct_relationship_endpoints_cannot_collapse_to_same_person() -> None:
    first = _mention("m_first", "Ереке")
    second = _mention("m_second", "Ереке")
    extraction = ExtractionResult(
        recording_id="rec_endpoint_collision",
        speaker_id="speaker",
        speaker_name="Күләш",
        people_mentions=[first, second],
        relationship_claims=[
            RelationshipClaim(
                relationship_id="r_spouse",
                relationship_type=RelationshipType.SPOUSE,
                subject_mention_id="m_first",
                subject_role=RelationshipRole.SPOUSE,
                object_mention_id="m_second",
                object_role=RelationshipRole.SPOUSE,
                source_segment_ids=["seg_001"],
                evidence_ids=["evidence_spouse"],
                evidence_class=EvidenceClass.A_EXPLICIT,
                confidence=1.0,
            )
        ],
    )
    context = EntityResolutionContext(
        family_id="family_a",
        profiles=[
            _profile(
                "p_erlan",
                "Ерлан",
                aliases=["Ереке"],
                verified_aliases=["Ереке"],
            )
        ],
    )

    run = resolve_mentions_with_report(extraction, context)

    assert all(item.status is ResolutionStatus.NEEDS_REVIEW for item in run.resolutions)
    assert run.metrics.mention_identity_collisions == 1
    assert all(
        "resolution.guard.relationship_endpoint_collision.v1" in trace.rule_ids
        for trace in run.traces
    )


def test_uncertain_identity_mention_never_auto_merges_on_verified_alias() -> None:
    mention = _mention("m_ereke", "Ереке", assertion_mode=AssertionMode.UNCERTAIN)
    context = EntityResolutionContext(
        family_id="family_a",
        profiles=[
            _profile(
                "p_erlan",
                "Ерлан",
                aliases=["Ереке"],
                verified_aliases=["Ереке"],
            )
        ],
    )

    run = resolve_mentions_with_report(
        ExtractionResult(
            recording_id="rec_uncertain_identity",
            speaker_id="speaker",
            speaker_name="Күләш",
            people_mentions=[mention],
        ),
        context,
    )

    assert run.resolutions[0].status is ResolutionStatus.NEEDS_REVIEW
    assert "resolution.guard.uncertain_mention.v1" in run.traces[0].rule_ids
