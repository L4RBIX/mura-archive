from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from services.kaggle_asr import artifacts as asr_artifacts
from services.kaggle_asr import audio, tunnel
from services.kaggle_asr.artifacts import (
    GIGAAM_MODEL_COMMIT,
    GIGAAM_MODEL_VARIANT,
    SILERO_VAD_VERSION,
    safe_model_metadata,
    snapshot_artifacts,
    validate_artifact_pins,
)
from services.kaggle_asr.model import GigaAMTranscriber


def test_model_revision_is_immutable_and_variant_is_explicit() -> None:
    validate_artifact_pins()
    assert len(GIGAAM_MODEL_COMMIT) == 40
    assert GIGAAM_MODEL_VARIANT == "large_ctc"
    assert GigaAMTranscriber.revision == GIGAAM_MODEL_COMMIT
    assert GigaAMTranscriber.model_variant == "large_ctc"


def test_snapshot_artifacts_hashes_code_config_and_weights(tmp_path: Path) -> None:
    contents = {
        "config.json": b"config",
        "modeling_gigaam.py": b"code",
        "pytorch_model.bin": b"weights",
    }
    for name, content in contents.items():
        (tmp_path / name).write_bytes(content)

    artifacts = snapshot_artifacts(tmp_path)

    assert artifacts.file_sha256 == {
        name: hashlib.sha256(content).hexdigest() for name, content in contents.items()
    }
    metadata = safe_model_metadata(artifacts, chunk_count=2)
    assert metadata["model_commit"] == GIGAAM_MODEL_COMMIT
    assert metadata["model_variant"] == "large_ctc"
    assert metadata["vad_version"] == SILERO_VAD_VERSION
    assert metadata["chunk_count"] == 2


def test_snapshot_artifacts_rejects_missing_remote_code(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pytorch_model.bin").write_bytes(b"weights")

    with pytest.raises(RuntimeError, match=r"modeling_gigaam\.py"):
        snapshot_artifacts(tmp_path)


def test_snapshot_download_uses_exact_immutable_revision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name, content in {
        "config.json": b"config",
        "modeling_gigaam.py": b"code",
        "model.safetensors": b"weights",
    }.items():
        (tmp_path / name).write_bytes(content)
    captured: dict[str, Any] = {}

    def fake_snapshot_download(**kwargs: Any) -> str:
        captured.update(kwargs)
        return str(tmp_path)

    monkeypatch.setattr(asr_artifacts, "_snapshot_download", fake_snapshot_download)

    artifacts = asr_artifacts.download_pinned_snapshot(token="token")

    assert artifacts.snapshot_path == tmp_path
    assert captured == {
        "repo_id": "ai-sage/GigaAM-Multilingual",
        "revision": GIGAAM_MODEL_COMMIT,
        "token": "token",
    }


def test_convert_to_wav_uses_bounded_noninteractive_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    audio.convert_to_wav(tmp_path / "input.mp3", tmp_path / "output.wav", timeout_seconds=5)

    assert "-nostdin" in captured["command"]
    assert captured["command"][captured["command"].index("-protocol_whitelist") + 1] == "file,pipe"
    assert captured["kwargs"]["timeout"] == 5
    assert captured["kwargs"]["check"] is False


def test_ffprobe_uses_local_protocol_allowlist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, '{"format":{"duration":"1.0"}}', "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert audio.audio_duration_seconds(tmp_path / "input.wav") == 1.0
    assert captured["command"][captured["command"].index("-protocol_whitelist") + 1] == (
        "file,pipe"
    )


def test_media_timeout_is_redacted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def timeout(*_args: Any, **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd="ffmpeg secret-path", timeout=1)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(audio.AudioProcessingError, match="timed out") as caught:
        audio.convert_to_wav(tmp_path / "private-name.mp3", tmp_path / "out.wav", timeout_seconds=1)
    assert "private-name" not in str(caught.value)


def test_cloudflared_download_requires_pinned_checksum(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    binary = tmp_path / "cloudflared"
    monkeypatch.setattr(tunnel, "CLOUDFLARED_SHA256", hashlib.sha256(b"trusted").hexdigest())
    monkeypatch.setattr(
        tunnel.requests,
        "get",
        lambda *_args, **_kwargs: SimpleNamespace(
            content=b"trusted",
            raise_for_status=lambda: None,
        ),
    )

    assert tunnel.ensure_cloudflared(binary) == binary
    assert binary.read_bytes() == b"trusted"
    # The executable bit is the deployment half of this invariant and is
    # asserted only where it can exist. NTFS has no POSIX execute bit, so
    # `Path.chmod(0o755)` there only clears the read-only flag and this would
    # fail on Windows for a reason that says nothing about the code. The
    # supply-chain half -- the pinned checksum -- is asserted on every
    # platform, above, and the worker itself runs on Linux.
    if os.name == "posix":
        assert binary.stat().st_mode & 0o111


def test_cloudflared_rejects_untrusted_existing_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    binary = tmp_path / "cloudflared"
    binary.write_bytes(b"tampered")
    monkeypatch.setattr(tunnel, "CLOUDFLARED_SHA256", hashlib.sha256(b"trusted").hexdigest())

    with pytest.raises(RuntimeError, match="checksum"):
        tunnel.ensure_cloudflared(binary)
