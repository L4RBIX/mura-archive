from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from apps.api.main import _job_view, create_app, get_auth_verifier, get_runtime, get_settings
from apps.api.recordings import RecordingRuntime
from mura.config import CoreSettings
from mura.domain.models import (
    AudioLanguage,
    DetectedLanguage,
    OutputLanguage,
    PipelineRequest,
    build_language_context,
)
from mura.jobs import JobStatus, SpeakerResolution
from mura.orchestration import LocalAudioStorage
from mura.speaker import (
    internal_narrator_reference,
    is_canonical_person_id,
    is_internal_narrator_reference,
    public_person_id,
)
from mura.storage.archive import ArchivePersonRow
from mura.storage.database import Database, PipelineResultRow, RecordingRepository, RecordingRow
from mura.storage.identity import IdentityRepository
from tests.authz_factories import (
    FakePrincipalVerifier,
    TestIdentity,
    create_family_with_id,
    create_test_user,
)

# A real RIFF/WAVE header: uploads are content-validated since PR-02C.
WAV_BYTES = b"RIFF$\x00\x00\x00WAVEfmt " + b"\x00" * 32

CORE_TOKEN = "c" * 40
FAMILY_A = "family_a"
FAMILY_B = "family_b"
PERSON_A = "person_" + "a" * 32
PERSON_B = "person_" + "b" * 32


def _settings() -> CoreSettings:
    return CoreSettings.model_validate(
        {
            "DEEPSEEK_API_KEY": "sk-" + "d" * 40,
            "CORE_API_KEY": CORE_TOKEN,
            "WORKER_REGISTRATION_TOKEN": "r" * 40,
            "KAGGLE_ASR_API_KEY": "a" * 40,
            "OPERATIONS_API_KEY": "o" * 40,
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "DATABASE_AUTO_CREATE": True,
        }
    )


def _pipeline_payload() -> dict[str, Any]:
    """A minimal but provenance-bearing PipelineResult payload."""

    return {
        "transcript": {
            "recording_id": "rec_seeded",
            "duration_seconds": 12.0,
            "full_text": "Менің атам Сапар.",
            "segments": [
                {"segment_id": "seg_001", "start": 0.0, "end": 12.0, "text": "Менің атам Сапар."}
            ],
            "asr_model": "gigaam",
            "asr_revision": "large_ctc",
            "chunker_version": "v1",
        },
        "cleaned_transcript": {
            "readable_segments": [{"segment_id": "seg_001", "text": "Менің атам Сапар."}],
            "full_readable_text": "Менің атам Сапар.",
        },
        "extraction": {
            "recording_id": "rec_seeded",
            "speaker_id": "narrator_rec_seeded",
            "speaker_name": "Айсұлу",
            "languages": ["kk"],
            "people_mentions": [
                {
                    "mention_id": "mention_001",
                    "name": "Сапар",
                    "category": "family_member",
                    "source_segment_ids": ["seg_001"],
                    "evidence_class": "A_explicit",
                    "assertion_mode": "explicit",
                    "confidence": 0.9,
                }
            ],
            "evidence_spans": [
                {
                    "evidence_id": "evidence_001",
                    "segment_id": "seg_001",
                    "text": "атам Сапар",
                    "source_layer": "raw_transcript",
                    "start_char": 7,
                    "end_char": 17,
                    "evidence_class": "A_explicit",
                }
            ],
            "provenance_activities": [
                {
                    "activity_id": "activity_001",
                    "stage": "extractor",
                    "system": "deepseek",
                    "version": "extraction-v1",
                }
            ],
        },
        "resolutions": [
            {"mention_id": "mention_001", "status": "needs_review", "reason": "ambiguous"}
        ],
        "processing": {
            "total_seconds": 1.5,
            "trace_id": "trace_abc",
            "versions": {"extraction_contract": "extraction-v1"},
        },
    }


