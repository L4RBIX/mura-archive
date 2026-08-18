/**
 * The typed client for the family archive.
 *
 * One boundary, mirroring Core's read models. There is no second archive
 * client and no raw `fetch` in a screen: a competing projection is how two
 * parts of the product end up disagreeing about who someone is.
 *
 * Every type here is a DTO Core actually returns. Nothing is widened to `any`
 * and nothing is filled in on the client -- an optional field is optional
 * because the archive genuinely may not know, and the UI has to say so rather
 * than substitute something plausible.
 */

import { coreRequest } from "@/lib/mura/core-api";

/** A date with the precision the archive actually has. */
export interface ArchiveDate {
  value: string | null;
  /** `day` | `month` | `year` | `decade` | `unknown` — Core's vocabulary. */
  precision: string;
  original_expression: string | null;
  approximate: boolean;
}

export interface ArchiveSource {
  recording_id: string;
  speaker_name: string;
  recorded_at: string;
  claim_ids: string[];
}

export interface ArchivePerson {
  person_id: string;
  display_name: string;
  aliases: string[];
  category: string;
  relation_to_speaker: string | null;
  story_count: number;
  recording_count: number;
}

export interface ArchiveRelationship {
  edge_id: string;
  relationship_type: string;
  subject_person_id: string;
  subject_role: string;
  object_person_id: string;
  object_role: string;
  source_claim_ids: string[];
}

export interface ArchiveEvent {
  event_id: string;
  title: string;
  event_type: string;
  description: string | null;
  location: string | null;
  date: ArchiveDate | null;
  participant_person_ids: string[];
}

export interface ArchiveStorySummary {
  story_id: string;
  title: string | null;
  excerpt: string | null;
  recording_id: string;
  speaker_name: string;
  recorded_at: string;
  person_ids: string[];
}

export interface ArchiveStoryDetail {
  story_id: string;
  title: string | null;
  summary: string | null;
  recording_id: string;
  speaker_name: string;
  recorded_at: string;
  people: ArchivePerson[];
  events: ArchiveEvent[];
  source: ArchiveSource;
  /** Only true when Core can genuinely serve the recording. */
  audio_available: boolean;
}

export interface ArchiveReviewItem {
  review_id: string;
  /** `open_question` or `conflict:<type>`, decided by Core. */
  kind: string;
  question: string;
  detail: string | null;
  recording_id: string | null;
  person_ids: string[];
  created_at: string | null;
}

export interface ArchiveStoryPage {
  page: { total: number; limit: number; offset: number };
  items: ArchiveStorySummary[];
}

export interface ArchiveOverview {
  family_id: string;
  people_count: number;
  relationship_count: number;
  story_count: number;
  recording_count: number;
  review_count: number;
  open_conflict_count: number;
  recent_stories: ArchiveStorySummary[];
}

const scope = (familyId: string) => `/v1/families/${encodeURIComponent(familyId)}`;

export function fetchArchiveOverview(
  familyId: string,
  signal?: AbortSignal,
): Promise<ArchiveOverview> {
  return coreRequest<ArchiveOverview>(`${scope(familyId)}/archive`, { signal });
}

export function fetchArchivePeople(
  familyId: string,
  signal?: AbortSignal,
): Promise<ArchivePerson[]> {
  return coreRequest<ArchivePerson[]>(`${scope(familyId)}/people`, { signal });
}

export function fetchArchiveRelationships(
  familyId: string,
  signal?: AbortSignal,
): Promise<ArchiveRelationship[]> {
  return coreRequest<ArchiveRelationship[]>(`${scope(familyId)}/relationships`, { signal });
}

export function fetchArchiveStories(
  familyId: string,
  options: { limit?: number; offset?: number; signal?: AbortSignal } = {},
): Promise<ArchiveStoryPage> {
  const query = new URLSearchParams();
  if (options.limit !== undefined) query.set("limit", String(options.limit));
  if (options.offset) query.set("offset", String(options.offset));
  const suffix = query.toString() ? `?${query}` : "";
  return coreRequest<ArchiveStoryPage>(`${scope(familyId)}/stories${suffix}`, {
    signal: options.signal,
  });
}

export function fetchArchiveStory(
  familyId: string,
  storyId: string,
  signal?: AbortSignal,
): Promise<ArchiveStoryDetail> {
  return coreRequest<ArchiveStoryDetail>(
    `${scope(familyId)}/stories/${encodeURIComponent(storyId)}`,
    { signal },
  );
}

/** One materialized attribute, with the claims that produced it. */
export interface ArchiveAttribute {
  attribute_type: string;
  value: string;
  normalized_value: string;
  source_claim_ids: string[];
  metadata: Record<string, unknown>;
}

/**
 * The materialized profile for one canonical person.
 *
 * Every list is empty when the archive knows nothing of that kind. There is no
 * placeholder biography: a profile that always looks complete is a profile
 * that is partly invented.
 */
export interface ArchiveProfile {
  person_id: string;
  family_id: string;
  canonical_name: string;
  category: string;
  birth_date: ArchiveAttribute | null;
  death_date: ArchiveAttribute | null;
  aliases: ArchiveAttribute[];
  professions: ArchiveAttribute[];
  locations: ArchiveAttribute[];
  education: ArchiveAttribute[];
  descriptions: ArchiveAttribute[];
  events: ArchiveAttribute[];
  source_claim_ids: string[];
  updated_at: string;
}

export function fetchArchiveProfile(
  familyId: string,
  personId: string,
  signal?: AbortSignal,
): Promise<ArchiveProfile> {
  return coreRequest<ArchiveProfile>(
    `${scope(familyId)}/profiles/${encodeURIComponent(personId)}`,
    { signal },
  );
}

export function fetchArchiveReviewItems(
  familyId: string,
  signal?: AbortSignal,
): Promise<ArchiveReviewItem[]> {
  return coreRequest<ArchiveReviewItem[]>(`${scope(familyId)}/review-items`, { signal });
}

/**
 * Where the browser plays a recording from.
 *
 * A proxied URL, never a storage key or a path: the browser is handed a
 * resource it is authorised to read, and Core resolves where the bytes live.
 */
export function recordingAudioUrl(familyId: string, recordingId: string): string {
  return `/api/mura${scope(familyId)}/recordings/${encodeURIComponent(recordingId)}/audio`;
}
