from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum

from pydantic import Field
from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from mura.domain.models import PipelineResult, StrictModel
from mura.observability import ProcessingTraceEvent
from mura.storage.database import Base, Database, utcnow
from mura.versioning import get_pipeline_versions

CURRENT_RELEASE_ID = "mura-core-v1.0.0-rc1"
PREVIOUS_RELEASE_ID = "mura-core-v0.9.0"
RELEASE_CONTROL_KEY = "global"


class ReleaseAction(StrEnum):
    ACTIVATE = "activate"
    ROLLBACK = "rollback"


class ReleaseBudgets(StrictModel):
    schema_version: str = "release-budgets-v1"
    maximum_pipeline_seconds: float = Field(default=180.0, gt=0)
    maximum_total_trace_seconds: float = Field(default=1080.0, gt=0)
    maximum_input_units: int = Field(default=120_000, ge=0)
    maximum_output_units: int = Field(default=30_000, ge=0)
    maximum_weighted_cost_units: int = Field(default=240_000, ge=0)
    maximum_people_per_recording: int = Field(default=250, ge=1)
    maximum_relationships_per_recording: int = Field(default=500, ge=1)


class ReleaseManifest(StrictModel):
    schema_version: str = "release-manifest-v1"
    release_id: str = Field(min_length=1, max_length=96)
    status: str
    runtime_compatibility_key: str
    pipeline_versions: dict[str, str]
    budgets: ReleaseBudgets
    replay_protocol: str = "deterministic-family-replay-v1"
    retention_protocol: str = "operational-retention-v1"
    notes: list[str] = Field(default_factory=list)


_CURRENT_MANIFEST = ReleaseManifest(
    release_id=CURRENT_RELEASE_ID,
    status="release_candidate",
    runtime_compatibility_key="mura-runtime-v1",
    pipeline_versions=get_pipeline_versions().model_dump(mode="json"),
    budgets=ReleaseBudgets(),
    notes=[
        "The offline composite gate includes frozen-provider end-to-end orchestration.",
        "Production promotion still requires a live approved-audio GigaAM and DeepSeek gate.",
        "Live ASR and LLM calls remain external and are not deterministic replay inputs.",
        "Rollback is a desired-release control-plane operation, not an in-process code swap.",
    ],
)

_PREVIOUS_MANIFEST = ReleaseManifest(
    release_id=PREVIOUS_RELEASE_ID,
    status="previous",
    runtime_compatibility_key="mura-runtime-v0.9",
    pipeline_versions=get_pipeline_versions().model_dump(mode="json"),
    budgets=ReleaseBudgets(),
    notes=[
        "This release requires deployment of its matching historical runtime.",
        "The current process must restart after this release becomes desired.",
    ],
)

_RELEASE_CATALOG = {
    _CURRENT_MANIFEST.release_id: _CURRENT_MANIFEST,
    _PREVIOUS_MANIFEST.release_id: _PREVIOUS_MANIFEST,
}


class ReleaseControlRow(Base):
    __tablename__ = "release_control"

    control_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    active_release_id: Mapped[str] = mapped_column(String(96), index=True)
    previous_release_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    generation: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class ReleaseDecisionRow(Base):
    __tablename__ = "release_decisions"

    decision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    from_release_id: Mapped[str] = mapped_column(String(96))
    to_release_id: Mapped[str] = mapped_column(String(96), index=True)
    requested_by: Mapped[str] = mapped_column(String(256))
    note: Mapped[str] = mapped_column(Text)
    generation: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReleaseStateView(StrictModel):
    schema_version: str = "release-state-v1"
    active_release_id: str
    previous_release_id: str | None
    runtime_release_id: str = CURRENT_RELEASE_ID
    generation: int = Field(ge=1)
    runtime_matches_desired: bool
    restart_required: bool
    active_manifest: ReleaseManifest
    available_releases: list[ReleaseManifest]
    updated_at: datetime


