"""Whisper transcription: language handling and transcript contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from mura.asr.factory import ASRConfigurationError, build_asr_client
from mura.asr.language import read_languages
from mura.asr.whisper import WhisperASRClient
from mura.config import ASRProvider


class _Response:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self) -> object:
        return self._payload


class _Session:
    """Captures the outgoing request so the contract can be asserted on it."""

    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, **kwargs: object) -> _Response:
        self.calls.append({"url": url, **kwargs})
        return self.response


def _client(response: _Response) -> tuple[WhisperASRClient, _Session]:
    session = _Session(response)
    client = WhisperASRClient(
        api_key="k", base_url="https://api.example.com/v1", model="whisper-1", session=session
    )
    return client, session


MIXED = "Менің әжем Алматыда тұрды, потом мы поехали к ней летом"


def _payload(text: str = MIXED, language: str = "kk") -> dict[str, object]:
    return {
        "text": text,
        "language": language,
        "duration": 6.5,
        "segments": [
            {"id": 0, "start": 0.0, "end": 3.0, "text": "Менің әжем Алматыда тұрды,"},
            {"id": 1, "start": 3.0, "end": 6.5, "text": "потом мы поехали к ней летом"},
        ],
    }


def test_language_is_never_pinned_and_translation_is_never_requested(tmp_path: Path) -> None:
    audio = tmp_path / "a.webm"
    audio.write_bytes(b"x")
    client, session = _client(_Response(_payload()))

    client.transcribe(audio_path=audio, recording_id="rec_1")

    sent = session.calls[0]
    assert sent["url"].endswith("/audio/transcriptions")
    assert "translations" not in str(sent["url"])
    # The decisive assertion: forcing a language mangles code-switched speech.
    assert "language" not in sent["data"]


def test_code_switched_speech_is_reported_as_mixed(tmp_path: Path) -> None:
    audio = tmp_path / "a.webm"
    audio.write_bytes(b"x")
    client, _ = _client(_Response(_payload()))

    envelope = client.transcribe(audio_path=audio, recording_id="rec_1")

    assert envelope.asr_metadata["detected_language"] == "mixed"
    assert envelope.asr_metadata["mixed_language"] is True
    assert envelope.asr_metadata["transcript_languages"] == "kk,ru"
    assert envelope.language_hints == ["kk", "ru"]


def test_transcript_is_preserved_verbatim(tmp_path: Path) -> None:
    audio = tmp_path / "a.webm"
    audio.write_bytes(b"x")
    client, _ = _client(_Response(_payload()))

    envelope = client.transcribe(audio_path=audio, recording_id="rec_1")

    # Kazakh stays Kazakh and Russian stays Russian; nothing is normalised.
    assert envelope.full_text == MIXED
    assert len(envelope.segments) == 2
    assert envelope.segments[0].text.startswith("Менің")


def test_whisper_own_language_claim_is_kept_beside_the_reading(tmp_path: Path) -> None:
    audio = tmp_path / "a.webm"
    audio.write_bytes(b"x")
    client, _ = _client(_Response(_payload(language="ru")))

    envelope = client.transcribe(audio_path=audio, recording_id="rec_1")

    # Whisper said "ru"; the text shows both. The disagreement stays visible.
    assert envelope.asr_metadata["asr_reported_language"] == "ru"
    assert envelope.asr_metadata["detected_language"] == "mixed"


def test_empty_transcript_is_a_failure_not_an_empty_success(tmp_path: Path) -> None:
    audio = tmp_path / "a.webm"
    audio.write_bytes(b"x")
    client, _ = _client(_Response({"text": "   ", "language": "ru", "duration": 1.0}))

    with pytest.raises(Exception) as excinfo:
        client.transcribe(audio_path=audio, recording_id="rec_1")
    assert "empty transcript" in str(excinfo.value)


def test_missing_segments_still_produce_a_valid_envelope(tmp_path: Path) -> None:
    audio = tmp_path / "a.webm"
    audio.write_bytes(b"x")
    client, _ = _client(_Response({"text": MIXED, "language": "kk", "duration": 4.0}))

    envelope = client.transcribe(audio_path=audio, recording_id="rec_1")

    assert len(envelope.segments) == 1
    assert envelope.segments[0].text == MIXED


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (MIXED, "mixed"),
        ("Моя бабушка жила в Алматы, затем мы поехали к ней летом", "ru"),
        ("Менің әжем Алматыда тұрды", "kk"),
        ("Ол бізге келді", "kk"),
        ("", "unknown"),
    ],
)
def test_language_reading(text: str, expected: str) -> None:
    assert read_languages(text).detected == expected


@pytest.mark.parametrize(
    "text",
    [
        "Да, мы поехали к ней летом",
        "Те дни я помню",
        "Та встреча была давно",
    ],
)
def test_russian_particles_are_not_read_as_kazakh(text: str) -> None:
    """Unambiguous Russian must never be reported as code-switched.

    «да», «де», «та» and «те» are Kazakh clitics and also everyday Russian
    words. Treating them as Kazakh evidence claimed a language that was never
    spoken, which is the one thing language reporting must not do.
    """

    reading = read_languages(text)
    assert reading.detected == "ru"
    assert reading.mixed is False


class _WhisperSettings:
    asr_provider = ASRProvider.WHISPER
    asr_request_timeout_seconds = 900.0
    whisper_base_url = "https://api.example.com/v1"
    whisper_model = "whisper-1"
    whisper_api_key: str | None = None


def test_whisper_without_a_key_fails_at_construction() -> None:
    with pytest.raises(ASRConfigurationError):
        build_asr_client(_WhisperSettings())


def test_whisper_client_does_not_wait_for_a_registered_worker() -> None:
    settings = _WhisperSettings()
    settings.whisper_api_key = "k"
    client = build_asr_client(settings)
    assert client.requires_registered_worker is False