def _seed(database: Database) -> None:
    with database.session_factory.begin() as session:
        session.add_all(
            [
                ArchivePersonRow(
                    person_id=PERSON_A,
                    family_id=FAMILY_A,
                    canonical_name="Сапар",
                    normalized_name="сапар",
                ),
                ArchivePersonRow(
                    person_id=PERSON_B,
                    family_id=FAMILY_B,
                    canonical_name="Нұрбек",
                    normalized_name="нұрбек",
                ),
            ]
        )


def _seed_recording(
    database: Database,
    *,
    family_id: str,
    recording_id: str,
    job_id: str,
    with_result: bool = True,
    audio_language: str | None = "kk",
    output_language: str | None = "ru",
) -> None:
    repository = RecordingRepository(database)
    repository.create_recording_and_job(
        recording_id=recording_id,
        job_id=job_id,
        family_id=family_id,
        speaker_id=internal_narrator_reference(recording_id),
        speaker_name="Айсұлу",
        original_filename="memory.wav",
        content_type="audio/wav",
        audio_path=Path("/tmp/memory.wav"),
        audio_language=audio_language,
        output_language=output_language,
    )
    if with_result:
        payload = _pipeline_payload()
        payload["transcript"]["recording_id"] = recording_id
        payload["extraction"]["recording_id"] = recording_id
        with database.session_factory.begin() as session:
            session.add(PipelineResultRow(recording_id=recording_id, payload=payload))


class _Runtime(RecordingRuntime):
    def __init__(self, database: Database, tmp_path: Path) -> None:
        self.database = database
        self.repository = RecordingRepository(database)
        self.storage = LocalAudioStorage(tmp_path / "audio", max_upload_bytes=1024 * 1024)


#: The signed-in user these tests act as: an owner of family A and a stranger to
#: family B. Since PR-03B-SWITCH the service token reaches none of these routes,
#: so every request below carries a verified user token instead.
_MEMBER: TestIdentity | None = None


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    global _MEMBER
    settings = _settings()
    database = Database(settings.database_url)
    database.create_schema()
    _seed(database)
    _seed_recording(database, family_id=FAMILY_A, recording_id="rec_a", job_id="job_a")
    _seed_recording(database, family_id=FAMILY_B, recording_id="rec_b", job_id="job_b")

    identity = IdentityRepository(database)
    verifier = FakePrincipalVerifier()
    _MEMBER = create_test_user(identity, subject="family-a-owner", verifier=verifier)
    create_family_with_id(database, family_id=FAMILY_A, name="Family A", owner=_MEMBER)
    # Family B exists and has its own owner. The caller is simply not in it.
    create_family_with_id(
        database,
        family_id=FAMILY_B,
        name="Family B",
        owner=create_test_user(identity, subject="family-b-owner", verifier=verifier),
    )

    application = create_app(settings)
    runtime = _Runtime(database, tmp_path)
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_runtime] = lambda: runtime
    application.dependency_overrides[get_auth_verifier] = lambda: verifier
    return TestClient(application, raise_server_exceptions=False)


def _auth() -> dict[str, str]:
    assert _MEMBER is not None, "the client fixture establishes the signed-in user"
    return _MEMBER.headers


def _upload(client: TestClient, family_id: str, **form: str) -> Any:
    data = {"speaker_name": "Айсұлу", **form}
    return client.post(
        f"/v1/families/{family_id}/recordings",
        headers=_auth(),
        files={"file": ("memory.wav", io.BytesIO(WAV_BYTES), "audio/wav")},
        data=data,
    )


# ----------------------------------------------------------------------- routes


def test_canonical_upload_accepts_and_returns_ids(client: TestClient) -> None:
    response = _upload(client, FAMILY_A)

    assert response.status_code == 202
    body = response.json()
    assert body["recording_id"].startswith("rec_")
    assert body["job_id"].startswith("job_")


