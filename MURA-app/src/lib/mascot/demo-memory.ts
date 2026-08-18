import type { TranslationKey } from "@/lib/i18n";

/**
 * The prepared demo memory behind /ask.
 *
 * Kept separate from the family graph on purpose: this is a scripted retrieval
 * for the demo, not a record the pipeline produced. When the real retrieval
 * lands, /ask swaps this resolver out and nothing else changes.
 */

export interface DemoMemoryPhoto {
  src: string;
  altKey: TranslationKey;
  width: number;
  height: number;
}

export interface DemoMemory {
  id: string;
  titleKey: TranslationKey;
  eraKey: TranslationKey;
  summaryKey: TranslationKey;
  photos: DemoMemoryPhoto[];
}

const MUSTAFA: DemoMemory = {
  id: "demo-mustafa",
  titleKey: "mustafaTitle",
  eraKey: "mustafaEra",
  summaryKey: "mustafaSummary",
  photos: [
    {
      src: "/memories/mustafa-stage.jpg",
      altKey: "mustafaPhotoTeam",
      width: 1280,
      height: 960,
    },
    {
      src: "/memories/mustafa-team-portrait.jpg",
      altKey: "mustafaPhotoPortrait",
      width: 1200,
      height: 1600,
    },
  ],
};

/** Russian, Kazakh and Latin spellings, stemmed so case endings still match. */
const MUSTAFA_PATTERN = /(мустаф|мұстаф|mustaf)/i;

export function findDemoMemory(transcript: string): DemoMemory | null {
  return MUSTAFA_PATTERN.test(transcript) ? MUSTAFA : null;
}

/** Scripted demo answer used when Copilot is configured to answer any prompt. */
export function mustafaDemoMemory(): DemoMemory {
  return MUSTAFA;
}
