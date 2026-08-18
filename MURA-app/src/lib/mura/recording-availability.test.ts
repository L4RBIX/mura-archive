/**
 * Capture and processing are different questions.
 *
 * The bug these tests lock down: a degraded recogniser used to disable the
 * microphone, and a signed-in user with a family was told "recording is not
 * allowed" for reasons that had nothing to do with their role.
 */

import { describe, expect, it } from "vitest";
import type { Capabilities, FamilyView } from "@/lib/mura/core-api";
import {
  canSubmitRecording,
  captureAvailability,
  processingAvailability,
  processingNotice,
  type MicrophoneState,
} from "@/lib/mura/recording-availability";

const MIC: MicrophoneState = { supported: true, permission: "granted" };

function family(capabilities: string[] = ["read_recordings", "create_recording"]): FamilyView {
  return { family_id: `family_${"a".repeat(32)}`, name: "A", role: "owner", capabilities };
}

function capabilities(overrides: Partial<Capabilities> = {}): Capabilities {
  return {
    schema_version: "core-capabilities-v1",
    status: "ready",
    recording: { enabled: true, mode: "audio" },
    asr: {
      registration: "registered",
      registered_at: null,
      registration_age_seconds: null,
      live_health_verified: false,
    },
    analysis: { configuration: "configured", live_health_verified: false },
    validation: { release_version: "v1" },
    ...overrides,
  };
}

const ready = { authSettled: true, signedIn: true, family: family(), microphone: MIC };

describe("capture availability", () => {
  it("allows a signed-in editor with a family and a microphone", () => {
    expect(captureAvailability(ready)).toEqual({ available: true });
  });

  it("reports the blocker the user can act on, in order", () => {
    expect(captureAvailability({ ...ready, authSettled: false }).available).toBe(false);
    expect(captureAvailability({ ...ready, authSettled: false })).toMatchObject({
      reason: "authenticating",
    });
    expect(captureAvailability({ ...ready, signedIn: false })).toMatchObject({
      reason: "sign_in_required",
    });
    expect(captureAvailability({ ...ready, family: null })).toMatchObject({
      reason: "family_required",
    });
    expect(
      captureAvailability({ ...ready, family: family(["read_recordings"]) }),
    ).toMatchObject({ reason: "role_forbidden" });
  });

  it("never reports a later blocker while an earlier one is unresolved", () => {
    // Saying "allow the microphone" to someone who is not signed in sends them
    // to the wrong settings screen.
    const stillLoading = captureAvailability({
      authSettled: false,
      signedIn: false,
      family: null,
      microphone: { supported: false, permission: "denied" },
    });

    expect(stillLoading).toMatchObject({ reason: "authenticating" });
  });

  it("reports browser and permission problems as themselves", () => {
    expect(
      captureAvailability({ ...ready, microphone: { supported: false, permission: "unknown" } }),
    ).toMatchObject({ reason: "browser_unsupported" });
    expect(
      captureAvailability({ ...ready, microphone: { supported: true, permission: "denied" } }),
    ).toMatchObject({ reason: "microphone_denied" });
  });

  it("does not block capture on an unqueried permission", () => {
    // The browser will prompt when the user taps record; refusing beforehand
    // would make the button unusable on engines without the Permissions API.
    expect(
      captureAvailability({ ...ready, microphone: { supported: true, permission: "prompt" } }),
    ).toEqual({ available: true });
    expect(
      captureAvailability({ ...ready, microphone: { supported: true, permission: "unknown" } }),
    ).toEqual({ available: true });
  });

  it("does not consult capabilities at all", () => {
    // Capture takes no capability argument by construction: an ASR outage
    // cannot reach this decision.
    expect(captureAvailability(ready)).toEqual({ available: true });
  });
});

describe("processing availability", () => {
  it("is ready when audio recording is enabled and analysis is configured", () => {
    expect(processingAvailability(capabilities(), true)).toBe("ready");
  });

  it("is queueable, not blocked, when the recogniser is degraded", () => {
    // Core keeps jobs in PostgreSQL with leases and backoff, so a recording
    // made now is processed when the recogniser returns.
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

    expect(processingAvailability(degraded, true)).toBe("degraded_queueable");
    expect(canSubmitRecording("degraded_queueable")).toBe(true);
    expect(processingNotice("degraded_queueable")).toBe("queued_later");
  });

  it("treats an unknown recogniser as degraded rather than healthy", () => {
    // Preserves the PR-02 rule that silence is never taken for health, without
    // escalating it into "you may not record".
    const unknown = capabilities({
      recording: { enabled: true, mode: "transcript_only" },
      asr: {
        registration: "unknown",
        registered_at: null,
        registration_age_seconds: null,
        live_health_verified: false,
      },
    });

    expect(processingAvailability(unknown, true)).toBe("degraded_queueable");
  });

  it("refuses submission when no analysis provider is configured", () => {
    // Queueing into a system that will never process is a promise the product
    // cannot keep.
    const unconfigured = capabilities({
      analysis: { configuration: "not_configured", live_health_verified: false },
    });

    expect(processingAvailability(unconfigured, true)).toBe("unconfigured");
    expect(canSubmitRecording("unconfigured")).toBe(false);
    expect(processingNotice("unconfigured")).toBe("unconfigured");
  });

  it("distinguishes an unreachable Core from a degraded recogniser", () => {
    expect(processingAvailability(null, true)).toBe("unavailable");
    expect(canSubmitRecording("unavailable")).toBe(false);
    expect(processingNotice("unavailable")).toBe("core_unreachable");
  });

  it("is unknown until capabilities resolve, and shows no notice yet", () => {
    expect(processingAvailability(null, false)).toBe("unknown");
    expect(processingNotice("unknown")).toBeNull();
    expect(processingNotice("ready")).toBeNull();
  });

  it("allows submission while capabilities are still unknown", () => {
    // Blocking here would make the record button flicker on every page load.
    expect(canSubmitRecording("unknown")).toBe(true);
  });
});
