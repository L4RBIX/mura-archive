"""One place that resolves a recording's audio, wherever it lives.

Both the worker and replay used to reach into ``RecordingRow.audio_path`` and
build a filesystem Path. That is the coupling this module removes: callers ask
for audio by recording, and the storage boundary decides how to produce it.

Legacy rows are handled here too, so the fallback exists once rather than being
re-implemented by every caller.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from mura.storage.audio import AudioStorage, materialize_legacy_path
from mura.storage.database import RecordingRow


def is_legacy_recording(recording: RecordingRow) -> bool:
    """True for recordings created before storage keys existed."""

    return not recording.storage_key


@contextmanager
def materialize_recording_audio(
    recording: RecordingRow,
    storage: AudioStorage | None,
) -> Iterator[Path]:
    """Yield a local file for providers that still require one.

    This is the only sanctioned key-to-Path conversion outside the storage
    implementation itself. The Kaggle ASR worker uploads a file, so the
    conversion happens at the provider boundary; the domain keeps working in
    storage keys. A future object store materialises to a temporary file here
    and cleans it up on exit, with no caller change.
    """

    if is_legacy_recording(recording):
        with materialize_legacy_path(recording.audio_path) as path:
            yield path
        return
    if storage is None:
        raise RuntimeError("a storage backend is required to resolve this recording")
    with storage.materialize(recording.storage_key or "") as path:
        yield path
