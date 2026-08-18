/**
 * Screen state for a recording, and the capability signal that gates it.
 *
 * Two corrections since the Core realignment:
 *
 * 1. Capability is no longer read from `/v1/health`. That is an infrastructure
 *    liveness probe, not a product API. `/v1/capabilities` is authoritative.
 *
 * 2. An unknown capability no longer means healthy. The old code returned null
 *    on failure and treated null as "recording is fine", which told the user
 *    the service worked when Core could not establish that.
 */

import {
  WAITING_FOR_ASR_STAGE,
  type Capabilities,
  type JobView,
  type RecordingMode,
} from "@/lib/mura/core-api";

export type PipelineState =
  | "idle"
  | "recording"
  | "uploading"
  | "preprocessing"
  | "transcribing"
  | "extracting"
  | "validating"
  | "completed"
  | "degraded"
  | "failed";

/** States where nothing is in flight, so a new submission is allowed. */
export const RESTING_STATES: ReadonlySet<PipelineState> = new Set([
  "idle",
  "completed",
  "degraded",
  "failed",
]);

/** States where polling must continue. Anything else stops the timer. */
export const POLLING_STATES: ReadonlySet<PipelineState> = new Set([
  "uploading",
  "preprocessing",
  "transcribing",
  "extracting",
  "validating",
  // A deferred job is still queued in Core and will be retried automatically.
  "degraded",
]);

/**
 * What the app may offer right now.
 *
 * `unknown` is its own state precisely so it cannot be mistaken for `ready`.
 */
export type RecordingAvailability = "ready" | "transcript_only" | "unavailable" | "unknown";

export function recordingAvailability(
  capabilities: Capabilities | null,
): RecordingAvailability {
  if (capabilities === null) return "unknown";
  if (!capabilities.recording.enabled) return "unavailable";
  const mode: RecordingMode = capabilities.recording.mode;
  if (mode === "audio") return "ready";
  if (mode === "transcript_only") return "transcript_only";
  return "unavailable";
}

/**
 * True only when Core positively reports that audio can be processed.
 *
 * Unknown deliberately returns false: silence is not consent, and the previous
 * fail-open behaviour promised a working pipeline during an outage.
 */
export function canRecordLive(capabilities: Capabilities | null): boolean {
  return recordingAvailability(capabilities) === "ready";
}

/** Core reached, but audio capture cannot be served right now. */
export function isDegradedCapability(capabilities: Capabilities | null): boolean {
  return recordingAvailability(capabilities) === "transcript_only";
}

/**
 * A job Core has deferred and will retry by itself.
 *
 * There is no `deferred` status: Core keeps the job queued and marks the stage
 * and retry metadata instead, so all three signals are checked together.
 */
export function isAwaitingAutomaticRetry(job: JobView): boolean {
  return (
    job.status === "queued" && job.stage === WAITING_FOR_ASR_STAGE && job.retryable === true
  );
}

export function stateFromJob(job: JobView): PipelineState {
  if (isAwaitingAutomaticRetry(job)) return "degraded";
  switch (job.status) {
    case "completed":
      return "completed";
    case "failed":
      return "failed";
    case "transcribing":
      return "transcribing";
    case "cleaning":
    case "extracting":
      return "extracting";
    case "resolving":
      return "validating";
    case "queued":
      return job.stage.startsWith("window_") ? "extracting" : "preprocessing";
    default:
      return "preprocessing";
  }
}

/** Seconds until Core's own next attempt, or null when it is not retrying. */
export function retryCountdownSeconds(job: JobView): number | null {
  if (!isAwaitingAutomaticRetry(job)) return null;
  return job.retry_after_seconds ?? null;
}
