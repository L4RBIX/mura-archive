from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from pydantic import ValidationError

from mura.domain.models import TranscriptEnvelope


@dataclass(frozen=True)
class ASRClientError(RuntimeError):
    message: str
    retryable: bool = False
    status_code: int | None = None

    def __str__(self) -> str:
        return self.message


class RemoteASRClient:
    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 900,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def transcribe(
        self,
        *,
        worker_url: str,
        audio_path: Path,
        recording_id: str,
        content_type: str | None = None,
    ) -> TranscriptEnvelope:
        url = f"{worker_url.rstrip('/')}/v1/transcribe"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            with audio_path.open("rb") as audio_file:
                response = self.session.post(
                    url,
                    headers=headers,
                    data={"recording_id": recording_id},
                    files={
                        "file": (
                            audio_path.name,
                            audio_file,
                            content_type or "application/octet-stream",
                        )
                    },
                    timeout=(20, self.timeout_seconds),
                )
        except (OSError, requests.RequestException) as exc:
            raise ASRClientError(
                f"ASR worker is unreachable: {exc}",
                retryable=True,
            ) from exc

        if response.status_code >= 400:
            detail = self._response_detail(response)
            retryable = response.status_code in {408, 409, 425, 429} or response.status_code >= 500
            raise ASRClientError(
                f"ASR worker returned HTTP {response.status_code}: {detail}",
                retryable=retryable,
                status_code=response.status_code,
            )

        try:
            payload: Any = response.json()
            return TranscriptEnvelope.model_validate(payload)
        except (ValueError, ValidationError) as exc:
            raise ASRClientError(
                f"ASR worker returned an invalid transcript contract: {exc}",
                retryable=False,
                status_code=response.status_code,
            ) from exc

    @staticmethod
    def _response_detail(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text[:1000]
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("error")
            if detail:
                return str(detail)[:1000]
        return str(payload)[:1000]
