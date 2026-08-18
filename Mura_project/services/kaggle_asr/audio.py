from __future__ import annotations

import json
import subprocess
from pathlib import Path

DEFAULT_MEDIA_TIMEOUT_SECONDS = 120.0


class AudioProcessingError(RuntimeError):
    pass


def _run_media_command(
    command: list[str],
    *,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioProcessingError("media processing timed out") from exc
    except OSError as exc:
        raise AudioProcessingError("media processing executable is unavailable") from exc


def convert_to_wav(
    input_path: Path,
    output_path: Path,
    sample_rate: int = 16_000,
    *,
    timeout_seconds: float = DEFAULT_MEDIA_TIMEOUT_SECONDS,
) -> None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-nostdin",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    process = _run_media_command(command, timeout_seconds=timeout_seconds)
    if process.returncode != 0:
        raise AudioProcessingError("ffmpeg could not decode the uploaded media")


def audio_duration_seconds(
    path: Path,
    *,
    timeout_seconds: float = DEFAULT_MEDIA_TIMEOUT_SECONDS,
) -> float:
    command = [
        "ffprobe",
        "-v",
        "quiet",
        "-protocol_whitelist",
        "file,pipe",
        "-print_format",
        "json",
        "-show_format",
        str(path),
    ]
    process = _run_media_command(command, timeout_seconds=timeout_seconds)
    if process.returncode != 0:
        raise AudioProcessingError("ffprobe could not inspect the uploaded media")
    try:
        duration = float(json.loads(process.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AudioProcessingError("ffprobe returned no valid duration") from exc
    if duration <= 0:
        raise AudioProcessingError("audio duration must be positive")
    return duration


def ffmpeg_version(*, timeout_seconds: float = 10.0) -> str:
    process = _run_media_command(["ffmpeg", "-version"], timeout_seconds=timeout_seconds)
    if process.returncode != 0 or not process.stdout.strip():
        raise AudioProcessingError("ffmpeg version could not be determined")
    return process.stdout.splitlines()[0].strip()