class ReleaseMutationResult(StrictModel):
    action: ReleaseAction
    changed: bool
    state: ReleaseStateView


class BudgetAssessment(StrictModel):
    schema_version: str = "runtime-budget-assessment-v1"
    release_id: str = CURRENT_RELEASE_ID
    passed: bool
    complete: bool
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    measurements: dict[str, int | float] = Field(default_factory=dict)
    limits: ReleaseBudgets


class ReleaseControlError(ValueError):
    pass


def release_catalog() -> list[ReleaseManifest]:
    return [manifest.model_copy(deep=True) for manifest in _RELEASE_CATALOG.values()]


def current_release_manifest() -> ReleaseManifest:
    return _CURRENT_MANIFEST.model_copy(deep=True)


def _usage_units(result: PipelineResult) -> tuple[int, int, list[str]]:
    input_units = 0
    output_units = 0
    warnings: list[str] = []
    for usage_name in ("cleaner_usage", "extractor_usage"):
        usage = result.processing.get(usage_name)
        if not isinstance(usage, dict):
            warnings.append(f"{usage_name} is missing")
            continue
        input_value = usage.get("prompt_tokens")
        output_value = usage.get("completion_tokens")
        if isinstance(input_value, int) and input_value >= 0:
            input_units += input_value
        else:
            warnings.append(f"{usage_name}.prompt_tokens is missing")
        if isinstance(output_value, int) and output_value >= 0:
            output_units += output_value
        else:
            warnings.append(f"{usage_name}.completion_tokens is missing")
    return input_units, output_units, warnings


def evaluate_runtime_budget(
    result: PipelineResult,
    trace_events: Sequence[ProcessingTraceEvent] = (),
    *,
    manifest: ReleaseManifest | None = None,
) -> BudgetAssessment:
    selected = manifest or current_release_manifest()
    limits = selected.budgets
    input_units, output_units, warnings = _usage_units(result)
    pipeline_value = result.processing.get("total_seconds")
    pipeline_seconds = float(pipeline_value) if isinstance(pipeline_value, (int, float)) else 0.0
    if not isinstance(pipeline_value, (int, float)):
        warnings.append("processing.total_seconds is missing")
    trace_seconds = sum((event.duration_ms or 0) for event in trace_events) / 1000
    weighted_cost_units = input_units + output_units * 4
    measurements: dict[str, int | float] = {
        "pipeline_seconds": pipeline_seconds,
        "total_trace_seconds": trace_seconds,
        "input_units": input_units,
        "output_units": output_units,
        "weighted_cost_units": weighted_cost_units,
        "people_count": len(result.extraction.people_mentions),
        "relationship_count": len(result.extraction.relationship_claims),
    }
    failures: list[str] = []

    def maximum(name: str, limit: int | float) -> None:
        value = measurements[name]
        if value > limit:
            failures.append(f"{name}={value} exceeds maximum {limit}")

    maximum("pipeline_seconds", limits.maximum_pipeline_seconds)
    maximum("total_trace_seconds", limits.maximum_total_trace_seconds)
    maximum("input_units", limits.maximum_input_units)
    maximum("output_units", limits.maximum_output_units)
    maximum("weighted_cost_units", limits.maximum_weighted_cost_units)
    maximum("people_count", limits.maximum_people_per_recording)
    maximum("relationship_count", limits.maximum_relationships_per_recording)
    return BudgetAssessment(
        release_id=selected.release_id,
        passed=not failures,
        complete=not warnings,
        failures=failures,
        warnings=warnings,
        measurements=measurements,
        limits=limits,
    )


def attach_runtime_budget(
    result: PipelineResult,
    trace_events: Sequence[ProcessingTraceEvent] = (),
) -> PipelineResult:
    assessment = evaluate_runtime_budget(result, trace_events)
    return result.model_copy(
        update={
            "processing": {
                **result.processing,
                "release_id": CURRENT_RELEASE_ID,
                "runtime_budget": assessment.model_dump(mode="json"),
            }
        }
    )


