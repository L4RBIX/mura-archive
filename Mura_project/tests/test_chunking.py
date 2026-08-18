from pathlib import Path

from services.kaggle_asr.chunking import (
    ChunkRecord,
    SpeechRegion,
    TranscriptPart,
    apply_edge_padding,
    build_smart_ranges,
    merge_transcript_parts,
)


def test_build_smart_ranges_merges_nearby_regions() -> None:
    regions = [
        SpeechRegion(0, 80_000),
        SpeechRegion(88_000, 160_000),
        SpeechRegion(400_000, 480_000),
    ]
    chunks = build_smart_ranges(
        regions,
        sample_rate=16_000,
        max_chunk_seconds=12,
        max_internal_gap_seconds=1,
    )
    assert chunks == [SpeechRegion(0, 160_000), SpeechRegion(400_000, 480_000)]


def test_padding_never_exceeds_limit() -> None:
    padded = apply_edge_padding(
        [SpeechRegion(0, 384_000)],
        sample_rate=16_000,
        total_samples=500_000,
        edge_padding_seconds=1,
        max_final_seconds=24.9,
    )
    assert (padded[0].end_sample - padded[0].start_sample) / 16_000 <= 24.9


def test_merge_removes_overlap_duplicate() -> None:
    first = ChunkRecord(1, Path("a.wav"), 0.0, 10.5)
    second = ChunkRecord(2, Path("b.wav"), 10.0, 20.0)
    text = merge_transcript_parts(
        [
            TranscriptPart(first, "Ерлан бала кезінен техникаға қызығатын"),
            TranscriptPart(second, "техникаға қызығатын кейін инженер болды"),
        ]
    )
    assert text == "Ерлан бала кезінен техникаға қызығатын кейін инженер болды"


def test_merge_preserves_human_repeat_without_audio_overlap() -> None:
    first = ChunkRecord(1, Path("a.wav"), 0.0, 10.0)
    second = ChunkRecord(2, Path("b.wav"), 10.1, 20.0)
    text = merge_transcript_parts(
        [
            TranscriptPart(first, "Ерлан Ерлан"),
            TranscriptPart(second, "Ерлан бала кезінен сабырлы"),
        ]
    )
    assert text == "Ерлан Ерлан Ерлан бала кезінен сабырлы"


def test_merge_does_not_fuzzy_delete_similar_words() -> None:
    first = ChunkRecord(1, Path("a.wav"), 0.0, 10.5)
    second = ChunkRecord(2, Path("b.wav"), 10.0, 20.0)
    text = merge_transcript_parts(
        [
            TranscriptPart(first, "Ол ауылға барды"),
            TranscriptPart(second, "ауылда қалды"),
        ]
    )
    assert text == "Ол ауылға барды ауылда қалды"


def test_merge_limits_removal_to_audio_overlap_capacity() -> None:
    first = ChunkRecord(1, Path("a.wav"), 0.0, 10.05)
    second = ChunkRecord(2, Path("b.wav"), 10.0, 20.0)
    text = merge_transcript_parts(
        [
            TranscriptPart(first, "one two three four five six"),
            TranscriptPart(second, "one two three four five six later"),
        ]
    )
    assert text == "one two three four five six one two three four five six later"


def test_empty_chunk_does_not_break_overlap_with_last_spoken_chunk() -> None:
    first = ChunkRecord(1, Path("a.wav"), 0.0, 10.5)
    empty = ChunkRecord(2, Path("b.wav"), 10.0, 10.2)
    third = ChunkRecord(3, Path("c.wav"), 10.3, 20.0)

    text = merge_transcript_parts(
        [
            TranscriptPart(first, "техникаға қызығатын"),
            TranscriptPart(empty, ""),
            TranscriptPart(third, "техникаға қызығатын кейін инженер болды"),
        ]
    )

    assert text == "техникаға қызығатын кейін инженер болды"
