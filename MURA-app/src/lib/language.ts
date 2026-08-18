export type UiLanguage = "ru" | "kk";
export type AudioLanguage = "auto" | "ru" | "kk" | "mixed";
export type DetectedLanguage = "ru" | "kk" | "mixed" | "unknown";
export type OutputLanguage = "same_as_transcript" | "ru" | "kk";
export type EffectiveAudioLanguageMode = "multilingual_auto";

export interface LanguageContext {
  ui_language: UiLanguage;
  audio_language: AudioLanguage;
  detected_audio_language: DetectedLanguage;
  transcript_language: DetectedLanguage;
  output_language: OutputLanguage;
}

/** Language information owned by Core. UI language is deliberately absent. */
export interface CoreLanguageContext {
  audio_language: AudioLanguage;
  effective_audio_language_mode: EffectiveAudioLanguageMode;
  detected_audio_language: DetectedLanguage;
  transcript_language: DetectedLanguage;
  output_language: OutputLanguage;
  diagnostics?: string[];
}

export const DEFAULT_AUDIO_LANGUAGE: AudioLanguage = "auto";
export const DEFAULT_OUTPUT_LANGUAGE: OutputLanguage = "same_as_transcript";

export interface TranscriptLanguageDiagnostics {
  language: DetectedLanguage;
  confidence: number;
  token_count: number;
  russian_marker_count: number;
  kazakh_marker_count: number;
  kazakh_specific_token_count: number;
}

const KAZAKH_SPECIFIC_LETTERS = /[әғқңөұүһі]/u;
const TOKEN_PATTERN = /[а-яёәғқңөұүһі]+/giu;

const RUSSIAN_MARKERS = new Set([
  "я",
  "мы",
  "он",
  "она",
  "они",
  "это",
  "этот",
  "эта",
  "как",
  "когда",
  "был",
  "была",
  "были",
  "мой",
  "моя",
  "мою",
  "наш",
  "наша",
  "мне",
  "его",
  "её",
  "ее",
  "потом",
  "всегда",
  "помню",
  "после",
  "перед",
  "школе",
  "школа",
  "жил",
  "жила",
  "живёт",
  "живет",
  "вместе",
  "который",
  "которая",
]);

const KAZAKH_MARKERS = new Set([
  "мен",
  "біз",
  "ол",
  "бұл",
  "сол",
  "және",
  "бірақ",
  "қалай",
  "қашан",
  "еді",
  "болды",
  "болған",
  "менің",
  "біздің",
  "оның",
  "олардың",
  "анам",
  "әкем",
  "үй",
  "мектеп",
  "кейін",
  "бұрын",
  "жыл",
  "жылы",
  "бала",
  "балалар",
  "есімде",
  "туралы",
  "үйленді",
  "әйелі",
  "ұлы",
  "ұлым",
  "қызы",
  "қызым",
  "сәлем",
]);

/**
 * Conservative RU/KK transcript classification.
 *
 * Shared Cyrillic alone is not evidence of Russian. The detector only returns
 * a concrete language when lexical markers or Kazakh-specific letters provide
 * enough signal; otherwise it returns unknown.
 */
export function detectTranscriptLanguageDetailed(
  transcript: string,
): TranscriptLanguageDiagnostics {
  const tokens = transcript.toLocaleLowerCase().match(TOKEN_PATTERN) ?? [];
  const russianMarkerCount = tokens.filter((token) => RUSSIAN_MARKERS.has(token)).length;
  const kazakhMarkerCount = tokens.filter((token) => KAZAKH_MARKERS.has(token)).length;
  const kazakhSpecificTokenCount = tokens.filter((token) =>
    KAZAKH_SPECIFIC_LETTERS.test(token),
  ).length;

  const russianScore = russianMarkerCount * 2;
  const kazakhScore = kazakhMarkerCount * 2 + kazakhSpecificTokenCount * 2;
  const hasRussianSignal = russianMarkerCount >= 2;
  const hasKazakhSignal =
    kazakhMarkerCount >= 2 ||
    kazakhSpecificTokenCount >= 2 ||
    (kazakhMarkerCount >= 1 && kazakhSpecificTokenCount >= 1);

  let language: DetectedLanguage = "unknown";
  if (hasRussianSignal && hasKazakhSignal) language = "mixed";
  else if (hasKazakhSignal) language = "kk";
  else if (hasRussianSignal) language = "ru";

  const totalScore = russianScore + kazakhScore;
  const strongestScore = Math.max(russianScore, kazakhScore);
  const confidence =
    language === "unknown" || totalScore === 0
      ? 0
      : language === "mixed"
        ? Math.min(russianScore, kazakhScore) / Math.max(russianScore, kazakhScore)
        : strongestScore / totalScore;

  return {
    language,
    confidence: Number(confidence.toFixed(3)),
    token_count: tokens.length,
    russian_marker_count: russianMarkerCount,
    kazakh_marker_count: kazakhMarkerCount,
    kazakh_specific_token_count: kazakhSpecificTokenCount,
  };
}

export function detectTranscriptLanguage(transcript: string): DetectedLanguage {
  return detectTranscriptLanguageDetailed(transcript).language;
}

export function isUiLanguage(value: unknown): value is UiLanguage {
  return value === "ru" || value === "kk";
}

export function isAudioLanguage(value: unknown): value is AudioLanguage {
  return value === "auto" || value === "ru" || value === "kk" || value === "mixed";
}

export function isDetectedLanguage(value: unknown): value is DetectedLanguage {
  return value === "ru" || value === "kk" || value === "mixed" || value === "unknown";
}

export function isOutputLanguage(value: unknown): value is OutputLanguage {
  return value === "same_as_transcript" || value === "ru" || value === "kk";
}
