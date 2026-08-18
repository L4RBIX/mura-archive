from __future__ import annotations

import argparse
import json
import tempfile
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from mura.domain.models import (
    CleanerResult,
    PipelineResult,
    RawSegment,
    ReadableSegment,
    TranscriptEnvelope,
)
from mura.extraction_sanitizer import sanitize_extraction_output
from mura.leases import new_worker_id
from mura.observability import (
    ProcessingTrace,
    ProcessingTraceEventRow,
    TraceOutcome,
    TraceRepository,
)
from mura.release_control import CURRENT_RELEASE_ID, ReleaseControlService
from mura.replay import FamilyReplayService, PipelineReplayRunRow
from mura.retention import RETENTION_CONFIRMATION, RetentionService
from mura.storage.completion import finalize_recording_job
from mura.storage.conflict_resolution import ConflictResolutionService
from mura.storage.database import Database, ProcessingJobRow, RecordingRepository, utcnow
from mura.storage.generic_claims import persist_generic_claims


def _synthetic_result() -> PipelineResult:
    transcript = TranscriptEnvelope(
        recording_id="rec_smoke",
        duration_seconds=2.0,
        full_text="Менің атым Күләш.",
        segments=[
            RawSegment(
                segment_id="seg_001",
                start=0,
                end=2,
                text="Менің атым Күләш.",
            )
        ],
        asr_model="synthetic-fixture",
        asr_revision="fixture-v1",
        chunker_version="fixture-v1",
    )
    extraction, issues, _ = sanitize_extraction_output(
        raw={
            "recording_id": "rec_smoke",
            "speaker_id": "speaker_smoke",
            "speaker_name": "Күләш",
            "languages": ["kk"],
            "provenance_activities": [],
            "evidence_spans": [],
            "coreference_links": [],
            "conflict_sets": [],
            "people_mentions": [],
            "relationship_claims": [],
            "events": [],
            "descriptions": [],
            "stories": [],
            "unresolved_questions": [],
        },
        transcript=transcript,
        speaker_id="speaker_smoke",
        speaker_name="Күләш",
    )
    if issues:
        raise RuntimeError(f"synthetic extraction is not clean: {issues}")
    return PipelineResult(
        transcript=transcript,
        cleaned_transcript=CleanerResult(
            readable_segments=[ReadableSegment(segment_id="seg_001", text="Менің атым Күләш.")],
            full_readable_text="Менің атым Күләш.",
        ),
        extraction=extraction,
        processing={
            "total_seconds": 0.25,
            "cleaner_usage": {
                "prompt_tokens": 120,
                "completion_tokens": 20,
                "total_tokens": 140,
            },
            "extractor_usage": {
                "prompt_tokens": 180,
                "completion_tokens": 30,
                "total_tokens": 210,
            },
        },
    )


