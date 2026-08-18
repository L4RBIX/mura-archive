/**
 * Reads what the core pipeline actually returns and reduces it to what the
 * memory screen needs.
 *
 * The backend contract is deliberately richer than the UI — evidence spans,
 * coreference links, conflict sets, provenance, temporal precision. None of
 * that belongs on screen, but none of it should be thrown away either, so this
 * is a projection, not a replacement: the stored analysis keeps its shape and
 * this module only decides what a reader sees.
 *
 * Everything here is defensive. A field that is missing, null, or the wrong
 * type yields a safe default rather than throwing — a memory must still open
 * even when an analysis is partial or from an older schema version.
 */

import type { LanguageContext, SpeakerView } from "@/lib/mura/core-api";

/** Core's own default context, used when a payload predates language_context. */
const FALLBACK_LANGUAGE_CONTEXT: LanguageContext = {
  schema_version: "language-context-v1",
  requested_audio_language: "auto",
  effective_audio_language: "auto",
  audio_language_applied: false,
  detected_audio_language: "unknown",
  transcript_language: "unknown",
  requested_output_language: "same_as_transcript",
  effective_output_language: null,
  output_language_applied: false,
};

export type MuraJobStatus =
  | "queued"
  | "transcribing"
  | "cleaning"
  | "extracting"
  | "resolving"
  | "completed"
  | "failed"
  | "deferred";

/** Kinship as the backend states it, before it is phrased for a reader. */
export type MuraRelation =
  | "parent"
  | "child"
  | "sibling"
  | "spouse"
  | "grandparent"
  | "grandchild"
  | "relative"
  | "unknown";

export interface MemoryPerson {
  /** Mention id from the extraction; stable within one recording. */
  mentionId: string;
  name: string;
  aliases: string[];
  /** Raw relation phrase from the model, kept for display fallback. */
  relationToSpeaker: string | null;
  relation: MuraRelation;
  /** Resolved to an existing graph person, when resolution succeeded. */
  personId: string | null;
  /** True when this recording is what introduced them. */
  isNew: boolean;
  /** Resolution was ambiguous — needs a human, must not become a graph node. */
  needsReview: boolean;
}

export interface MemoryEvent {
  eventId: string;
  type: string;
  title: string;
  description: string;
  /** Original spoken expression, never a normalised date we invented. */
  dateText: string | null;
  location: string | null;
  participantMentionIds: string[];
}

export interface MemoryPlace {
  name: string;
}

export interface MemoryAnalysis {
  title: string | null;
  summary: string | null;
  /** Punctuation-repaired transcript from the cleaner stage. */
  cleanTranscript: string | null;
  /** Verbatim ASR output. Never overwritten. */
  rawTranscript: string | null;
  languages: string[];
  people: MemoryPerson[];
  events: MemoryEvent[];
  places: MemoryPlace[];
  /** Open questions the pipeline could not settle on its own. */
  reviewQuestions: string[];
  needsReview: boolean;
  durationSec: number | null;
  /** Canonical Core language state. Never overwritten by a client heuristic. */
  languageContext: LanguageContext;
  /** Canonical narrator identity, or null while Core has not resolved one. */
  speaker: SpeakerView | null;
}

// --------------------------------------------------------------- primitives

