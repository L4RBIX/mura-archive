/**
 * The family a recording workflow belongs to, fixed at submission.
 *
 * A recording takes a minute or two to process, and the user may switch family
 * while it does. If the processing screen read the *current* selection, that
 * switch would repoint an in-flight job at another archive: the poll would
 * 404, or worse, a recording id that happened to exist in both would surface
 * the wrong memory. So the family is captured once, when the upload starts, and
 * carried with the workflow instead of being re-derived.
 *
 * It travels in the URL rather than in React state because the processing screen
 * is a separate route that must survive a reload, and because a value in the URL
 * cannot be quietly mutated by a later global selection change.
 */

export interface RecordingWorkflow {
  jobId: string;
  recordingId: string;
  memoryId: string;
  /** Immutable for the life of this workflow. */
  familyId: string;
}

export function processingHref(workflow: RecordingWorkflow): string {
  const query = new URLSearchParams({
    job: workflow.jobId,
    recording: workflow.recordingId,
    memory: workflow.memoryId,
    family: workflow.familyId,
  });
  return `/processing?${query.toString()}`;
}

/**
 * Read the workflow back out of the URL.
 *
 * Returns null unless all four parts are present. A partial workflow must not
 * fall back to the current selection to fill the gap -- that is precisely the
 * substitution this module exists to prevent.
 */
export function readWorkflow(params: {
  get(key: string): string | null;
}): RecordingWorkflow | null {
  const jobId = params.get("job");
  const recordingId = params.get("recording");
  const memoryId = params.get("memory");
  const familyId = params.get("family");
  if (!jobId || !recordingId || !memoryId || !familyId) return null;
  return { jobId, recordingId, memoryId, familyId };
}

/**
 * Cache key for anything family-scoped.
 *
 * Family-scoped data is never keyed by resource id alone. Two families can hold
 * recordings, profiles and conflicts under ids the client has no reason to
 * assume are globally distinct, and an unscoped key is how family A's result
 * would be rendered under family B after a switch.
 */
export function familyScopedKey(familyId: string, kind: string, resourceId: string): string {
  return `${familyId}:${kind}:${resourceId}`;
}
