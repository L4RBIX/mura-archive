from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from mura.storage.audio import (
    AudioStorageBackend,
    AudioStorageError,
    AudioTooLargeError,
    LocalAudioStorage,
    UnsupportedAudioError,
    build_storage_key,
    sniff_container,
)
from mura.storage.database import Database, RecordingRepository, RecordingRow
from mura.storage.deletion import RecordingDeletionService
from mura.storage.recording_audio import is_legacy_recording, materialize_recording_audio

FAMILY = "family_a"
RECORDING = "rec_" + "a" * 32

# Minimal but genuine container headers.
WAV = b"RIFF$\x00\x00\x00WAVEfmt " + b"\x00" * 32
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 32
OGG = b"OggS" + b"\x00" * 32


@pytest.fixture
def storage(tmp_path: Path) -> LocalAudioStorage:
    return LocalAudioStorage(tmp_path / "audio", max_upload_bytes=1024 * 1024)


def _save(storage: LocalAudioStorage, payload: bytes, name: str, mime: str = "audio/wav"):
    return storage.save(
        family_id=FAMILY,
        recording_id=RECORDING,
        original_filename=name,
        content_type=mime,
        source=io.BytesIO(payload),
    )


# ------------------------------------------------------------------- keys


def test_storage_key_is_server_generated_from_canonical_ids() -> None:
    key = build_storage_key(family_id=FAMILY, recording_id=RECORDING, extension=".wav")

    assert key == f"family/{FAMILY}/recordings/{RECORDING}/original.wav"


@pytest.mark.parametrize(
    "family",
    ["../../etc", "family/../..", "C:\\Windows", "family id", "", "a" * 200],
)
def test_storage_key_rejects_non_canonical_segments(family: str) -> None:
    with pytest.raises(AudioStorageError):
        build_storage_key(family_id=family, recording_id=RECORDING, extension=".wav")


def test_uploaded_filename_never_becomes_the_storage_path(
    storage: LocalAudioStorage,
) -> None:
    stored = _save(storage, WAV, "../../../evil.wav")

    assert "evil" not in stored.storage_key
    assert ".." not in stored.storage_key
    assert stored.storage_key.endswith("original.wav")


# --------------------------------------------------------------- integrity


def test_save_records_truthful_hash_size_and_mime(storage: LocalAudioStorage) -> None:
    payload = WAV + b"\x01\x02\x03"

    stored = _save(storage, payload, "memory.wav", "audio/wav")

    assert stored.sha256 == hashlib.sha256(payload).hexdigest()
    assert stored.size_bytes == len(payload)
    assert stored.content_type == "audio/wav"
    assert stored.backend is AudioStorageBackend.LOCAL


def test_identical_uploads_are_not_deduplicated(storage: LocalAudioStorage) -> None:
    first = _save(storage, WAV, "a.wav")
    second = storage.save(
        family_id=FAMILY,
        recording_id="rec_" + "b" * 32,
        original_filename="a.wav",
        content_type="audio/wav",
        source=io.BytesIO(WAV),
    )

    # Same bytes, two intentional recordings: hash is integrity, not identity.
    assert first.sha256 == second.sha256
    assert first.storage_key != second.storage_key


def test_streaming_size_limit_is_enforced_and_leaves_nothing_behind(
    tmp_path: Path,
) -> None:
    small = LocalAudioStorage(tmp_path / "audio", max_upload_bytes=64)

    with pytest.raises(AudioTooLargeError):
        _save(small, WAV + b"\x00" * 4096, "big.wav")

    assert list((tmp_path / "audio").rglob("*.uploading")) == []


# -------------------------------------------------------------- validation


@pytest.mark.parametrize("name", ["memory.txt", "memory.exe", "memory"])
def test_unsupported_extension_is_rejected(storage: LocalAudioStorage, name: str) -> None:
    with pytest.raises(UnsupportedAudioError):
        _save(storage, WAV, name)


def test_unsupported_declared_mime_is_rejected(storage: LocalAudioStorage) -> None:
    with pytest.raises(UnsupportedAudioError):
        _save(storage, WAV, "memory.wav", "application/x-msdownload")


def test_arbitrary_binary_named_wav_is_rejected(storage: LocalAudioStorage) -> None:
    # Content sniffing, not extension trust: MZ is a Windows executable.
    with pytest.raises(UnsupportedAudioError):
        _save(storage, b"MZ\x90\x00" + b"\x00" * 64, "memory.wav")


def test_container_extension_mismatch_is_rejected(storage: LocalAudioStorage) -> None:
    with pytest.raises(UnsupportedAudioError):
        _save(storage, OGG, "memory.wav")