function str(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function arr(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function obj(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function strList(value: unknown): string[] {
  return arr(value)
    .map(str)
    .filter((item): item is string => item !== null);
}

// ------------------------------------------------------------- relationships

/**
 * The backend records a relationship as a typed edge plus the role each side
 * plays. `sibling` is symmetric; the others read differently depending on
 * which end the speaker is on, so the role decides the direction.
 */
const ROLE_TO_RELATION: Record<string, MuraRelation> = {
  parent: "parent",
  child: "child",
  spouse: "spouse",
  sibling: "sibling",
  older_sibling: "sibling",
  younger_sibling: "sibling",
  grandparent: "grandparent",
  grandchild: "grandchild",
};

/** Free-text relation phrases the extractor may emit, in RU / KK / EN. */
const PHRASE_TO_RELATION: Array<[RegExp, MuraRelation]> = [
  [/(брат|сестра|сестр|аға|апа|іні|қарындас|sibling|brother|sister)/i, "sibling"],
  [/(мама|мать|отец|папа|әке|ана|mother|father|parent)/i, "parent"],
  [/(сын|дочь|ұл|қыз|son|daughter|child)/i, "child"],
  [/(бабушка|дедушка|ата|әже|grandmother|grandfather|grandparent)/i, "grandparent"],
  [/(внук|внучка|немере|grandson|granddaughter|grandchild)/i, "grandchild"],
  [/(муж|жена|жұбай|күйеу|spouse|husband|wife)/i, "spouse"],
];

function relationFromPhrase(phrase: string | null): MuraRelation {
  if (!phrase) return "unknown";
  for (const [pattern, relation] of PHRASE_TO_RELATION) {
    if (pattern.test(phrase)) return relation;
  }
  return "unknown";
}

/**
 * Relation of each mention to the speaker, from the relationship claims.
 * Only claims that actually touch the speaker count, and only ones the
 * backend still considers current — a former or figurative tie ("как брат")
 * is history, not a live family edge.
 */
function relationsToSpeaker(
  claims: unknown[],
  speakerMentionIds: Set<string>,
): Map<string, MuraRelation> {
  const relations = new Map<string, MuraRelation>();
  for (const raw of claims) {
    const claim = obj(raw);
    if (str(claim.relationship_state) !== "current") continue;
    const subject = str(claim.subject_mention_id);
    const object = str(claim.object_mention_id);
    if (!subject || !object) continue;

    // Take the role of whichever end is *not* the speaker.
    if (speakerMentionIds.has(subject) && !speakerMentionIds.has(object)) {
      const relation = ROLE_TO_RELATION[str(claim.object_role) ?? ""];
      if (relation) relations.set(object, relation);
    } else if (speakerMentionIds.has(object) && !speakerMentionIds.has(subject)) {
      const relation = ROLE_TO_RELATION[str(claim.subject_role) ?? ""];
      if (relation) relations.set(subject, relation);
    }
  }
  return relations;
}

// ------------------------------------------------------------------ mapping

/**
 * `result` is the `PipelineResult` body of a `RecordingResultView`.
 * Pass the whole view or just the result — both are accepted.
 */
export function readAnalysis(payload: unknown): MemoryAnalysis {
  const root = obj(payload);
  const result = obj(root.result ?? root);
  const extraction = obj(result.extraction);
  const transcript = obj(result.transcript);
  const cleaned = obj(result.cleaned_transcript);
  const rawTranscript = str(transcript.full_text);
  // Core owns language truth. When it says unknown, it stays unknown: a client
  // heuristic must never be promoted into the canonical context.
  const languageContext: LanguageContext =
    typeof root.language_context === "object" && root.language_context !== null
      ? (root.language_context as LanguageContext)
      : FALLBACK_LANGUAGE_CONTEXT;

  const speakerObject = obj(root.speaker);
  const speaker: SpeakerView | null = str(speakerObject.name)
    ? {
        person_id: str(speakerObject.person_id),
        name: str(speakerObject.name) ?? "",
        resolution_status:
          str(speakerObject.resolution_status) === "resolved" ? "resolved" : "pending",
      }
    : null;

  // Only a canonical Core person id may identify the speaker's own mentions.
  const speakerId = speaker?.person_id ?? null;
  const mentions = arr(extraction.people_mentions).map(obj);

  // The speaker appears as a mention too; they are not "a person in this
  // memory" and must never be offered as a new relative.
  const speakerMentionIds = new Set<string>();
  const resolutions = new Map<string, Record<string, unknown>>();
  for (const raw of arr(result.resolutions)) {
    const resolution = obj(raw);
    const mentionId = str(resolution.mention_id);
    if (!mentionId) continue;
    resolutions.set(mentionId, resolution);
    if (speakerId && str(resolution.person_id) === speakerId) {
      speakerMentionIds.add(mentionId);
    }
  }

  const relations = relationsToSpeaker(
    arr(extraction.relationship_claims),
    speakerMentionIds,
  );

  const people: MemoryPerson[] = mentions
    .filter((mention) => {
      const mentionId = str(mention.mention_id);
      return mentionId !== null && !speakerMentionIds.has(mentionId);
    })
    .map((mention) => {
      const mentionId = str(mention.mention_id)!;
      const resolution = obj(resolutions.get(mentionId));
      const status = str(resolution.status);
      const personId = str(resolution.person_id);
      const relationPhrase = str(mention.relation_to_speaker);
      return {
        mentionId,
        name: str(mention.name) ?? "",
        aliases: strList(mention.aliases),
        relationToSpeaker: relationPhrase,
        relation: relations.get(mentionId) ?? relationFromPhrase(relationPhrase),
        personId,
        isNew: status === "created" || (status === "resolved" && !personId),
        needsReview: status === "ambiguous" || status === "unresolved",
      };
    })
    .filter((person) => person.name.length > 0);

  const events: MemoryEvent[] = arr(extraction.events).map((raw) => {
    const event = obj(raw);
    const date = obj(event.date);
    return {
      eventId: str(event.event_id) ?? "",
      type: str(event.event_type) ?? "other",
      title: str(event.title) ?? "",
      description: str(event.description) ?? "",
      // Prefer what was actually said over anything normalised.
      dateText: str(date.original_expression) ?? str(date.value),
      location: str(event.location),
      participantMentionIds: strList(event.participant_mention_ids),
    };
  });

  const places: MemoryPlace[] = [
    ...new Set(
      events
        .map((event) => event.location)
        .filter((name): name is string => name !== null),
    ),
  ].map((name) => ({ name }));

  // The pipeline may produce several stories for one recording; the first is
  // the memory as a whole.
  const story = obj(arr(extraction.stories)[0]);
  const questions = arr(extraction.unresolved_questions)
    .map((raw) => str(obj(raw).question))
    .filter((question): question is string => question !== null);

  const duration = result.transcript ? Number(transcript.duration_seconds) : NaN;

  return {
    title: str(story.title),
    summary: str(story.summary),
    cleanTranscript: str(cleaned.full_readable_text),
    rawTranscript,
    languages: strList(extraction.languages),
    people,
    events,
    places,
    reviewQuestions: questions,
    needsReview:
      questions.length > 0 ||
      people.some((person) => person.needsReview) ||
      arr(extraction.conflict_sets).length > 0,
    durationSec: Number.isFinite(duration) && duration > 0 ? duration : null,
    languageContext,
    speaker,
  };
}

/** True when the analysis carries enough to replace the placeholder memory. */
export function isPresentable(analysis: MemoryAnalysis): boolean {
  return Boolean(analysis.summary || analysis.title);
}