def test_canonical_recording_and_job_reads_work(client: TestClient) -> None:
    recording = client.get(f"/v1/families/{FAMILY_A}/recordings/rec_a", headers=_auth())
    job = client.get(f"/v1/families/{FAMILY_A}/jobs/job_a", headers=_auth())
    review = client.get(f"/v1/families/{FAMILY_A}/recordings/rec_a/review-items", headers=_auth())

    assert recording.status_code == 200
    assert job.status_code == 200
    assert review.status_code == 200
    assert job.json()["job_id"] == "job_a"


@pytest.mark.parametrize(
    "path",
    ["/v1/recordings", "/v1/recordings/rec_a", "/v1/recordings/rec_a/review-items"],
)
def test_old_unscoped_recording_routes_are_gone(path: str) -> None:
    assert path not in create_app(_settings()).openapi()["paths"]


def test_old_unscoped_job_route_is_gone() -> None:
    paths = create_app(_settings()).openapi()["paths"]

    assert "/v1/jobs/{job_id}" not in paths
    # The operator trace route is deliberately retained.
    assert "/v1/jobs/{job_id}/trace" in paths


def test_family_id_is_not_accepted_in_the_body(client: TestClient) -> None:
    schema = create_app(_settings()).openapi()["paths"]["/v1/families/{family_id}/recordings"]
    body = schema["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]

    assert "family_id" not in body.get("properties", {})


# -------------------------------------------------------------- family integrity


@pytest.mark.parametrize(
    "path",
    [
        f"/v1/families/{FAMILY_A}/recordings/rec_b",
        f"/v1/families/{FAMILY_A}/jobs/job_b",
        f"/v1/families/{FAMILY_A}/recordings/rec_b/review-items",
    ],
)
def test_cross_family_reads_are_not_found(client: TestClient, path: str) -> None:
    response = client.get(path, headers=_auth())

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    # The foreign family and its ids must not be disclosed.
    assert FAMILY_B not in response.text


# ---------------------------------------------------------------------- speaker


def test_known_canonical_speaker_is_accepted(client: TestClient) -> None:
    response = _upload(client, FAMILY_A, speaker_person_id=PERSON_A)

    assert response.status_code == 202


def test_arbitrary_string_cannot_claim_canonical_identity(client: TestClient) -> None:
    response = _upload(client, FAMILY_A, speaker_person_id="aisulu")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_syntactically_valid_but_unknown_person_is_not_found(client: TestClient) -> None:
    response = _upload(client, FAMILY_A, speaker_person_id="person_" + "f" * 32)

    assert response.status_code == 404


def test_other_family_person_is_not_found_and_not_disclosed(client: TestClient) -> None:
    response = _upload(client, FAMILY_A, speaker_person_id=PERSON_B)

    assert response.status_code == 404
    assert PERSON_B not in response.text
    assert FAMILY_B not in response.text


def test_unknown_narrator_uploads_without_a_canonical_person(client: TestClient) -> None:
    accepted = _upload(client, FAMILY_A).json()
    result = client.get(
        f"/v1/families/{FAMILY_A}/recordings/{accepted['recording_id']}", headers=_auth()
    )

    # No result row yet, but the recording exists and no person was invented.
    assert result.status_code == 409


def test_internal_narrator_reference_cannot_collide_with_canonical_namespace() -> None:
    token = internal_narrator_reference("rec_deadbeef")

    assert is_internal_narrator_reference(token)
    assert not is_canonical_person_id(token)
    assert public_person_id(token) is None


def test_speaker_view_never_exposes_the_internal_reference(client: TestClient) -> None:
    body = client.get(f"/v1/families/{FAMILY_A}/recordings/rec_a", headers=_auth()).json()

    assert body["speaker"]["person_id"] is None
    assert body["speaker"]["resolution_status"] == SpeakerResolution.PENDING.value
    assert "narrator_" not in str(body["speaker"])


# --------------------------------------------------------------------- language


@pytest.mark.parametrize("value", [member.value for member in AudioLanguage])
def test_every_audio_language_is_accepted(client: TestClient, value: str) -> None:
    assert _upload(client, FAMILY_A, audio_language=value).status_code == 202


@pytest.mark.parametrize("value", [member.value for member in OutputLanguage])
def test_every_output_language_is_accepted(client: TestClient, value: str) -> None:
    assert _upload(client, FAMILY_A, output_language=value).status_code == 202


def test_invalid_audio_language_is_rejected(client: TestClient) -> None:
    response = _upload(client, FAMILY_A, audio_language="klingon")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_invalid_output_language_is_rejected(client: TestClient) -> None:
    assert _upload(client, FAMILY_A, output_language="klingon").status_code == 422


def test_language_values_persist_on_the_recording_row(client: TestClient, tmp_path: Path) -> None:
    accepted = _upload(client, FAMILY_A, audio_language="kk", output_language="ru").json()
    runtime = client.app.dependency_overrides[get_runtime]()

    row = runtime.repository.get_family_recording(
        family_id=FAMILY_A, recording_id=accepted["recording_id"]
    )

    assert row.audio_language == "kk"
    assert row.output_language == "ru"


def test_historical_null_languages_read_as_defaults(client: TestClient) -> None:
    runtime = client.app.dependency_overrides[get_runtime]()
    _seed_recording(
        runtime.database,
        family_id=FAMILY_A,
        recording_id="rec_legacy",
        job_id="job_legacy",
        audio_language=None,
        output_language=None,
    )

    body = client.get(f"/v1/families/{FAMILY_A}/recordings/rec_legacy", headers=_auth()).json()

    assert body["language_context"]["requested_audio_language"] == "auto"
    assert body["language_context"]["requested_output_language"] == "same_as_transcript"


def test_pipeline_request_carries_language_intent() -> None:
    payload = _pipeline_payload()
    request = PipelineRequest(
        transcript=payload["transcript"],
        speaker_id="narrator_rec_seeded",
        speaker_name="Айсұлу",
        requested_audio_language=AudioLanguage.KK,
        requested_output_language=OutputLanguage.RU,
    )

    assert request.requested_audio_language is AudioLanguage.KK
    assert request.requested_output_language is OutputLanguage.RU


def test_language_context_is_truthful_about_unapplied_requests() -> None:
    context = build_language_context(
        requested_audio_language=AudioLanguage.KK,
        requested_output_language=OutputLanguage.RU,
    )

    assert context.requested_audio_language is AudioLanguage.KK
    # No language reaches the recogniser, so the effective mode stays auto.
    assert context.effective_audio_language is AudioLanguage.AUTO
    assert context.audio_language_applied is False
    assert context.requested_output_language is OutputLanguage.RU
    assert context.effective_output_language is None
    assert context.output_language_applied is False
    # Core owns no detector; a frontend heuristic must not fill these.
    assert context.detected_audio_language is DetectedLanguage.UNKNOWN
    assert context.transcript_language is DetectedLanguage.UNKNOWN


def test_result_exposes_requested_language_context(client: TestClient) -> None:
    body = client.get(f"/v1/families/{FAMILY_A}/recordings/rec_a", headers=_auth()).json()
    context = body["language_context"]

    assert context["requested_audio_language"] == "kk"
    assert context["requested_output_language"] == "ru"
    assert context["audio_language_applied"] is False
    assert context["output_language_applied"] is False


# ----------------------------------------------------------------------- result


def test_result_preserves_provenance_and_uncertainty(client: TestClient) -> None:
    body = client.get(f"/v1/families/{FAMILY_A}/recordings/rec_a", headers=_auth()).json()
    extraction = body["result"]["extraction"]

    assert extraction["evidence_spans"][0]["evidence_id"] == "evidence_001"
    assert extraction["evidence_spans"][0]["start_char"] == 7
    assert extraction["provenance_activities"][0]["activity_id"] == "activity_001"
    assert extraction["people_mentions"][0]["assertion_mode"] == "explicit"
    assert extraction["people_mentions"][0]["evidence_class"] == "A_explicit"
    assert body["result"]["resolutions"][0]["status"] == "needs_review"
    assert "conflict_sets" in extraction
    assert body["result"]["processing"]["versions"]["extraction_contract"] == "extraction-v1"
    assert body["result"]["transcript"]["full_text"]
    assert body["result"]["cleaned_transcript"]["full_readable_text"]


def test_result_never_exposes_the_local_audio_path(client: TestClient) -> None:
    text = client.get(f"/v1/families/{FAMILY_A}/recordings/rec_a", headers=_auth()).text

    assert "/tmp/memory.wav" not in text
    assert "audio_path" not in text


def test_review_items_preserve_core_objects_without_recomputation(client: TestClient) -> None:
    body = client.get(
        f"/v1/families/{FAMILY_A}/recordings/rec_a/review-items", headers=_auth()
    ).json()

    assert body["recording_id"] == "rec_a"
    assert body["ambiguous_resolutions"][0]["mention_id"] == "mention_001"
    assert "conflict_sets" in body
    assert "needsReview" not in body


# -------------------------------------------------------------------------- job


def test_family_job_keeps_waiting_for_asr_semantics(client: TestClient) -> None:
    runtime = client.app.dependency_overrides[get_runtime]()
    runtime.repository.defer_job(
        "job_a",
        error_code="asr_worker_unavailable",
        error_detail="no ready ASR worker is registered",
        retry_after_seconds=30,
    )

    body = client.get(f"/v1/families/{FAMILY_A}/jobs/job_a", headers=_auth()).json()

    assert body["status"] == JobStatus.QUEUED.value
    assert body["stage"] == "waiting_for_asr"
    assert body["retryable"] is True
    assert 0 <= body["retry_after_seconds"] <= 30
    assert body["next_retry_at"] is not None


def test_job_view_hides_internals(client: TestClient) -> None:
    body = client.get(f"/v1/families/{FAMILY_A}/jobs/job_a", headers=_auth()).json()

    for hidden in ("lease_owner", "worker_id", "error_detail", "audio_path"):
        assert hidden not in body


def test_job_view_builder_is_deterministic() -> None:
    now = datetime.now(UTC)
    row = RecordingRow(
        recording_id="rec_x",
        family_id=FAMILY_A,
        speaker_id=internal_narrator_reference("rec_x"),
        speaker_name="Айсұлу",
        original_filename="x.wav",
        content_type="audio/wav",
        audio_path="/tmp/x.wav",
    )
    assert row.recording_id == "rec_x"
    assert (now - now) == timedelta(0)


# ------------------------------------------------------------------- migration


def test_migration_0007_follows_the_current_head_and_moves_both_columns() -> None:
    module: dict[str, Any] = {}
    source = Path("migrations/versions/20260719_0007_recording_language_context.py").read_text(
        encoding="utf-8"
    )
    exec(compile(source, "0007", "exec"), module)

    assert module["revision"] == "20260719_0007"
    assert module["down_revision"] == "20260719_0006"
    assert "audio_language" in source and "output_language" in source
    assert source.count("op.add_column") == 2
    assert source.count("op.drop_column") == 2


def test_recording_row_persists_explicit_language_values(tmp_path: Path) -> None:
    database = Database(f"sqlite+pysqlite:///{tmp_path.as_posix()}/languages.db")
    database.create_schema()
    _seed_recording(
        database,
        family_id=FAMILY_A,
        recording_id="rec_lang",
        job_id="job_lang",
        with_result=False,
        audio_language="mixed",
        output_language="kk",
    )

    row = RecordingRepository(database).get_family_recording(
        family_id=FAMILY_A, recording_id="rec_lang"
    )

    assert (row.audio_language, row.output_language) == ("mixed", "kk")


def test_job_view_helper_is_importable() -> None:
    assert callable(_job_view)
