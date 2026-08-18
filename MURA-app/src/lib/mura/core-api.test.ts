import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CoreRequestError,
  fetchJob,
  readApiError,
  submitRecording,
} from "@/lib/mura/core-api";
import { currentSpeakerPersonId } from "@/lib/mura/scope";

/** An authorized family id, as it now arrives from the family session. */
const FAMILY = `family_${"a".repeat(32)}`;

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "x-request-id": "req_abc" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("canonical error envelope", () => {
  it("parses the canonical shape", () => {
    const parsed = readApiError({
      error: {
        code: "not_found",
        message: "The requested resource was not found.",
        retryable: false,
        request_id: "req_123",
      },
    });

    expect(parsed).toEqual({
      code: "not_found",
      message: "The requested resource was not found.",
      retryable: false,
      requestId: "req_123",
    });
  });

  it("rejects legacy and malformed shapes instead of trusting them", () => {
    // Core's old ad-hoc shape had a string `error`; it must not parse.
    expect(readApiError({ error: "deepseek_pipeline_failed", detail: "..." })).toBeNull();
    expect(readApiError({ detail: "Core service is not configured" })).toBeNull();
    expect(readApiError({ error: { code: 1, message: 2 } })).toBeNull();
    expect(readApiError(null)).toBeNull();
    expect(readApiError("boom")).toBeNull();
  });

  it("surfaces the canonical error and keeps request_id on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          {
            error: {
              code: "service_unavailable",
              message: "The service is not available.",
              retryable: true,
              request_id: "req_zzz",
            },
          },
          503,
        ),
      ),
    );

    await expect(fetchJob("job_" + "a".repeat(32), FAMILY)).rejects.toMatchObject({
      status: 503,
      api: { code: "service_unavailable", retryable: true, requestId: "req_zzz" },
    });
  });

  it("does not invent a canonical error from an unparsable body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("<html>gateway</html>", { status: 502 })),
    );

    const error = await fetchJob("job_" + "a".repeat(32), FAMILY).catch((value) => value);

    expect(error).toBeInstanceOf(CoreRequestError);
    expect(error.api.code).toBe("unexpected_response");
  });
});

describe("recording submission", () => {
  it("puts family_id in the route and never in the body", async () => {
    const spy = vi.fn(async () => jsonResponse({ recording_id: "rec_1", job_id: "job_1" }));
    vi.stubGlobal("fetch", spy);

    await submitRecording(
      {
        audio: new Blob(["x"]),
        filename: "memory.webm",
        speakerName: "Айсұлу",
        speakerPersonId: currentSpeakerPersonId(),
        audioLanguage: "kk",
        outputLanguage: "ru",
      },
      FAMILY,
    );

    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`/api/mura/v1/families/${FAMILY}/recordings`);
    const form = init.body as FormData;
    expect(form.get("family_id")).toBeNull();
    expect(form.get("speaker_id")).toBeNull();
    expect(form.get("ui_language")).toBeNull();
    expect(form.get("speaker_name")).toBe("Айсұлу");
    expect(form.get("audio_language")).toBe("kk");
    expect(form.get("output_language")).toBe("ru");
  });

  it("omits speaker_person_id entirely when no canonical person is known", async () => {
    const spy = vi.fn(async () => jsonResponse({ recording_id: "rec_1", job_id: "job_1" }));
    vi.stubGlobal("fetch", spy);

    await submitRecording(
      {
        audio: new Blob(["x"]),
        filename: "memory.webm",
        speakerName: "Айсұлу",
        speakerPersonId: null,
        audioLanguage: "auto",
        outputLanguage: "same_as_transcript",
      },
      FAMILY,
    );

    const form = (spy.mock.calls[0] as unknown as [string, RequestInit])[1].body as FormData;
    // A fabricated id such as "aisulu" must never be sent.
    expect(form.get("speaker_person_id")).toBeNull();
  });

  it("sends a canonical speaker_person_id when one genuinely exists", async () => {
    const spy = vi.fn(async () => jsonResponse({ recording_id: "rec_1", job_id: "job_1" }));
    vi.stubGlobal("fetch", spy);
    const canonical = `person_${"a".repeat(32)}`;

    await submitRecording(
      {
        audio: new Blob(["x"]),
        filename: "memory.webm",
        speakerName: "Айсұлу",
        speakerPersonId: canonical,
        audioLanguage: "auto",
        outputLanguage: "same_as_transcript",
      },
      FAMILY,
    );

    const form = (spy.mock.calls[0] as unknown as [string, RequestInit])[1].body as FormData;
    expect(form.get("speaker_person_id")).toBe(canonical);
  });

  it("never manufactures a canonical person id in the browser", () => {
    expect(currentSpeakerPersonId()).toBeNull();
  });
});

describe("job requests", () => {
  it("uses the family-scoped job path", async () => {
    const spy = vi.fn(async () => jsonResponse({ job_id: "job_1" }));
    vi.stubGlobal("fetch", spy);
    const jobId = `job_${"b".repeat(32)}`;

    await fetchJob(jobId, FAMILY);

    expect((spy.mock.calls[0] as unknown as [string])[0]).toBe(
      `/api/mura/v1/families/${FAMILY}/jobs/${jobId}`,
    );
  });
});
