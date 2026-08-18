/**
 * The single typed client for Mura Core.
 *
 * Types mirror the canonical Core DTOs at production/core-v1 (fca7c9f). The
 * full recording result is kept intact as `CoreRecordingResult` so provenance
 * survives the boundary; UI projection happens separately in pipeline-result.
 *
 * Every family-scoped call takes `familyId` explicitly and has no default. That
 * is deliberate: a default is how a hardcoded family survives a migration, and
 * an omitted argument would then read another family's memories rather than
 * failing to compile.
 */

// ------------------------------------------------------------------- errors

export interface CoreApiError {
  code: string;
  message: string;
  retryable: boolean;
  requestId: string;
}

export class CoreRequestError extends Error {
  readonly status: number;
  readonly api: CoreApiError;

  constructor(status: number, api: CoreApiError) {
    super(api.message);
    this.name = "CoreRequestError";
    this.status = status;
    this.api = api;
  }
}

/**
 * Parse the canonical envelope and nothing else.
 *
 * Core emits exactly one error shape since API-CONTRACT-01A-i, and the proxy
 * synthesises the same one, so a body that does not match is not silently
 * upgraded into a trusted error.
 */
export function readApiError(payload: unknown): CoreApiError | null {
  if (typeof payload !== "object" || payload === null) return null;
  const wrapper = (payload as { error?: unknown }).error;
  if (typeof wrapper !== "object" || wrapper === null) return null;
  const error = wrapper as Record<string, unknown>;
  if (typeof error.code !== "string" || typeof error.message !== "string") return null;
  return {
    code: error.code,
    message: error.message,
    retryable: error.retryable === true,
    requestId: typeof error.request_id === "string" ? error.request_id : "",
  };
}

// ------------------------------------------------------ identity & families

/**
 * The signed-in account, as Core describes it.
 *
 * Mirrors `UserView`: an internal `user_id` plus safe profile metadata. The
 * provider subject and issuer are not in this DTO on purpose, so the frontend
 * cannot come to depend on them and cannot leak them into the UI.
 */
export interface MeView {
  user_id: string;
  email: string | null;
  display_name: string | null;
}

export type FamilyRole = "owner" | "editor" | "viewer";

/**
 * A family the signed-in user is authorized for.
 *
 * `role` and `capabilities` are the caller's own, which is what lets the UI hide
 * actions it may not perform. That is convenience only -- Core re-checks every
 * request, so a forged click is still refused.
 */
export interface FamilyView {
  family_id: string;
  name: string;
  role: FamilyRole;
  capabilities: string[];
}

export interface MemberView {
  user_id: string;
  display_name: string | null;
  role: FamilyRole;
}

// ------------------------------------------------------------- capabilities

export type CapabilityStatus = "ready" | "degraded" | "unavailable";
export type AsrRegistration = "registered" | "unavailable" | "unknown";
export type ProviderConfiguration = "configured" | "not_configured";
export type RecordingMode = "audio" | "transcript_only" | "unavailable";

export interface Capabilities {
  schema_version: string;
  status: CapabilityStatus;
  recording: { enabled: boolean; mode: RecordingMode };
  asr: {
    registration: AsrRegistration;
    registered_at: string | null;
    /** Diagnostic Kaggle-era metadata. Product behaviour must not depend on it. */
    registration_age_seconds: number | null;
    live_health_verified: boolean;
  };
  analysis: { configuration: ProviderConfiguration; live_health_verified: boolean };
  validation: { release_version: string };
}

// --------------------------------------------------------------------- jobs

export type JobStatus =
  | "queued"
  | "transcribing"
  | "cleaning"
  | "extracting"
  | "resolving"
  | "completed"
  | "failed";

/** Core's stage while it is waiting to retry an unreachable recogniser. */
export const WAITING_FOR_ASR_STAGE = "waiting_for_asr";

export interface JobView {
  job_id: string;
  recording_id: string;
  status: JobStatus;
  stage: string;
  attempts: number;
  retryable: boolean;
  retry_after_seconds: number | null;
  next_retry_at: string | null;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
}

// ----------------------------------------------------------------- language

export type AudioLanguage = "auto" | "ru" | "kk" | "mixed";
export type OutputLanguage = "same_as_transcript" | "ru" | "kk";
export type DetectedAudioLanguage = "ru" | "kk" | "mixed" | "unknown";

/**
 * Canonical language state from Core. `*_applied` is false today because no
 * provider consumes the request; the UI must not claim otherwise.
 */
export interface LanguageContext {
  schema_version: string;
  requested_audio_language: AudioLanguage;
  effective_audio_language: AudioLanguage;
  audio_language_applied: boolean;
  detected_audio_language: DetectedAudioLanguage;
  transcript_language: DetectedAudioLanguage;
  requested_output_language: OutputLanguage;
  effective_output_language: OutputLanguage | null;
  output_language_applied: boolean;
}

// ------------------------------------------------------------------ speaker

export type SpeakerResolution = "resolved" | "pending";

export interface SpeakerView {
  /** Canonical archive person, or null while the narrator is not canonical. */
  person_id: string | null;
  name: string;
  resolution_status: SpeakerResolution;
}

// ------------------------------------------------------------------ results

export interface RecordingAccepted {
  recording_id: string;
  job_id: string;
  status?: JobStatus;
}

/**
 * The complete Core result. Deliberately typed loosely below the top level:
 * the frontend does not consume every Pydantic model, but nothing is dropped,
 * so evidence spans, provenance activities, conflict sets, assertion modes and
 * resolution status remain reachable for Review, Ask MURA and Book later.
 */
