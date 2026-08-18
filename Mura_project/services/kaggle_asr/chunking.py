from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

CHUNKER_VERSION = "silero-smart-v2-exact-overlap"


@dataclass(frozen=True)
class SpeechRegion:
    start_sample: int
    end_sample: int

    def __post_init__(self) -> None:
        if self.start_sample < 0 or self.end_sample <= self.start_sample:
            raise ValueError("speech region must have a non-negative start and positive length")


@dataclass(frozen=True)
class ChunkRecord:
    index: int
    path: Path
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class TranscriptPart:
    chunk: ChunkRecord
    text: str


@dataclass(frozen=True)
class MergeDiagnostics:
    overlap_boundaries: int = 0
    duplicate_words_removed: int = 0
    empty_parts_skipped: int = 0


def build_smart_ranges(
    regions: list[SpeechRegion],
    *,
    sample_rate: int,
    max_chunk_seconds: float = 22.0,
    max_internal_gap_seconds: float = 1.2,
) -> list[SpeechRegion]:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if not regions:
        return []

    ordered = sorted(regions, key=lambda item: item.start_sample)
    current_start = ordered[0].start_sample
    current_end = ordered[0].end_sample
    output: list[SpeechRegion] = []

    for region in ordered[1:]:
        proposed_duration = (region.end_sample - current_start) / sample_rate
        gap = max(0.0, (region.start_sample - current_end) / sample_rate)
        if proposed_duration <= max_chunk_seconds and gap <= max_internal_gap_seconds:
            current_end = max(current_end, region.end_sample)
        else:
            output.append(SpeechRegion(current_start, current_end))
            current_start, current_end = region.start_sample, region.end_sample

    output.append(SpeechRegion(current_start, current_end))
    return output


def apply_edge_padding(
    ranges: list[SpeechRegion],
    *,
    sample_rate: int,
    total_samples: int,
    edge_padding_seconds: float = 0.45,
    max_final_seconds: float = 24.9,
) -> list[SpeechRegion]:
    if sample_rate <= 0 or total_samples <= 0:
        raise ValueError("sample_rate and total_samples must be positive")
    padding = int(edge_padding_seconds * sample_rate)
    padded: list[SpeechRegion] = []

    for region in ranges:
        start = max(0, region.start_sample - padding)
        end = min(total_samples, region.end_sample + padding)
        if (end - start) / sample_rate > max_final_seconds:
            overflow = (end - start) - int(max_final_seconds * sample_rate)
            trim_left = overflow // 2
            trim_right = overflow - trim_left
            start += trim_left
            end -= trim_right
        padded.append(SpeechRegion(start, end))

    return padded


def _normalize_word(word: str) -> str:
    return re.sub(r"[^\w]+", "", word.casefold(), flags=re.UNICODE)


def _exact_overlap_size(
    previous_words: list[str],
    current_words: list[str],
    *,
    maximum: int,
) -> int:
    for size in range(maximum, 1, -1):
        old_tail = [_normalize_word(word) for word in previous_words[-size:]]
        new_head = [_normalize_word(word) for word in current_words[:size]]
        if all(old_tail) and old_tail == new_head:
            return size
    return 0


def merge_transcript_parts_with_diagnostics(
    parts: list[TranscriptPart],
    *,
    max_overlap_words: int = 8,
    maximum_words_per_second: float = 5.0,
) -> tuple[str, MergeDiagnostics]:
    """Merge chunk transcripts without fuzzy deletion of genuine human repetition."""
    if not parts:
        return "", MergeDiagnostics()

    ordered = sorted(parts, key=lambda part: (part.chunk.start, part.chunk.index))
    merged = ""
    previous: TranscriptPart | None = None
    overlap_boundaries = 0
    duplicate_words_removed = 0
    empty_parts_skipped = 0

    for current in ordered:
        new_text = current.text.strip()
        if not new_text:
            empty_parts_skipped += 1
            continue
        if not merged:
            merged = new_text
            previous = current
            continue

        overlap_size = 0
        if previous is not None:
            overlap_seconds = max(0.0, previous.chunk.end - current.chunk.start)
            if overlap_seconds > 0:
                overlap_boundaries += 1
                old_words = merged.split()
                new_words = new_text.split()
                acoustic_limit = max(2, int(overlap_seconds * maximum_words_per_second) + 1)
                maximum = min(max_overlap_words, acoustic_limit, len(old_words), len(new_words))
                overlap_size = _exact_overlap_size(old_words, new_words, maximum=maximum)
                duplicate_words_removed += overlap_size
                if overlap_size:
                    new_text = " ".join(new_words[overlap_size:])

        if new_text:
            merged = f"{merged} {new_text}".strip()
        previous = current

    return merged, MergeDiagnostics(
        overlap_boundaries=overlap_boundaries,
        duplicate_words_removed=duplicate_words_removed,
        empty_parts_skipped=empty_parts_skipped,
    )


def merge_transcript_parts(
    parts: list[TranscriptPart],
    *,
    max_overlap_words: int = 8,
) -> str:
    merged, _ = merge_transcript_parts_with_diagnostics(
        parts,
        max_overlap_words=max_overlap_words,
    )
    return merged
