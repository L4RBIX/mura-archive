/**
 * Whether the user may record, and — separately — what will happen to it.
 *
 * These were one question and should never have been. "Can this browser capture
 * audio into an authorized family?" and "can the pipeline analyse it right
 * now?" have different inputs and different answers, and merging them meant a
 * degraded recogniser silently disabled the microphone.
 *
 * Capture depends on the user: signed in, a family they may write to, a browser
 * that can record, and microphone permission.
 *
 * Processing depends on the deployment: Core reachable, and a recogniser
 * configured and reachable. Core queues durably — jobs are rows in PostgreSQL
 * with leases and backoff — so a recording submitted while the recogniser is
 * merely unreachable is not lost, it waits. That is why degraded processing
 * still permits capture and submission.
 *
 * The one case that genuinely blocks submission is an *unconfigured* pipeline:
 * queueing into a system that will never process is a promise the product
 * cannot keep. Unknown is treated as degraded rather than ready, preserving the
 * PR-02 rule that silence is never taken for health.
 */

import type { Capabilities } from "@/lib/mura/core-api";
import type { FamilyView } from "@/lib/mura/core-api";
import { CREATE_RECORDING, familyAllows } from "@/lib/mura/family-session";

export type CaptureBlocker =
  | "authenticating"
  | "sign_in_required"
  | "family_required"
  | "role_forbidden"
  | "browser_unsupported"
  | "microphone_denied"
  | "microphone_missing";

export type CaptureAvailability =
  | { available: true }
  | { available: false; reason: CaptureBlocker };

export type ProcessingAvailability =
  /** Recogniser registered and analysis configured. */
  | "ready"
  /** Core is up and will queue the job; analysis catches up later. */
  | "degraded_queueable"
  /** Nothing can process this deployment's recordings at all. */
  | "unconfigured"
  /** Core itself could not be reached, so nothing can be submitted. */
  | "unavailable"
  /** Capabilities have not resolved yet. */
  | "unknown";

export interface MicrophoneState {
  supported: boolean;
  permission: "granted" | "denied" | "prompt" | "unknown";
}

export interface CaptureInputs {
  signedIn: boolean;
  authSettled: boolean;
  family: FamilyView | null;
  microphone: MicrophoneState;
}

export function captureAvailability(inputs: CaptureInputs): CaptureAvailability {
  // Order matters: report the first thing the user could actually act on, and
  // never report a later blocker while an earlier one is still unresolved.
  if (!inputs.authSettled) return { available: false, reason: "authenticating" };
  if (!inputs.signedIn) return { available: false, reason: "sign_in_required" };
  if (!inputs.family) return { available: false, reason: "family_required" };
  if (!familyAllows(inputs.family, CREATE_RECORDING)) {
    return { available: false, reason: "role_forbidden" };
  }
  if (!inputs.microphone.supported) return { available: false, reason: "browser_unsupported" };
  if (inputs.microphone.permission === "denied") {
    return { available: false, reason: "microphone_denied" };
  }
  return { available: true };
}

export function processingAvailability(
  capabilities: Capabilities | null,
  resolved: boolean,
): ProcessingAvailability {
  if (!resolved) return "unknown";
  // Capabilities could not be read at all: Core is the only thing that serves
  // them, so this is a Core problem rather than a recogniser problem.
  if (capabilities === null) return "unavailable";

  // No analysis provider configured means a queued job would never complete.
  if (capabilities.analysis.configuration === "not_configured") return "unconfigured";

  if (capabilities.recording.enabled && capabilities.recording.mode === "audio") {
    return "ready";
  }
  // Registered-but-not-audio, unavailable or unknown recogniser: Core still
  // accepts the upload and keeps the job queued with backoff.
  return "degraded_queueable";
}

/** Submission is refused only when nothing could ever process the result. */
export function canSubmitRecording(processing: ProcessingAvailability): boolean {
  return processing !== "unconfigured" && processing !== "unavailable";
}

/**
 * Does the user need to be told something before recording?
 *
 * Returns null when the pipeline is healthy, so the common case shows no
 * banner at all.
 */
export function processingNotice(
  processing: ProcessingAvailability,
): "queued_later" | "unconfigured" | "core_unreachable" | null {
  switch (processing) {
    case "degraded_queueable":
      return "queued_later";
    case "unconfigured":
      return "unconfigured";
    case "unavailable":
      return "core_unreachable";
    default:
      return null;
  }
}
