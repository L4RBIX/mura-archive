import { describe, expect, it } from "vitest";
import type { Capabilities, JobView } from "@/lib/mura/core-api";
import {
  canRecordLive,
  isAwaitingAutomaticRetry,
  isDegradedCapability,
  recordingAvailability,
  retryCountdownSeconds,
  stateFromJob,
} from "@/lib/mura/pipeline-state";

function capabilities(overrides: Partial<Capabilities> = {}): Capabilities {
  return {
    schema_version: "core-capabilities-v1",
    status: "ready",
    recording: { enabled: true, mode: "audio" },
    asr: {
      registration: "registered",
      registered_at: "2026-08-17T12:00:00Z",
      registration_age_seconds: 300,
      live_health_verified: false,
    },
    analysis: { configuration: "configured", live_health_verified: false },
    validation: { release_version: "mura-core-v1.0.0-rc1" },
    ...overrides,
  };
}

function job(overrides: Partial<JobView> = {}): JobView {
  return {
    job_id: "job_1",
    recording_id: "rec_1",
    status: "queued",
    stage: "queued",
    attempts: 0,
    retryable: false,
    retry_after_seconds: null,
    next_retry_at: null,
    error_code: null,
    created_at: "2026-08-17T12:00:00Z",
    started_at: null,
    completed_at: null,
    updated_at: "2026-08-17T12:00:00Z",
    ...overrides,
  };
}

describe("capability gating", () => {
  it("allows live recording only when Core reports audio mode", () => {
    expect(canRecordLive(capabilities())).toBe(true);
    expect(recordingAvailability(capabilities())).toBe("ready");
  });

  it("never treats unknown capability as healthy", () => {
    // The old code returned null on failure and let null mean "fine".
    expect(canRecordLive(null)).toBe(false);
    expect(recordingAvailability(null)).toBe("unknown");
  });

  it("degrades to transcript only when no worker is registered", () => {
    const degraded = capabilities({
      status: "degraded",
      recording: { enabled: true, mode: "transcript_only" },
      asr: {
        registration: "unavailable",
        registered_at: null,
        registration_age_seconds: null,
        live_health_verified: false,
      },
    });

    expect(canRecordLive(degraded)).toBe(false);
    expect(isDegradedCapability(degraded)).toBe(true);
  });

  it("reports unavailable when recording is disabled", () => {
    const off = capabilities({
      status: "unavailable",
      recording: { enabled: false, mode: "unavailable" },
    });

    expect(recordingAvailability(off)).toBe("unavailable");
  });

  it("does not depend on the diagnostic registration age", () => {
    const stale = capabilities({
      asr: {
        registration: "registered",
        registered_at: "2020-01-01T00:00:00Z",
        registration_age_seconds: 99_999_999,
        live_health_verified: false,
      },
    });

    // Kaggle-era diagnostics must not change product behaviour.
    expect(canRecordLive(stale)).toBe(canRecordLive(capabilities()));
  });
});

describe("job mapping", () => {
  it("maps waiting_for_asr to the degraded auto-retry state", () => {
    const deferred = job({
      stage: "waiting_for_asr",
      retryable: true,
      retry_after_seconds: 15,
      next_retry_at: "2026-08-17T12:00:15Z",
    });

    expect(isAwaitingAutomaticRetry(deferred)).toBe(true);
    expect(stateFromJob(deferred)).toBe("degraded");
    expect(retryCountdownSeconds(deferred)).toBe(15);
  });

  it("does not treat ordinary queued work as awaiting retry", () => {
    expect(isAwaitingAutomaticRetry(job())).toBe(false);
    expect(stateFromJob(job())).toBe("preprocessing");
    expect(retryCountdownSeconds(job())).toBeNull();
  });

  it("has no deferred status in the canonical contract", () => {
    const statuses: JobView["status"][] = [
      "queued",
      "transcribing",
      "cleaning",
      "extracting",
      "resolving",
      "completed",
      "failed",
    ];

    expect(statuses).not.toContain("deferred" as never);
  });

  it("maps the remaining canonical statuses", () => {
    expect(stateFromJob(job({ status: "transcribing" }))).toBe("transcribing");
    expect(stateFromJob(job({ status: "cleaning" }))).toBe("extracting");
    expect(stateFromJob(job({ status: "extracting" }))).toBe("extracting");
    expect(stateFromJob(job({ status: "resolving" }))).toBe("validating");
    expect(stateFromJob(job({ status: "completed" }))).toBe("completed");
    expect(stateFromJob(job({ status: "failed" }))).toBe("failed");
  });

  it("keeps long-form window stages in the extracting state", () => {
    expect(stateFromJob(job({ stage: "window_2_extracting" }))).toBe("extracting");
  });
});
