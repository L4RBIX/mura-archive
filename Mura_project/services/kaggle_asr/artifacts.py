from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

GIGAAM_MODEL_ID = "ai-sage/GigaAM-Multilingual"
GIGAAM_MODEL_VARIANT = "large_ctc"
# Immutable Hugging Face commit backing the large_ctc variant used by Mura.
GIGAAM_MODEL_COMMIT = "ac7c6db08133f83478451a659f8470ee8ab47a2d"
SILERO_VAD_PACKAGE = "silero-vad"
SILERO_VAD_VERSION = "6.2.1"
REMOTE_CODE_POLICY = "immutable_hf_commit_local_snapshot_v1"
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class SnapshotArtifacts:
    snapshot_path: Path
    file_sha256: dict[str, str]

    def metadata(self) -> dict[str, str]:
        values = {
            "model_id": GIGAAM_MODEL_ID,
            "model_variant": GIGAAM_MODEL_VARIANT,
            "model_commit": GIGAAM_MODEL_COMMIT,
            "remote_code_policy": REMOTE_CODE_POLICY,
        }
        values.update(
            {f"artifact_sha256:{name}": digest for name, digest in self.file_sha256.items()}
        )
        return values


def validate_artifact_pins() -> None:
    if not _SHA_PATTERN.fullmatch(GIGAAM_MODEL_COMMIT):
        raise RuntimeError("GigaAM model revision must be an immutable 40-character commit SHA")


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(chunk_size):
            digest.update(block)
    return digest.hexdigest()


def snapshot_artifacts(snapshot_path: Path) -> SnapshotArtifacts:
    expected_names = (
        "config.json",
        "modeling_gigaam.py",
        "pytorch_model.bin",
        "model.safetensors",
        "tokenizer.model",
    )
    digests: dict[str, str] = {}
    for name in expected_names:
        candidate = snapshot_path / name
        if candidate.is_file():
            digests[name] = sha256_file(candidate)
    if "config.json" not in digests or "modeling_gigaam.py" not in digests:
        raise RuntimeError("GigaAM snapshot is missing config.json or modeling_gigaam.py")
    if not ({"pytorch_model.bin", "model.safetensors"} & digests.keys()):
        raise RuntimeError("GigaAM snapshot contains no supported model weight artifact")
    return SnapshotArtifacts(snapshot_path=snapshot_path, file_sha256=digests)


def _snapshot_download(*, repo_id: str, revision: str, token: str | None = None) -> str:
    """Load the optional Hugging Face client only in the live ASR environment."""
    try:
        from huggingface_hub import snapshot_download
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "huggingface-hub is required for ASR model download; install the kaggle extra"
        ) from exc
    return str(
        snapshot_download(
            repo_id=repo_id,
            revision=revision,
            token=token,
        )
    )


def download_pinned_snapshot(*, token: str | None = None) -> SnapshotArtifacts:
    validate_artifact_pins()
    path = Path(
        _snapshot_download(
            repo_id=GIGAAM_MODEL_ID,
            revision=GIGAAM_MODEL_COMMIT,
            token=token,
        )
    )
    return snapshot_artifacts(path)


def installed_silero_version() -> str:
    try:
        return metadata.version(SILERO_VAD_PACKAGE)
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError("silero-vad is not installed") from exc


def verify_silero_version() -> str:
    installed = installed_silero_version()
    if installed != SILERO_VAD_VERSION:
        raise RuntimeError(
            f"silero-vad version mismatch: expected {SILERO_VAD_VERSION}, found {installed}"
        )
    return installed


def safe_model_metadata(
    artifacts: SnapshotArtifacts,
    **extra: Any,
) -> dict[str, str | int | float | bool]:
    result: dict[str, str | int | float | bool] = dict(artifacts.metadata())
    result["vad_package"] = SILERO_VAD_PACKAGE
    result["vad_version"] = SILERO_VAD_VERSION
    for key, value in extra.items():
        if isinstance(value, (str, int, float, bool)):
            result[key] = value
    return result