def test_matching_container_is_accepted(storage: LocalAudioStorage) -> None:
    stored = _save(storage, WEBM, "memory.webm", "audio/webm")

    assert stored.storage_key.endswith("original.webm")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [(WAV, "wav"), (WEBM, "webm"), (OGG, "ogg"), (b"fLaC" + b"\x00" * 16, "flac")],
)
def test_container_sniffing_identifies_known_headers(payload: bytes, expected: str) -> None:
    assert sniff_container(payload) == expected


def test_empty_upload_is_rejected(storage: LocalAudioStorage) -> None:
    with pytest.raises(UnsupportedAudioError):
        _save(storage, b"", "memory.wav")


# ------------------------------------------------------- read/exists/delete


def test_stored_audio_can_be_read_back_and_materialized(
    storage: LocalAudioStorage,
) -> None:
    stored = _save(storage, WAV, "memory.wav")

    assert storage.exists(stored.storage_key)
    with storage.open(stored.storage_key) as handle:
        assert handle.read() == WAV
    with storage.materialize(stored.storage_key) as path:
        assert path.is_file()


def test_delete_is_idempotent(storage: LocalAudioStorage) -> None:
    stored = _save(storage, WAV, "memory.wav")

    assert storage.delete(stored.storage_key) is True
    # Already absent is not a failure.
    assert storage.delete(stored.storage_key) is False
    assert storage.exists(stored.storage_key) is False


# ------------------------------------------------------------ legacy rows


def _database() -> Database:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    return database


def test_legacy_recording_resolves_through_the_audio_path(
    tmp_path: Path, storage: LocalAudioStorage
) -> None:
    legacy_file = tmp_path / "legacy.wav"
    legacy_file.write_bytes(WAV)
    recording = RecordingRow(
        recording_id="rec_legacy",
        family_id=FAMILY,
        speaker_id="narrator_rec_legacy",
        speaker_name="Айсұлу",
        original_filename="legacy.wav",
        content_type="audio/wav",
        audio_path=str(legacy_file),
    )

    assert is_legacy_recording(recording) is True
    with materialize_recording_audio(recording, storage) as path:
        assert path.read_bytes() == WAV


def test_canonical_recording_resolves_through_storage(storage: LocalAudioStorage) -> None:
    stored = _save(storage, WAV, "memory.wav")
    recording = RecordingRow(
        recording_id=RECORDING,
        family_id=FAMILY,
        speaker_id=f"narrator_{RECORDING}",
        speaker_name="Айсұлу",
        original_filename="memory.wav",
        content_type="audio/wav",
        audio_path=stored.storage_key,
        storage_key=stored.storage_key,
    )

    assert is_legacy_recording(recording) is False
    with materialize_recording_audio(recording, storage) as path:
        assert path.read_bytes() == WAV


# ---------------------------------------------------------------- deletion


def test_deletion_removes_rows_and_audio_and_is_idempotent(
    storage: LocalAudioStorage,
) -> None:
    database = _database()
    stored = _save(storage, WAV, "memory.wav")
    RecordingRepository(database).create_recording_and_job(
        recording_id=RECORDING,
        job_id="job_" + "a" * 32,
        family_id=FAMILY,
        speaker_id=f"narrator_{RECORDING}",
        speaker_name="Айсұлу",
        original_filename="memory.wav",
        content_type="audio/wav",
        audio_path=stored.storage_key,
        storage_key=stored.storage_key,
        storage_backend=stored.backend.value,
    )
    service = RecordingDeletionService(database, storage)

    first = service.delete_recording(family_id=FAMILY, recording_id=RECORDING)
    second = service.delete_recording(family_id=FAMILY, recording_id=RECORDING)

    assert first.rows_deleted is True
    assert first.audio_deleted is True
    assert storage.exists(stored.storage_key) is False
    # Repeating the lifecycle job must be safe.
    assert second.rows_deleted is False


def test_deletion_is_family_scoped(storage: LocalAudioStorage) -> None:
    database = _database()
    stored = _save(storage, WAV, "memory.wav")
    RecordingRepository(database).create_recording_and_job(
        recording_id=RECORDING,
        job_id="job_" + "c" * 32,
        family_id=FAMILY,
        speaker_id=f"narrator_{RECORDING}",
        speaker_name="Айсұлу",
        original_filename="memory.wav",
        content_type="audio/wav",
        audio_path=stored.storage_key,
        storage_key=stored.storage_key,
    )
    service = RecordingDeletionService(database, storage)

    result = service.delete_recording(family_id="family_other", recording_id=RECORDING)

    assert result.rows_deleted is False
    assert storage.exists(stored.storage_key) is True
