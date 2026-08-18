from pathlib import Path

import pytest
from pydantic import ValidationError

from mura.domain.models import (
    ExtractionResult,
    KnownPerson,
    PersonCategory,
    PersonMention,
    RelationshipClaim,
    RelationshipRole,
    RelationshipType,
    ResolutionStatus,
)
from mura.entity_resolution import EntityResolutionContext, KnownPersonProfile
from mura.evaluation.entity_resolution import run_entity_resolution_benchmark
from mura.resolution import resolve_mentions, resolve_mentions_with_report

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "benchmarks" / "entity_resolution_v2.json"


def _extraction(mention: PersonMention) -> ExtractionResult:
    return ExtractionResult(
        schema_version="extraction-v2",
        recording_id="recording_test",
        speaker_id="speaker_test",
        speaker_name="Күләш",
        people_mentions=[mention],
    )


def _mention(
    *,
    mention_id: str,
    name: str,
    category: PersonCategory = PersonCategory.FAMILY_MEMBER,
    relation_to_speaker: str | None = None,
) -> PersonMention:
    return PersonMention(
        mention_id=mention_id,
        name=name,
        category=category,
        relation_to_speaker=relation_to_speaker,
        source_segment_ids=["seg_001"],
        confidence=1.0,
    )


def test_exact_name_alone_is_reviewed_instead_of_merged() -> None:
    mention = _mention(mention_id="mention_erlan", name="Ерлан")
    context = EntityResolutionContext(
        family_id="family_a",
        profiles=[
            KnownPersonProfile(
                family_id="family_a",
                person=KnownPerson(
                    person_id="person_erlan",
                    canonical_name="Ерлан",
                    category=PersonCategory.FAMILY_MEMBER,
                ),
            )
        ],
    )

    run = resolve_mentions_with_report(_extraction(mention), context)

    assert run.resolutions[0].status is ResolutionStatus.NEEDS_REVIEW
    assert run.resolutions[0].person_id is None
    assert run.resolutions[0].candidate_person_ids == ["person_erlan"]
    assert run.metrics.resolved == 0
    assert run.metrics.needs_review == 1


def test_verified_alias_resolves_but_stays_unreviewed() -> None:
    mention = _mention(mention_id="mention_ereke", name="Ереке")
    context = EntityResolutionContext(
        family_id="family_a",
        profiles=[
            KnownPersonProfile(
                family_id="family_a",
                person=KnownPerson(
                    person_id="person_erlan",
                    canonical_name="Ерлан",
                    aliases=["Ереке"],
                    category=PersonCategory.FAMILY_MEMBER,
                ),
                verified_aliases=["Ереке"],
            )
        ],
    )

    run = resolve_mentions_with_report(_extraction(mention), context)

    assert run.resolutions[0].status is ResolutionStatus.RESOLVED
    assert run.resolutions[0].person_id == "person_erlan"
    trace = run.traces[0]
    assert trace.verification_status.value == "unreviewed"
    assert "resolution.name.verified_alias.v3" in trace.rule_ids


def test_unverified_archive_alias_remains_reviewable() -> None:
    mention = _mention(mention_id="mention_ereke", name="Ереке")
    context = EntityResolutionContext(
        family_id="family_a",
        profiles=[
            KnownPersonProfile(
                family_id="family_a",
                person=KnownPerson(
                    person_id="person_erlan",
                    canonical_name="Ерлан",
                    aliases=["Ереке"],
                    category=PersonCategory.FAMILY_MEMBER,
                ),
            )
        ],
    )

    run = resolve_mentions_with_report(_extraction(mention), context)

    assert run.resolutions[0].status is ResolutionStatus.NEEDS_REVIEW
    assert "resolution.name.archive_alias_candidate.v3" in run.traces[0].rule_ids


def test_relation_and_generation_must_both_agree_for_name_based_auto_merge() -> None:
    mention = _mention(
        mention_id="mention_erlan_son",
        name="Ерлан",
        relation_to_speaker="son",
    )
    context = EntityResolutionContext(
        family_id="family_a",
        speaker_id="speaker_kulash",
        profiles=[
            KnownPersonProfile(
                family_id="family_a",
                person=KnownPerson(
                    person_id="person_erlan_son",
                    canonical_name="Ерлан",
                    category=PersonCategory.FAMILY_MEMBER,
                    relation_to_speaker="son",
                ),
                generation_relative_to_speaker=1,
            )
        ],
    )

    resolution = resolve_mentions_with_report(_extraction(mention), context).resolutions[0]

    assert resolution.status is ResolutionStatus.RESOLVED
    assert resolution.person_id == "person_erlan_son"


