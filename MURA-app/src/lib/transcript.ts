import type { Person } from "./types";

export interface TranscriptSegment {
  text: string;
  /** Set when this segment is a family member’s name. */
  personId?: string;
}

/**
 * Splits a paragraph into plain-text and person-name segments so the UI can
 * lay a highlighter mark over every family member the story mentions.
 */
export function parseMentions(
  text: string,
  people: Person[],
): TranscriptSegment[] {
  if (people.length === 0) return [{ text }];

  const byName = new Map(people.map((p) => [p.name, p.id]));
  const names = people
    .map((p) => p.name)
    .sort((a, b) => b.length - a.length)
    .join("|");
  const pattern = new RegExp(`\\b(${names})\\b`, "g");

  const segments: TranscriptSegment[] = [];
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor) {
      segments.push({ text: text.slice(cursor, match.index) });
    }
    segments.push({ text: match[0], personId: byName.get(match[0]) });
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) {
    segments.push({ text: text.slice(cursor) });
  }
  return segments;
}