def run_smoke(database_path: Path) -> dict[str, object]:
    database = Database(f"sqlite+pysqlite:///{database_path}")
    database.create_schema()
    repository = RecordingRepository(database)
    audio_path = database_path.with_suffix(".wav")
    audio_path.write_bytes(b"synthetic-audio-placeholder")
    repository.create_recording_and_job(
        recording_id="rec_smoke",
        job_id="job_smoke",
        family_id="family_smoke",
        speaker_id="speaker_smoke",
        speaker_name="Күләш",
        original_filename="smoke.wav",
        content_type="audio/wav",
        audio_path=audio_path,
    )
    claimed = repository.claim_next_job(lease_owner=new_worker_id(), lease_seconds=300)
    if claimed is None:
        raise RuntimeError("smoke job was not claimable")

    result = _synthetic_result()
    trace = ProcessingTrace(
        job_id="job_smoke",
        recording_id="rec_smoke",
        family_id="family_smoke",
        attempt=1,
    )
    trace.instant(stage="job", event_name="job_claimed", attributes={"attempt": 1})
    trace.start("archive_persistence")
    trace.finish(
        "archive_persistence",
        outcome=TraceOutcome.INFO,
        event_name="transaction_prepared",
    )
    recording = repository.get_recording("rec_smoke")
    if recording is None:
        raise RuntimeError("smoke recording disappeared")
    with database.session_factory.begin() as session:
        ConflictResolutionService.persist_pipeline_result(
            session,
            recording=recording,
            result=result,
        )
        persist_generic_claims(session, recording=recording, result=result)
        finalize_recording_job(
            session,
            job_id="job_smoke",
            result=result,
            trace_events=trace.events,
        )

    stored_result = repository.get_pipeline_result("rec_smoke")
    if stored_result is None:
        raise RuntimeError("smoke result was not persisted")
    completed_job = repository.get_job("job_smoke")
    if completed_job is None:
        raise RuntimeError("smoke job disappeared after completion")
    budget_payload = stored_result.processing.get("runtime_budget")
    budget_passed = isinstance(budget_payload, dict) and budget_payload.get("passed") is True
    trace_view = TraceRepository(database).get_job_trace(job_id="job_smoke")
    replay = FamilyReplayService(database).run(family_id="family_smoke")

    release_service = ReleaseControlService(database)
    initial_release = release_service.get_state()
    rolled_back = release_service.rollback(
        requested_by="release-smoke",
        note="verify rollback control path",
    )
    reactivated = release_service.activate(
        release_id=CURRENT_RELEASE_ID,
        requested_by="release-smoke",
        note="restore current release after rollback test",
    )

    old_time = utcnow() - timedelta(days=120)
    with database.session_factory.begin() as session:
        job = session.get(ProcessingJobRow, "job_smoke")
        if job is None:
            raise RuntimeError("smoke job disappeared before retention test")
        job.completed_at = old_time
        for event in session.scalars(select(ProcessingTraceEventRow)):
            event.created_at = old_time
        replay_row = session.get(PipelineReplayRunRow, replay.replay_id)
        if replay_row is None:
            raise RuntimeError("smoke replay was not persisted")
        replay_row.created_at = old_time
    retention_service = RetentionService(database)
    retention_preview = retention_service.preview()
    retention_applied = retention_service.apply(confirmation=RETENTION_CONFIRMATION)

    checks = {
        "job_completed": completed_job.status == "completed",
        "budget_passed": budget_passed,
        "trace_available": trace_view is not None and bool(trace_view.events),
        "replay_passed": replay.status == "passed",
        "rollback_requires_restart": rolled_back.state.restart_required,
        "release_restored": (
            reactivated.state.active_release_id == CURRENT_RELEASE_ID
            and reactivated.state.runtime_matches_desired
        ),
        "retention_preview_found_data": (
            retention_preview.expired_trace_events > 0 and retention_preview.expired_replay_runs > 0
        ),
        "retention_deleted_data": (
            retention_applied.deleted_trace_events > 0 and retention_applied.deleted_replay_runs > 0
        ),
    }
    passed = all(checks.values())
    return {
        "schema_version": "release-smoke-report-v1",
        "release_id": CURRENT_RELEASE_ID,
        "passed": passed,
        "checks": checks,
        "initial_release": initial_release.model_dump(mode="json"),
        "runtime_budget": budget_payload,
        "replay": replay.model_dump(mode="json"),
        "retention_preview": retention_preview.model_dump(mode="json"),
        "retention_applied": retention_applied.model_dump(mode="json"),
        "database_path": str(database_path),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Mura release candidate smoke test without external services."
    )
    parser.add_argument("--database-path", type=Path)
    parser.add_argument("--json-output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.database_path is None:
        with tempfile.TemporaryDirectory(prefix="mura-rc-smoke-") as directory:
            report = run_smoke(Path(directory) / "mura-smoke.db")
    else:
        args.database_path.parent.mkdir(parents=True, exist_ok=True)
        report = run_smoke(args.database_path)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