export interface CorePipelineResult {
  transcript: Record<string, unknown>;
  cleaned_transcript: Record<string, unknown>;
  extraction: Record<string, unknown>;
  resolutions: Array<Record<string, unknown>>;
  processing: Record<string, unknown>;
}

export interface CoreRecordingResult {
  recording_id: string;
  family_id: string;
  speaker: SpeakerView;
  job: JobView;
  language_context: LanguageContext;
  result: CorePipelineResult;
}

export interface ReviewItems {
  recording_id: string;
  uncertain_fragments: Array<Record<string, unknown>>;
  detected_corrections: Array<Record<string, unknown>>;
  unresolved_questions: Array<Record<string, unknown>>;
  extraction_issues: Array<Record<string, unknown>>;
  ambiguous_resolutions: Array<Record<string, unknown>>;
  conflict_sets: Array<Record<string, unknown>>;
}

// ------------------------------------------------------------------- client

const BASE = "/api/mura";

/**
 * The single request path to Core.
 *
 * Exported so the archive client can reuse the error envelope, the no-store
 * policy and the `CoreRequestError` contract rather than growing a second,
 * subtly different one.
 */
export async function coreRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    let parsed: CoreApiError | null = null;
    try {
      parsed = readApiError(await response.json());
    } catch {
      parsed = null;
    }
    throw new CoreRequestError(
      response.status,
      parsed ?? {
        code: "unexpected_response",
        message: "Сервис вернул неожиданный ответ.",
        retryable: response.status >= 500,
        requestId: response.headers.get("x-request-id") ?? "",
      },
    );
  }
  // Removing a member answers 204 with no body; parsing it would throw.
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * Product capabilities.
 *
 * Authenticated since PR-03B-SWITCH, so this must run *after* the session
 * resolves. Calling it while signed out returns 401, and treating that 401 as a
 * service outage would tell the user the pipeline is broken when the only thing
 * missing is a login.
 */
export function fetchCapabilities(signal?: AbortSignal): Promise<Capabilities> {
  return coreRequest<Capabilities>("/v1/capabilities", { signal });
}

export function fetchMe(signal?: AbortSignal): Promise<MeView> {
  return coreRequest<MeView>("/v1/me", { signal });
}

export function fetchFamilies(signal?: AbortSignal): Promise<FamilyView[]> {
  return coreRequest<FamilyView[]>("/v1/families", { signal });
}

export function createFamily(name: string): Promise<FamilyView> {
  return coreRequest<FamilyView>("/v1/families", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export function fetchFamily(familyId: string, signal?: AbortSignal): Promise<FamilyView> {
  return coreRequest<FamilyView>(`/v1/families/${encodeURIComponent(familyId)}`, { signal });
}

export function fetchFamilyMembers(
  familyId: string,
  signal?: AbortSignal,
): Promise<MemberView[]> {
  return coreRequest<MemberView[]>(`/v1/families/${encodeURIComponent(familyId)}/members`, {
    signal,
  });
}

export function updateMemberRole(
  familyId: string,
  userId: string,
  role: FamilyRole,
): Promise<MemberView> {
  return coreRequest<MemberView>(
    `/v1/families/${encodeURIComponent(familyId)}/members/${encodeURIComponent(userId)}`,
    {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ role }),
    },
  );
}

export async function removeMember(familyId: string, userId: string): Promise<void> {
  await coreRequest<unknown>(
    `/v1/families/${encodeURIComponent(familyId)}/members/${encodeURIComponent(userId)}`,
    { method: "DELETE" },
  );
}

export interface RecordingSubmission {
  audio: Blob;
  filename: string;
  speakerName: string;
  /** Only ever a canonical Core person id. Never fabricated in the browser. */
  speakerPersonId?: string | null;
  audioLanguage: AudioLanguage;
  outputLanguage: OutputLanguage;
}

export function submitRecording(
  submission: RecordingSubmission,
  familyId: string,
): Promise<RecordingAccepted> {
  const form = new FormData();
  form.append("file", submission.audio, submission.filename);
  form.append("speaker_name", submission.speakerName);
  // family_id is the route scope and must not be duplicated in the body.
  if (submission.speakerPersonId) {
    form.append("speaker_person_id", submission.speakerPersonId);
  }
  form.append("audio_language", submission.audioLanguage);
  form.append("output_language", submission.outputLanguage);
  return coreRequest<RecordingAccepted>(
    `/v1/families/${encodeURIComponent(familyId)}/recordings`,
    { method: "POST", body: form },
  );
}

export function fetchJob(jobId: string, familyId: string): Promise<JobView> {
  return coreRequest<JobView>(
    `/v1/families/${encodeURIComponent(familyId)}/jobs/${encodeURIComponent(jobId)}`,
  );
}

export function fetchRecordingResult(
  recordingId: string,
  familyId: string,
): Promise<CoreRecordingResult> {
  return coreRequest<CoreRecordingResult>(
    `/v1/families/${encodeURIComponent(familyId)}/recordings/${encodeURIComponent(recordingId)}`,
  );
}

export function fetchReviewItems(
  recordingId: string,
  familyId: string,
): Promise<ReviewItems> {
  return coreRequest<ReviewItems>(
    `/v1/families/${encodeURIComponent(familyId)}/recordings/${encodeURIComponent(
      recordingId,
    )}/review-items`,
  );
}
