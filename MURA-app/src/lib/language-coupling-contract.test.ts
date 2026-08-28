import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  isAudioLanguage,
  isDetectedLanguage,
  isOutputLanguage,
  isUiLanguage,
} from "@/lib/language";

function source(relativePath: string) {
  return readFileSync(resolve(process.cwd(), relativePath), "utf8");
}

/** Source with comments removed, so prose explaining a rule cannot fail it. */
function code(relativePath: string) {
  return source(relativePath)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
}

/**
 * Four languages, four questions, and nothing joins them.
 *
 *   UiLanguage         which language the interface is written in
 *   AudioLanguage      what the recogniser should expect to hear
 *   TranscriptLanguage what was actually detected in the audio
 *   OutputLanguage     which language a summary is presented in
 *
 * The failure this guards against is the tempting one: someone reads the
 * interface locale and passes it to the recogniser, because in most products
 * those are the same value. Here they are not. A Russian interface recording a
 * Kazakh grandmother is the normal case, and coupling the two would restart
 * speech recognition in the wrong language every time somebody changed the
 * interface — silently, and only for the families least able to work around it.
 */

describe("the four language types stay distinct", () => {
  it("accepts different sets of values", () => {
    // If any two were the same type, one of these would pass in both.
    expect(isUiLanguage("en")).toBe(true);
    expect(isAudioLanguage("en")).toBe(false);

    expect(isAudioLanguage("auto")).toBe(true);
    expect(isUiLanguage("auto")).toBe(false);

    expect(isDetectedLanguage("unknown")).toBe(true);
    expect(isUiLanguage("unknown")).toBe(false);
    expect(isAudioLanguage("unknown")).toBe(false);

    expect(isOutputLanguage("same_as_transcript")).toBe(true);
    expect(isUiLanguage("same_as_transcript")).toBe(false);
    expect(isAudioLanguage("same_as_transcript")).toBe(false);
  });

  it("keeps English out of everything below the interface", () => {
    // MURA transcribes Russian and Kazakh. Adding an English *interface* must
    // not imply an English recogniser or an English summary.
    expect(isAudioLanguage("en")).toBe(false);
    expect(isDetectedLanguage("en")).toBe(false);
    expect(isOutputLanguage("en")).toBe(false);
  });
});

describe("UI language is statically forbidden from ASR contracts", () => {
  it("keeps locale out of Web Speech live transcription", () => {
    const liveHook = source("src/hooks/use-live-transcript.ts");
    const recordView = source("src/components/record/record-view.tsx");
    const askView = source("src/components/ask/ask-view.tsx");

    expect(liveHook).not.toMatch(/\bLocale\b|\blocale\b|uiLanguage|ui_language/);
    expect(recordView).not.toMatch(/useLiveTranscript\s*\(\s*(locale|uiLanguage)/);
    expect(askView).not.toMatch(/useLiveTranscript\s*\(\s*(locale|uiLanguage)/);
  });

  it("keeps UI locale out of the Core upload", () => {
    const recordView = source("src/components/record/record-view.tsx");

    expect(recordView).not.toMatch(/form\.append\(["']ui_language["']/);
    expect(recordView).not.toMatch(/JSON\.stringify\(\{[\s\S]*?\blocale\b/);
  });

  it("never derives the audio language from the interface language", () => {
    const recordView = code("src/components/record/record-view.tsx");

    // The exact shapes this would take if someone "simplified" the two into one.
    expect(recordView).not.toMatch(/audioLanguage\s*=\s*(locale|uiLanguage)/);
    expect(recordView).not.toMatch(/setAudioLanguage\s*\(\s*(locale|uiLanguage)\s*\)/);
  });
});

describe("the two preferences are stored apart", () => {
  const audio = source("src/lib/mura/audio-language.ts");
  const i18n = source("src/lib/i18n.tsx");

  it("uses a different storage key for each", () => {
    // One key would make the last writer win, and changing the interface would
    // silently rewrite what the recogniser expects to hear.
    expect(audio).toMatch(/"mura-audio-language"/);
    expect(i18n).toMatch(/"mura-locale"/);
    expect(audio).not.toMatch(/"mura-locale"/);
    expect(i18n).not.toMatch(/"mura-audio-language"/);
  });

  it("keeps the audio preference free of any interface-language import", () => {
    expect(code("src/lib/mura/audio-language.ts")).not.toMatch(/from "@\/lib\/i18n"/);
  });

  it("keeps the interface provider free of any audio-language import", () => {
    expect(code("src/lib/i18n.tsx")).not.toMatch(/audio-language/);
  });
});

describe("settings states the separation to the user", () => {
  const settings = source("src/components/settings/settings-view.tsx");

  it("offers the audio language as its own group, not inside the interface one", () => {
    expect(settings).toMatch(/settings-audio-language/);
    expect(settings).toMatch(/AudioLanguageSection/);
  });

  it("shows a hint under each that names the other", () => {
    // Both hints exist so neither control can be read as governing the other.
    expect(settings).toMatch(/settingsLanguageHint/);
    expect(settings).toMatch(/settingsAudioLanguageHint/);
  });
});
