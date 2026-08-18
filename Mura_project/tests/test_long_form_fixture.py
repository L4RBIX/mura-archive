import json
from pathlib import Path

from mura.domain.models import RawSegment, TranscriptEnvelope
from mura.long_form import LongFormExtractionPlanner, LongFormMode


def test_long_form_fixture_is_synthetic_complete_and_plannable() -> None:
    path = Path("benchmarks/long_form_mixed_ru_kk_v1.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    transcript = TranscriptEnvelope(
        recording_id=payload["fixture_id"],
        duration_seconds=payload["duration_seconds"],
        language_hints=payload["language_hints"],
        full_text=" ".join(item["text"] for item in payload["segments"]),
        segments=[RawSegment.model_validate(item) for item in payload["segments"]],
        asr_model="synthetic-fixture",
        asr_revision="v1",
        chunker_version="v1",
    )

    plan = LongFormExtractionPlanner().plan(transcript)

    assert payload["privacy"] == "synthetic"
    assert len(transcript.segments) == 18
    assert plan.mode is LongFormMode.WINDOWED
    assert 3 <= len(plan.windows) <= 6
    assert {item.segment_id for item in transcript.segments} == {
        segment_id for window in plan.windows for segment_id in window.source_segment_ids
    }
    assert {
        "same_name_collision",
        "aliases",
        "self_corrected_year",
        "former_spouse",
        "figurative_father_relationship",
        "russian_teacher_quote",
        "private_story",
    }.issubset(payload["features"])
