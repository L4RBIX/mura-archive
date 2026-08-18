import { describe, expect, it } from "vitest";
import { migrateSavedMemory } from "@/lib/memory-store";

describe("SavedMemory language migration", () => {
  it("moves legacy locale without inferring transcript language", () => {
    const transcript = "Я помню этот день.";
    const migrated = migrateSavedMemory({
      id: "legacy-1",
      createdAt: "2026-07-20T10:00:00.000Z",
      locale: "kk",
      title: "Ескі естелік",
      summary: "",
      transcript,
      people: [],
      durationSec: 10,
      source: "audio_only",
    });

    expect(migrated).toMatchObject({
      ui_language_at_creation: "kk",
      audio_language: "auto",
      detected_audio_language: "unknown",
      transcript_language: "unknown",
      output_language: "same_as_transcript",
      transcript,
    });
    expect(migrated).not.toHaveProperty("locale");
  });

  it("preserves an existing decoupled language context", () => {
    const migrated = migrateSavedMemory({
      id: "current-1",
      createdAt: "2026-07-20T10:00:00.000Z",
      ui_language_at_creation: "ru",
      audio_language: "mixed",
      detected_audio_language: "unknown",
      transcript_language: "mixed",
      output_language: "same_as_transcript",
      title: "История",
      summary: "",
      transcript: "Мен помню этот күн.",
      people: [],
      durationSec: 10,
      source: "mura_core",
    });

    expect(migrated).toMatchObject({
      ui_language_at_creation: "ru",
      audio_language: "mixed",
      transcript_language: "mixed",
    });
  });
});
