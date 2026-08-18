import { describe, expect, it } from "vitest";
import { liveRecognitionLanguageOptions } from "@/hooks/use-live-transcript";

describe("liveRecognitionLanguageOptions", () => {
  it("does not pretend Web Speech supports multilingual auto", () => {
    expect(liveRecognitionLanguageOptions("auto")).toEqual([]);
    expect(liveRecognitionLanguageOptions("mixed")).toEqual([]);
  });

  it("uses explicit language only when the audio setting requests it", () => {
    expect(liveRecognitionLanguageOptions("ru")).toEqual(["ru-RU", "ru"]);
    expect(liveRecognitionLanguageOptions("kk")).toEqual(["kk-KZ", "kk"]);
  });
});
