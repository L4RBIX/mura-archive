export type AccentTone = "clay" | "periwinkle" | "sand";

export interface Person {
  id: string;
  name: string;
  nativeName: string;
  /** Relationship as the narrator says it: “My father”, “My daughter”. */
  relation: string;
  gender: "f" | "m";
  born: number;
  died?: number;
  tone: AccentTone;
  /** AI-written portrait distilled from the narrator’s recordings. */
  summary: string;
  /** Phrase inside `summary` that gets the highlighter mark. */
  summaryHighlight?: string;
  isNarrator?: boolean;
  /** Biological parents, by id. 0–2 entries — drives the whole family graph. */
  parentIds: string[];
  /** Spouse, by id, if any. */
  spouseId?: string;
}

export interface Story {
  id: string;
  title: string;
  /** Era the AI estimated from context: “Winter 1954 · estimated”. */
  era: string;
  /** When the narrator recorded it: “Today”, “Yesterday”, “12 March”. */
  recordedLabel: string;
  durationSec: number;
  excerpt: string;
  paragraphs: string[];
  /** People this story mentions, by id, most central first. */
  mentions: string[];
  isNew?: boolean;
}
