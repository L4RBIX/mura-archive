import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

function source(relativePath: string) {
  return readFileSync(resolve(process.cwd(), relativePath), "utf8");
}

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
});
