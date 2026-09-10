"""The single place that decides which recogniser the worker uses.

Nothing else in the codebase may read `settings.asr_provider`. Keeping the
decision here is what makes a provider cutover one edit instead of a search for
the one forgotten branch still calling the retired recogniser.

An unconfigured provider fails here, at construction, rather than at the first
recording. A worker that starts cleanly and then rejects every job looks healthy
to every dashboard while quietly losing family memories.
"""

from __future__ import annotations

from typing import Protocol

from mura.asr.client import RemoteASRClient
from mura.asr.whisper import WhisperASRClient
from mura.config import ASRProvider


class ASRConfigurationError(RuntimeError):
    """The selected provider cannot be built from the current settings."""


class ASRClient(Protocol):
    """What the orchestrator needs from any recogniser."""

    #: True for a tunnelled worker that must register itself before it can be
    #: reached; False for a recogniser addressed directly over HTTPS.
    requires_registered_worker: bool


def build_asr_client(settings: object) -> RemoteASRClient | WhisperASRClient:
    provider = getattr(settings, "asr_provider", ASRProvider.KAGGLE)
    timeout = float(getattr(settings, "asr_request_timeout_seconds", 900.0))

    if provider is ASRProvider.WHISPER:
        api_key = getattr(settings, "whisper_api_key", None)
        if not api_key:
            raise ASRConfigurationError(
                "ASR_PROVIDER=whisper requires WHISPER_API_KEY"
            )
        return WhisperASRClient(
            api_key=api_key,
            base_url=getattr(settings, "whisper_base_url", "https://api.openai.com/v1"),
            model=getattr(settings, "whisper_model", "whisper-1"),
            timeout_seconds=timeout,
        )

    return RemoteASRClient(
        api_key=getattr(settings, "kaggle_asr_api_key", ""),
        timeout_seconds=timeout,
    )
