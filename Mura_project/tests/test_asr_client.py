from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mura.asr import ASRClientError, RemoteASRClient


class FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> Any:
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.last_url: str | None = None
        self.last_headers: dict[str, str] | None = None

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.last_url = url
        self.last_headers = kwargs["headers"]
        return self.response


def _transcript_payload() -> dict[str, Any]:
    return {
        "recording_id": "rec_1",
        "duration_seconds": 2.0,
        "full_text": "сәлем",
        "segments": [
            {
                "segment_id": "seg_001",
                "start": 0,
                "end": 2,
                "text": "сәлем",
            }
        ],
        "asr_model": "gigaam",
        "asr_revision": "large_ctc",
        "chunker_version": "v1",
    }


def test_remote_asr_client_validates_worker_contract(tmp_path: Path) -> None:
    audio = tmp_path / "story.wav"
    audio.write_bytes(b"audio")
    session = FakeSession(FakeResponse(200, _transcript_payload()))
    client = RemoteASRClient(api_key="secret", session=session)  # type: ignore[arg-type]

    result = client.transcribe(
        worker_url="https://worker.example",
        audio_path=audio,
        recording_id="rec_1",
        content_type="audio/wav",
    )

    assert result.recording_id == "rec_1"
    assert session.last_url == "https://worker.example/v1/transcribe"
    assert session.last_headers == {"Authorization": "Bearer secret"}


def test_remote_asr_client_marks_503_as_retryable(tmp_path: Path) -> None:
    audio = tmp_path / "story.wav"
    audio.write_bytes(b"audio")
    client = RemoteASRClient(
        api_key="secret",
        session=FakeSession(FakeResponse(503, {"detail": "loading"})),  # type: ignore[arg-type]
    )

    with pytest.raises(ASRClientError) as caught:
        client.transcribe(
            worker_url="https://worker.example",
            audio_path=audio,
            recording_id="rec_1",
        )

    assert caught.value.retryable is True
    assert caught.value.status_code == 503
