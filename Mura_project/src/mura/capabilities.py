"""Product capabilities the frontend needs in order to decide what to offer.

This endpoint must never call GigaAM or DeepSeek, so it cannot report verified
live health. It reports only what Core knows locally, and says so: a worker
registration proves that a worker once registered, not that it is reachable now,
and a configured provider key proves configuration, not health.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum

from mura.domain.models import StrictModel
from mura.release_control import CURRENT_RELEASE_ID


class CapabilityStatus(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class AsrRegistration(StrEnum):
    """What Core knows about the ASR worker. None of these assert liveness."""

    REGISTERED = "registered"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ProviderConfiguration(StrEnum):
    CONFIGURED = "configured"
    NOT_CONFIGURED = "not_configured"


class RecordingMode(StrEnum):
    AUDIO = "audio"
    TRANSCRIPT_ONLY = "transcript_only"
    UNAVAILABLE = "unavailable"


class AsrCapability(StrictModel):
    registration: AsrRegistration
    registered_at: datetime | None = None
    registration_age_seconds: int | None = None
    # There is no worker heartbeat, so Core cannot prove the worker is alive.
    live_health_verified: bool = False


class AnalysisCapability(StrictModel):
    configuration: ProviderConfiguration
    live_health_verified: bool = False


class RecordingCapability(StrictModel):
    enabled: bool
    mode: RecordingMode


class ValidationCapability(StrictModel):
    release_version: str


class CapabilitiesView(StrictModel):
    schema_version: str = "core-capabilities-v1"
    status: CapabilityStatus
    recording: RecordingCapability
    asr: AsrCapability
    analysis: AnalysisCapability
    validation: ValidationCapability


def derive_capabilities(
    *,
    asr_registration: AsrRegistration,
    asr_registered_at: datetime | None,
    analysis_configured: bool,
    now: datetime,
    release_version: str = CURRENT_RELEASE_ID,
) -> CapabilitiesView:
    """Map locally-known state onto product capabilities without asserting health."""

    analysis = (
        ProviderConfiguration.CONFIGURED
        if analysis_configured
        else ProviderConfiguration.NOT_CONFIGURED
    )
    registered = asr_registration is AsrRegistration.REGISTERED

    if not analysis_configured:
        mode = RecordingMode.UNAVAILABLE
        status = CapabilityStatus.UNAVAILABLE
    elif registered:
        mode = RecordingMode.AUDIO
        status = CapabilityStatus.READY
    else:
        # Audio needs the worker; a supplied transcript still analyses.
        mode = RecordingMode.TRANSCRIPT_ONLY
        status = CapabilityStatus.DEGRADED

    age: int | None = None
    if asr_registered_at is not None:
        age = max(0, math.floor((now - asr_registered_at).total_seconds()))

    return CapabilitiesView(
        status=status,
        recording=RecordingCapability(
            enabled=mode is not RecordingMode.UNAVAILABLE,
            mode=mode,
        ),
        asr=AsrCapability(
            registration=asr_registration,
            registered_at=asr_registered_at,
            registration_age_seconds=age,
        ),
        analysis=AnalysisCapability(configuration=analysis),
        validation=ValidationCapability(release_version=release_version),
    )
