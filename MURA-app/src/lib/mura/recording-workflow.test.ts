/**
 * The workflow-scope invariant.
 *
 * A recording submitted under family A must stay under family A through
 * submission, job polling, the result fetch and review — even if the user
 * switches the global family selection while it processes.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchJob,
  fetchRecordingResult,
  fetchReviewItems,
  submitRecording,
} from "@/lib/mura/core-api";
import { familyScopedKey, processingHref, readWorkflow } from "@/lib/mura/recording-workflow";
import { currentSpeakerPersonId } from "@/lib/mura/scope";

const A = `family_${"a".repeat(32)}`;
const B = `family_${"b".repeat(32)}`;
const RECORDING = `rec_${"a".repeat(32)}`;
const JOB = `job_${"b".repeat(32)}`;
const MEMORY = "local-1234";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function captureFetch() {
  const spy = vi.fn(async () => jsonResponse({ ok: true }));
  vi.stubGlobal("fetch", spy);
  return () => spy.mock.calls.map((call) => String((call as unknown as [string])[0]));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("workflow scope travels with the recording", () => {
  it("pins the family into the processing link", () => {
    const href = processingHref({
      jobId: JOB,
      recordingId: RECORDING,
      memoryId: MEMORY,
      familyId: A,
    });

    expect(readWorkflow(new URL(href, "https://app.example").searchParams)).toEqual({
      jobId: JOB,
      recordingId: RECORDING,
      memoryId: MEMORY,
      familyId: A,
    });
  });

  it("refuses a workflow that is missing its family rather than guessing one", () => {
    const params = new URLSearchParams({ job: JOB, recording: RECORDING, memory: MEMORY });

    expect(readWorkflow(params)).toBeNull();
  });

  it("keeps every downstream call on the captured family after a switch", async () => {
    const urls = captureFetch();
    // The workflow was captured under A.
    const workflow = readWorkflow(
      new URL(
        processingHref({
          jobId: JOB,
          recordingId: RECORDING,
          memoryId: MEMORY,
          familyId: A,
        }),
        "https://app.example",
      ).searchParams,
    );
    expect(workflow).not.toBeNull();

    // Meanwhile the user switched the global selection to B. Every call below
    // still uses the workflow's own family.
    const selectedFamilyId = B;
    await fetchJob(workflow!.jobId, workflow!.familyId);
    await fetchRecordingResult(workflow!.recordingId, workflow!.familyId);
    await fetchReviewItems(workflow!.recordingId, workflow!.familyId);

    for (const url of urls()) {
      expect(url).toContain(A);
      expect(url).not.toContain(selectedFamilyId);
    }
  });
});

describe("core requests carry an authorized family and nothing else", () => {
  it("never routes through a hardcoded transitional family", async () => {
    const urls = captureFetch();

    await submitRecording(
      {
        audio: new Blob(["x"]),
        filename: "memory.webm",
        speakerName: "Айсұлу",
        speakerPersonId: currentSpeakerPersonId(),
        audioLanguage: "auto",
        outputLanguage: "same_as_transcript",
      },
      A,
    );
    await fetchJob(JOB, A);
    await fetchRecordingResult(RECORDING, A);
    await fetchReviewItems(RECORDING, A);

    for (const url of urls()) {
      expect(url).not.toContain("family_mura_app");
      expect(url).toContain(`/v1/families/${A}/`);
    }
  });

  it("never derives speaker_person_id from the signed-in account", async () => {
    const spy = vi.fn(async () => jsonResponse({ recording_id: RECORDING, job_id: JOB }));
    vi.stubGlobal("fetch", spy);
    const signedInUserId = `user_${"d".repeat(32)}`;

    await submitRecording(
      {
        audio: new Blob(["x"]),
        filename: "memory.webm",
        speakerName: "Айсұлу",
        speakerPersonId: currentSpeakerPersonId(),
        audioLanguage: "auto",
        outputLanguage: "same_as_transcript",
      },
      A,
    );

    const form = (spy.mock.calls[0] as unknown as [string, RequestInit])[1].body as FormData;
    // An account is not an archive Person. Turning a login into a canonical
    // person id would fabricate an evidence-backed entity out of a session.
    expect(form.get("speaker_person_id")).toBeNull();
    expect(String(form.get("speaker_name"))).not.toContain(signedInUserId);
    expect(currentSpeakerPersonId()).toBeNull();
  });
});

describe("family-scoped cache keys", () => {
  it("keeps the same resource id distinct across families", () => {
    // An unscoped key is how family A's result gets rendered under family B.
    expect(familyScopedKey(A, "recording", RECORDING)).not.toBe(
      familyScopedKey(B, "recording", RECORDING),
    );
    expect(familyScopedKey(A, "recording", RECORDING)).toContain(A);
  });

  it("keeps different kinds distinct within one family", () => {
    expect(familyScopedKey(A, "recording", "x")).not.toBe(familyScopedKey(A, "review", "x"));
  });
});
