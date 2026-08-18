"""Audio persistence behind a provider-neutral boundary.

The domain must not know where bytes physically live. Everything above this
module addresses audio by an opaque ``storage_key``; only an implementation
knows that a key maps to a file, a bucket object or anything else.

The key is always server-generated from canonical identifiers. An uploaded
filename is untrusted display metadata and never contributes to a path, which
is what keeps traversal and absolute-path injection impossible by construction.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Protocol

#: Read size for streaming. Audio is never loaded into memory whole.
CHUNK_BYTES = 1024 * 1024

#: Canonical identifiers are the only things allowed into a key.
_SAFE_SEGMENT = re.compile(r"\A[A-Za-z0-9_-]{1,128}\Z")

ALLOWED_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".mp4",
    ".aac",
    ".ogg",
    ".opus",
    ".webm",
    ".flac",
}

ALLOWED_CONTENT_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/aac",
    "audio/ogg",
    "audio/opus",
    "audio/webm",
    "audio/flac",
    "audio/x-flac",
    "video/mp4",
    "video/webm",
}


class AudioStorageBackend(StrEnum):
    LOCAL = "local"


class AudioStorageError(ValueError):
    """Upload rejected before anything durable was written."""


class AudioTooLargeError(AudioStorageError):
    pass


class UnsupportedAudioError(AudioStorageError):
    pass


@dataclass(frozen=True)
class StoredAudio:
    """Durable, truthful facts about one stored object."""

    storage_key: str
    backend: AudioStorageBackend
    sha256: str
    size_bytes: int
    content_type: str


def safe_extension(original_filename: str) -> str:
    """Extension from an untrusted filename, validated against the allowlist."""

    suffix = Path(Path(original_filename or "audio.bin").name).suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise UnsupportedAudioError(f"unsupported audio extension: {suffix or '<none>'}")
    return suffix


def validate_content_type(content_type: str | None) -> str:
    if content_type is None or not content_type.strip():
        return "application/octet-stream"
    declared = content_type.split(";", 1)[0].strip().lower()
    if declared not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedAudioError(f"unsupported audio content type: {declared}")
    return declared


def sniff_container(head: bytes) -> str | None:
    """Identify the container from its header bytes.

    This is header sniffing, not decoding: it proves the file begins like a
    known audio container, which is enough to reject an arbitrary binary named
    ``.wav``. It does not prove the stream is fully valid or playable -- that
    would need a real decoder pass.
    """

    if len(head) < 12:
        return None
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"fLaC":
        return "flac"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:3] == b"ID3" or (head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "mp3"
    if head[4:8] == b"ftyp":
        return "mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    return None


#: Which containers may legitimately carry a given extension.
_EXTENSION_CONTAINERS: dict[str, set[str]] = {
    ".wav": {"wav"},
    ".mp3": {"mp3"},
    ".flac": {"flac"},
    ".ogg": {"ogg"},
    ".opus": {"ogg"},
    ".m4a": {"mp4"},
    ".mp4": {"mp4"},
    ".aac": {"mp3", "mp4"},
    ".webm": {"webm"},
}


def validate_container(extension: str, head: bytes) -> str | None:
    """Reject a payload whose header contradicts its extension."""

    container = sniff_container(head)
    if container is None:
        raise UnsupportedAudioError("audio content does not match a supported container")
    expected = _EXTENSION_CONTAINERS.get(extension, set())
    if expected and container not in expected:
        raise UnsupportedAudioError("audio content does not match its file extension")
    return container


def build_storage_key(*, family_id: str, recording_id: str, extension: str) -> str:
    """Server-generated key. Only canonical identifiers reach it."""

    for segment in (family_id, recording_id):
        if not _SAFE_SEGMENT.fullmatch(segment):
            raise AudioStorageError("storage key segments must be canonical identifiers")
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise UnsupportedAudioError(f"unsupported audio extension: {extension}")
    return f"family/{family_id}/recordings/{recording_id}/original{extension}"


class AudioStorage(Protocol):
    """The contract the domain depends on. No filesystem concepts appear here."""

    backend: AudioStorageBackend

    def save(
        self,
        *,
        family_id: str,
        recording_id: str,
        original_filename: str,
        content_type: str | None,
        source: BinaryIO,
    ) -> StoredAudio: ...

    def exists(self, storage_key: str) -> bool: ...

    def delete(self, storage_key: str) -> bool: ...

    def open(self, storage_key: str) -> BinaryIO: ...

    def materialize(self, storage_key: str) -> AbstractContextManager[Path]: ...


class LocalAudioStorage:
    """Filesystem implementation for local development and tests.

    The mapping from key to path lives here and nowhere else. A future object
    store implements the same protocol without the rest of the system changing.
    """

    backend = AudioStorageBackend.LOCAL

    def __init__(self, root: Path, *, max_upload_bytes: int) -> None:
        self.root = Path(root).resolve()
        self.max_upload_bytes = max_upload_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        # Keys are server-generated, but resolve and re-check anyway so a
        # corrupted row can never escape the storage root.
        candidate = (self.root / storage_key).resolve()
        if self.root not in candidate.parents:
            raise AudioStorageError("storage key escapes the storage root")
        return candidate

    def save(
        self,
        *,
        family_id: str,
        recording_id: str,
        original_filename: str,
        content_type: str | None,
        source: BinaryIO,
    ) -> StoredAudio:
        extension = safe_extension(original_filename)
        declared = validate_content_type(content_type)
        storage_key = build_storage_key(
            family_id=family_id,
            recording_id=recording_id,
            extension=extension,
        )
        destination = self._path(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".uploading")

        digest = hashlib.sha256()
        total = 0
        head = b""
        try:
            with temporary.open("wb") as output:
                while chunk := source.read(CHUNK_BYTES):
                    if not head:
                        head = chunk[:16]
                        # Reject a mislabelled payload before writing more of it.
                        validate_container(extension, head)
                    total += len(chunk)
                    if total > self.max_upload_bytes:
                        raise AudioTooLargeError(
                            "audio exceeds maximum upload size of "
                            f"{self.max_upload_bytes // (1024 * 1024)} MB"
                        )
                    # Hashed in the same streaming pass; never re-read.
                    digest.update(chunk)
                    output.write(chunk)
            if not total:
                raise UnsupportedAudioError("audio upload was empty")
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        return StoredAudio(
            storage_key=storage_key,
            backend=self.backend,
            sha256=digest.hexdigest(),
            size_bytes=total,
            content_type=declared,
        )

    def exists(self, storage_key: str) -> bool:
        return self._path(storage_key).is_file()

    def delete(self, storage_key: str) -> bool:
        """Idempotent: an already-absent object is not an error.

        A permission or provider failure still raises, so a genuine problem is
        never mistaken for "already deleted".
        """

        path = self._path(storage_key)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        # Prune now-empty recording/family directories, best effort.
        for parent in (path.parent, path.parent.parent):
            try:
                parent.rmdir()
            except OSError:
                break
        return True

    def open(self, storage_key: str) -> BinaryIO:
        return self._path(storage_key).open("rb")

    @contextmanager
    def materialize(self, storage_key: str) -> Iterator[Path]:
        """Expose a local file for providers that still require one.

        This is the single sanctioned place where a key becomes a Path. The
        Kaggle ASR worker uploads a file, so the boundary lives here rather than
        leaking a Path into the domain. An object-store implementation would
        download to a temporary file and clean it up on exit.
        """

        yield self._path(storage_key)


@contextmanager
def materialize_legacy_path(audio_path: str) -> Iterator[Path]:
    """Escape hatch for recordings created before storage keys existed."""

    yield Path(audio_path)


def copy_stream(source: BinaryIO, destination: BinaryIO) -> int:
    shutil.copyfileobj(source, destination, CHUNK_BYTES)
    return destination.tell()
