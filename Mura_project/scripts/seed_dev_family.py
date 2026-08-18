"""Seed a development family with archive content, through canonical persistence.

Written for local browser validation only. It goes through
`ArchiveRepository.persist_pipeline_result` -- the same path the recording
worker uses -- rather than inserting rows, so what the product renders is what
extraction actually produces rather than a shape invented for a demo.

Usage:
    python scripts/seed_dev_family.py <family_id> [--recording-suffix N]

Refuses to run against a database whose name does not look disposable.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mura.domain.models import (
    CleanerResult,
    EventDate,
    EvidenceClass,
    EvidenceSpan,
    ExtractionResult,
    FamilyEvent,
    MentionResolution,
    PersonCategory,
    PersonMention,
    PipelineResult,
    RawSegment,
    ReadableSegment,
    RelationshipClaim,
    RelationshipRole,
    RelationshipType,
    ResolutionStatus,
    Story,
    TemporalPrecision,
    TranscriptEnvelope,
    UnresolvedQuestion,
)
from mura.storage.archive import ArchiveRepository
from mura.storage.database import Database, RecordingRepository, RecordingRow
from mura.storage.generic_claims import persist_generic_claims

TEXT = (
    "Бабушка Айсұлу рассказывала, как её муж Марат летом шестьдесят третьего "
    "чинил во дворе синий велосипед, а их сын Болат подавал ему ключи."
)


def build_result(recording_id: str) -> PipelineResult:
    transcript = TranscriptEnvelope(
        recording_id=recording_id,
        duration_seconds=42,
        language_hints=["ru"],
        full_text=TEXT,
        segments=[RawSegment(segment_id="seg_001", start=0, end=42, text=TEXT)],
        asr_model="dev-seed",
        asr_revision="dev-seed-v1",
        chunker_version="dev-seed-v1",
    )
    evidence = EvidenceSpan(
        evidence_id="evidence_main",
        segment_id="seg_001",
        text=TEXT,
        evidence_class=EvidenceClass.A_EXPLICIT,
        mention_ids=["mention_aisulu", "mention_marat", "mention_bolat"],
    )
    common = {
        "source_segment_ids": ["seg_001"],
        "evidence_ids": [evidence.evidence_id],
        "evidence_class": EvidenceClass.A_EXPLICIT,
    }
    people = [
        PersonMention(
            mention_id="mention_aisulu",
            name="Айсұлу",
            category=PersonCategory.FAMILY_MEMBER,
            relation_to_speaker="бабушка",
            confidence=1,
            **common,
        ),
        PersonMention(
            mention_id="mention_marat",
            name="Марат",
            category=PersonCategory.FAMILY_MEMBER,
            relation_to_speaker="муж бабушки",
            confidence=1,
            **common,
        ),
        PersonMention(
            mention_id="mention_bolat",
            name="Болат",
            category=PersonCategory.FAMILY_MEMBER,
            relation_to_speaker="сын",
            confidence=1,
            **common,
        ),
    ]
    relationships = [
        RelationshipClaim(
            relationship_id="relationship_spouse",
            relationship_type=RelationshipType.SPOUSE,
            subject_mention_id="mention_aisulu",
            subject_role=RelationshipRole.SPOUSE,
            object_mention_id="mention_marat",
            object_role=RelationshipRole.SPOUSE,
            confidence=1,
            **common,
        ),
        RelationshipClaim(
            relationship_id="relationship_parent",
            relationship_type=RelationshipType.PARENT_CHILD,
            subject_mention_id="mention_marat",
            subject_role=RelationshipRole.PARENT,
            object_mention_id="mention_bolat",
            object_role=RelationshipRole.CHILD,
            confidence=1,
            **common,
        ),
    ]
    event = FamilyEvent(
        event_id="event_bicycle",
        event_type="repair",
        title="Синий велосипед во дворе",
        participant_mention_ids=["mention_marat", "mention_bolat"],
        # Year only, and approximate: the product must not render a calendar day.
        date=EventDate(
            value="1963",
            precision=TemporalPrecision.YEAR,
            original_expression="летом шестьдесят третьего",
            approximate=True,
        ),
        location="Алматы",
        description="Марат чинил велосипед, Болат подавал ключи.",
        confidence=1,
        **common,
    )
    story = Story(
        story_id="story_bicycle",
        title="Синий велосипед Марата",
        summary=(
            "Бабушка Айсұлу вспоминает лето, когда её муж Марат чинил во дворе "
            "синий велосипед, а их сын Болат подавал ему ключи."
        ),
        person_mention_ids=["mention_aisulu", "mention_marat", "mention_bolat"],
        event_ids=["event_bicycle"],
        **common,
    )
    question = UnresolvedQuestion(
        question_id="question_bolat",
        question="Болат — сын Марата или племянник?",
        reason="В рассказе родство названо неоднозначно.",
        related_mention_ids=["mention_bolat"],
        **common,
    )
    return PipelineResult(
        transcript=transcript,
        cleaned_transcript=CleanerResult(
            readable_segments=[ReadableSegment(segment_id="seg_001", text=TEXT)],
            full_readable_text=TEXT,
        ),
        extraction=ExtractionResult(
            recording_id=recording_id,
            speaker_id=f"narrator_{recording_id}",
            speaker_name="Айсұлу",
            languages=["ru"],
            evidence_spans=[evidence],
            people_mentions=people,
            relationship_claims=relationships,
            events=[event],
            stories=[story],
            unresolved_questions=[question],
        ),
        resolutions=[
            MentionResolution(
                mention_id=mention.mention_id,
                status=ResolutionStatus.NEW_PERSON,
                reason="dev seed",
            )
            for mention in people
        ],
    )


LONG_TEXT = (
    "Мама всегда говорила, что дом начинается не со стен, а с запаха хлеба. "
    "Каждое утро, ещё до того как кто-то проснётся, она уже стояла у печи. "
    "Мы жили тогда в маленьком доме на окраине Алматы, и зимой окна замерзали "
    "так, что нельзя было разглядеть двор. Отец приносил уголь, а мы с сестрой "
    "по очереди держали дверцу. Когда хлеб был готов, она разламывала его "
    "руками и раздавала всем, даже соседским детям, которые почему-то всегда "
    "оказывались у нас во дворе именно в это время."
)


def build_long_result(recording_id: str) -> PipelineResult:
    """A second memory, deliberately long. Real archives are not one tidy
    paragraph, and reading width, truncation and vertical rhythm only show
    their problems against prose of a realistic length."""

    transcript = TranscriptEnvelope(
        recording_id=recording_id,
        duration_seconds=214,
        language_hints=["ru"],
        full_text=LONG_TEXT,
        segments=[RawSegment(segment_id="seg_001", start=0, end=214, text=LONG_TEXT)],
        asr_model="dev-seed",
        asr_revision="dev-seed-v1",
        chunker_version="dev-seed-v1",
    )
    evidence = EvidenceSpan(
        evidence_id="evidence_bread",
        segment_id="seg_001",
        text=LONG_TEXT,
        evidence_class=EvidenceClass.A_EXPLICIT,
        mention_ids=["mention_bibigul", "mention_sabyr"],
    )
    common = {
        "source_segment_ids": ["seg_001"],
        "evidence_ids": [evidence.evidence_id],
        "evidence_class": EvidenceClass.A_EXPLICIT,
    }
    people = [
        PersonMention(
            mention_id="mention_bibigul",
            name="Бибігүл Шаймарданова",
            category=PersonCategory.FAMILY_MEMBER,
            relation_to_speaker="мама",
            confidence=1,
            **common,
        ),
        PersonMention(
            mention_id="mention_sabyr",
            name="Сабыр",
            category=PersonCategory.FAMILY_MEMBER,
            relation_to_speaker="отец",
            confidence=1,
            **common,
        ),
    ]
    relationship = RelationshipClaim(
        relationship_id="relationship_bread_spouse",
        relationship_type=RelationshipType.SPOUSE,
        subject_mention_id="mention_bibigul",
        subject_role=RelationshipRole.SPOUSE,
        object_mention_id="mention_sabyr",
        object_role=RelationshipRole.SPOUSE,
        confidence=1,
        **common,
    )
    story = Story(
        story_id="story_bread",
        title="Мамин хлеб по утрам",
        summary=LONG_TEXT,
        person_mention_ids=["mention_bibigul", "mention_sabyr"],
        event_ids=[],
        **common,
    )
    question = UnresolvedQuestion(
        question_id="question_house",
        question="В каком году семья переехала в дом на окраине Алматы?",
        reason="В рассказе год не назван, упомянута только зима.",
        related_mention_ids=["mention_bibigul"],
        **common,
    )
    return PipelineResult(
        transcript=transcript,
        cleaned_transcript=CleanerResult(
            readable_segments=[ReadableSegment(segment_id="seg_001", text=LONG_TEXT)],
            full_readable_text=LONG_TEXT,
        ),
        extraction=ExtractionResult(
            recording_id=recording_id,
            speaker_id=f"narrator_{recording_id}",
            speaker_name="Айсұлу",
            languages=["ru"],
            evidence_spans=[evidence],
            people_mentions=people,
            relationship_claims=[relationship],
            events=[],
            stories=[story],
            unresolved_questions=[question],
        ),
        resolutions=[
            MentionResolution(
                mention_id=mention.mention_id,
                status=ResolutionStatus.NEW_PERSON,
                reason="dev seed",
            )
            for mention in people
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("family_id")
    parser.add_argument("--variant", choices=["bicycle", "bread"], default="bicycle")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    # The same disposability guard the PostgreSQL tests use. This script writes
    # archive rows; it must never be pointed at a real family's data.
    database_name = url.rsplit("/", 1)[-1].split("?")[0]
    if "test" not in database_name:
        print(f"refusing to seed {database_name!r}: name must contain 'test'", file=sys.stderr)
        return 2

    database = Database(url)
    recording_id = "rec_" + uuid.uuid4().hex
    job_id = "job_" + uuid.uuid4().hex

    RecordingRepository(database).create_recording_and_job(
        recording_id=recording_id,
        job_id=job_id,
        family_id=args.family_id,
        speaker_id=f"narrator_{recording_id}",
        speaker_name="Айсұлу",
        original_filename="memory.webm",
        content_type="audio/webm",
        audio_path=f"family/{args.family_id}/recordings/{recording_id}/original.webm",
        # No storage key: nothing was uploaded, so the story page must report
        # the audio as unavailable rather than offering a player.
        storage_key=None,
        storage_backend=None,
        audio_language="auto",
        output_language="same_as_transcript",
    )

    builder = build_result if args.variant == "bicycle" else build_long_result
    result = builder(recording_id)
    with database.session_factory.begin() as session:
        recording = session.get(RecordingRow, recording_id)
        assert recording is not None
        report = ArchiveRepository.persist_pipeline_result(
            session, recording=recording, result=result
        )
        # Same follow-up the worker performs, so profiles and generic
        # conflicts exist exactly as they would after a real recording.
        persist_generic_claims(session, recording=recording, result=result)

    print(f"seeded {args.family_id}: {report.model_dump()}")
    print(f"recording_id={recording_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
