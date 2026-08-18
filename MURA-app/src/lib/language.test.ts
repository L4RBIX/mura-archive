import { describe, expect, it } from "vitest";
import {
  detectTranscriptLanguage,
  detectTranscriptLanguageDetailed,
} from "@/lib/language";

describe("detectTranscriptLanguage", () => {
  it("detects Russian from lexical evidence", () => {
    expect(
      detectTranscriptLanguage("Я помню, как мне было шесть лет и мы жили вместе."),
    ).toBe("ru");
  });

  it("detects Kazakh from specific letters and lexical evidence", () => {
    expect(
      detectTranscriptLanguage("Мен мектепте оқыдым, кейін біздің үйге қайттым."),
    ).toBe("kk");
  });

  it("detects mixed Russian and Kazakh without using UI locale", () => {
    expect(
      detectTranscriptLanguage("Даниярдың әйелі Алина, и они потом жили вместе."),
    ).toBe("mixed");
  });

  it("does not assume shared Cyrillic is Russian", () => {
    expect(detectTranscriptLanguage("Ерлан Болат Алина")).toBe("unknown");
  });

  it("keeps confidence details internal and deterministic", () => {
    expect(
      detectTranscriptLanguageDetailed("Менің ұлым Ерлан. Я всегда им гордилась."),
    ).toEqual({
      language: "mixed",
      confidence: 0.5,
      token_count: 7,
      russian_marker_count: 2,
      kazakh_marker_count: 2,
      kazakh_specific_token_count: 2,
    });
  });
});