def test_uncertain_relationship_cannot_corroborate_an_identity_merge() -> None:
    erlan = _mention(mention_id="mention_erlan", name="Ерлан")
    dina = _mention(mention_id="mention_dina", name="Дина")
    extraction = ExtractionResult(
        schema_version="extraction-v2",
        recording_id="recording_graph_guard",
        speaker_id="speaker_test",
        speaker_name="Күләш",
        people_mentions=[erlan, dina],
        relationship_claims=[
            RelationshipClaim(
                relationship_id="relationship_spouse",
                relationship_type=RelationshipType.SPOUSE,
                subject_mention_id="mention_erlan",
                subject_role=RelationshipRole.SPOUSE,
                object_mention_id="mention_dina",
                object_role=RelationshipRole.SPOUSE,
                source_segment_ids=["seg_001"],
                confidence=1.0,
            )
        ],
    )
    context = EntityResolutionContext(
        family_id="family_a",
        profiles=[
            KnownPersonProfile(
                family_id="family_a",
                person=KnownPerson(
                    person_id="person_erlan",
                    canonical_name="Ерлан",
                    category=PersonCategory.FAMILY_MEMBER,
                ),
                spouse_person_ids=["person_dinara"],
            ),
            KnownPersonProfile(
                family_id="family_a",
                person=KnownPerson(
                    person_id="person_dinara",
                    canonical_name="Динара",
                    aliases=["Дина"],
                    category=PersonCategory.FAMILY_MEMBER,
                ),
                verified_aliases=["Дина"],
                spouse_person_ids=["person_erlan"],
            ),
        ],
    )

    run = resolve_mentions_with_report(extraction, context)
    resolutions = {item.mention_id: item for item in run.resolutions}

    assert resolutions["mention_dina"].status is ResolutionStatus.RESOLVED
    assert resolutions["mention_erlan"].status is ResolutionStatus.NEEDS_REVIEW


def test_foreign_family_profile_is_rejected_before_resolution() -> None:
    with pytest.raises(ValidationError, match="another family archive"):
        EntityResolutionContext(
            family_id="family_a",
            profiles=[
                KnownPersonProfile(
                    family_id="family_b",
                    person=KnownPerson(
                        person_id="person_foreign",
                        canonical_name="Ерлан",
                    ),
                )
            ],
        )


def test_verified_alias_must_exist_in_archive_aliases() -> None:
    with pytest.raises(ValidationError, match="verified aliases"):
        KnownPersonProfile(
            family_id="family_a",
            person=KnownPerson(
                person_id="person_erlan",
                canonical_name="Ерлан",
                aliases=[],
            ),
            verified_aliases=["Ереке"],
        )


def test_legacy_adapter_remains_available_but_alias_is_fail_closed() -> None:
    mention = _mention(mention_id="mention_ereke", name="Ереке")
    resolutions = resolve_mentions(
        _extraction(mention),
        [
            KnownPerson(
                person_id="person_erlan",
                canonical_name="Ерлан",
                aliases=["Ереке"],
            )
        ],
    )

    assert resolutions[0].status is ResolutionStatus.NEEDS_REVIEW


def test_entity_resolution_release_benchmark_has_zero_false_merges() -> None:
    report = run_entity_resolution_benchmark(BENCHMARK)
    summary = report.summary

    assert summary.case_count == 14
    assert summary.mentions == 17
    assert summary.status_accuracy == 1.0
    assert summary.identity_accuracy == 1.0
    assert summary.review_routing_accuracy == 1.0
    assert summary.new_person_accuracy == 1.0
    assert summary.false_merges == 0
    assert summary.false_splits == 0
    assert summary.cross_family_merges == 0
    assert summary.verified_alias_collisions == 1
    assert summary.mention_identity_collisions == 1
    assert summary.inactive_relationships_ignored == 1
    assert report.pipeline_versions["pipeline"] == "mura-core-v0.15.0"
    assert report.pipeline_versions["resolver"] == "mention-resolver-v3-collision-safe"