class ReleaseControlService:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _get_or_create(session: Session, *, lock: bool = False) -> ReleaseControlRow:
        statement = select(ReleaseControlRow).where(
            ReleaseControlRow.control_key == RELEASE_CONTROL_KEY
        )
        if lock:
            statement = statement.with_for_update()
        row = session.scalar(statement)
        if row is None:
            row = ReleaseControlRow(
                control_key=RELEASE_CONTROL_KEY,
                active_release_id=CURRENT_RELEASE_ID,
                previous_release_id=PREVIOUS_RELEASE_ID,
                generation=1,
            )
            session.add(row)
            session.flush()
        return row

    @staticmethod
    def _view(row: ReleaseControlRow) -> ReleaseStateView:
        manifest = _RELEASE_CATALOG.get(row.active_release_id)
        if manifest is None:
            raise ReleaseControlError(f"unknown active release: {row.active_release_id}")
        runtime_matches = row.active_release_id == CURRENT_RELEASE_ID
        return ReleaseStateView(
            active_release_id=row.active_release_id,
            previous_release_id=row.previous_release_id,
            generation=row.generation,
            runtime_matches_desired=runtime_matches,
            restart_required=not runtime_matches,
            active_manifest=manifest,
            available_releases=release_catalog(),
            updated_at=row.updated_at,
        )

    def get_state(self) -> ReleaseStateView:
        with self.database.session_factory.begin() as session:
            return self._view(self._get_or_create(session))

    def activate(
        self,
        *,
        release_id: str,
        requested_by: str,
        note: str,
    ) -> ReleaseMutationResult:
        if release_id not in _RELEASE_CATALOG:
            raise ReleaseControlError(f"unknown release: {release_id}")
        with self.database.session_factory.begin() as session:
            row = self._get_or_create(session, lock=True)
            previous = row.active_release_id
            changed = previous != release_id
            if changed:
                row.previous_release_id = previous
                row.active_release_id = release_id
                row.generation += 1
                row.updated_at = utcnow()
                self._append_decision(
                    session,
                    action=ReleaseAction.ACTIVATE,
                    from_release_id=previous,
                    to_release_id=release_id,
                    requested_by=requested_by,
                    note=note,
                    generation=row.generation,
                )
            session.flush()
            return ReleaseMutationResult(
                action=ReleaseAction.ACTIVATE,
                changed=changed,
                state=self._view(row),
            )

    def rollback(self, *, requested_by: str, note: str) -> ReleaseMutationResult:
        with self.database.session_factory.begin() as session:
            row = self._get_or_create(session, lock=True)
            target = row.previous_release_id
            if target is None:
                raise ReleaseControlError("no previous release is available")
            if target not in _RELEASE_CATALOG:
                raise ReleaseControlError(f"unknown previous release: {target}")
            previous = row.active_release_id
            row.active_release_id = target
            row.previous_release_id = previous
            row.generation += 1
            row.updated_at = utcnow()
            self._append_decision(
                session,
                action=ReleaseAction.ROLLBACK,
                from_release_id=previous,
                to_release_id=target,
                requested_by=requested_by,
                note=note,
                generation=row.generation,
            )
            session.flush()
            return ReleaseMutationResult(
                action=ReleaseAction.ROLLBACK,
                changed=True,
                state=self._view(row),
            )

    @staticmethod
    def _append_decision(
        session: Session,
        *,
        action: ReleaseAction,
        from_release_id: str,
        to_release_id: str,
        requested_by: str,
        note: str,
        generation: int,
    ) -> None:
        session.add(
            ReleaseDecisionRow(
                decision_id=f"release_decision_{uuid.uuid4().hex}",
                action=action.value,
                from_release_id=from_release_id,
                to_release_id=to_release_id,
                requested_by=requested_by,
                note=note,
                generation=generation,
            )
        )
