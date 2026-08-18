import { describe, expect, it } from "vitest";
import { isPresentable, readAnalysis } from "@/lib/mura/pipeline-result";

/**
 * Fixtures mirror the shape `GET /v1/recordings/{id}` actually returns:
 * a RecordingResultView wrapping PipelineResult{transcript, cleaned_transcript,
 * extraction, resolutions}.
 */

const RAW_RU =
  "моя старшая сестра лия всегда любила читать книги мы называли её аля " +
  "после окончания школы она уехала учиться в алматы каникулы обязательно " +
  "возвращалась домой";

const SUMMARY_RU =
  "Старшая сестра рассказчика Лия, которую в семье называли Алей, с детства " +
  "любила читать. После школы она уехала учиться в Алматы, но на каникулах " +
  "всегда возвращалась домой.";

function view(overrides: Record<string, unknown> = {}) {
  return {
    recording_id: "rec_a1",
    speaker: {
      person_id: "person_speaker",
      name: "\u0410\u0439\u0441\u04b1\u043b\u0443",
      resolution_status: "resolved",
    },
    speaker_name: "Айсұлу",
    job_id: "job_a1",
    status: "completed",
    result: {
      transcript: { full_text: RAW_RU, duration_seconds: 42.5 },
      cleaned_transcript: {
        full_readable_text:
          "Моя старшая сестра Лия всегда любила читать книги. Мы называли её Аля.",
      },
      extraction: {
        languages: ["ru"],
        stories: [{ story_id: "story_1", title: "Лия и её годы учёбы в Алматы", summary: SUMMARY_RU }],
        people_mentions: [
          { mention_id: "m_speaker", name: "Айсұлу", aliases: [], confidence: 0.9 },
          {
            mention_id: "m_liya",
            name: "Лия",
            aliases: ["Аля"],
            relation_to_speaker: "старшая сестра",
            confidence: 0.9,
          },
        ],
        relationship_claims: [
          {
            relationship_id: "r1",
            relationship_state: "current",
            subject_mention_id: "m_speaker",
            subject_role: "sibling",
            object_mention_id: "m_liya",
            object_role: "sibling",
          },
        ],
        events: [
          {
            event_id: "e1",
            event_type: "education",
            title: "Учёба в Алматы",
            description: "Лия уехала учиться в Алматы после школы",
            date: { original_expression: "после окончания школы", value: null },
            location: "Алматы",
            participant_mention_ids: ["m_liya"],
          },
        ],
        unresolved_questions: [],
        conflict_sets: [],
        ...(overrides.extraction as object),
      },
      resolutions: [
        { mention_id: "m_speaker", status: "resolved", person_id: "person_speaker", reason: "speaker" },
        { mention_id: "m_liya", status: "created", person_id: "person_liya", reason: "new" },
      ],
      ...(overrides.result as object),
    },
  };
}

describe("readAnalysis", () => {
  // §13.1 — «Кратко» must not be the transcript.
  it("returns a summary that is not the transcript verbatim", () => {
    const analysis = readAnalysis(view());
    expect(analysis.summary).toBeTruthy();
    expect(analysis.summary).not.toBe(analysis.rawTranscript);
    expect(analysis.summary).not.toBe(analysis.cleanTranscript);
    expect(analysis.rawTranscript?.startsWith(analysis.summary!)).toBe(false);
  });

  // §13.2 — never cut mid-sentence.
  it("keeps the summary ending on sentence punctuation", () => {
    const analysis = readAnalysis(view());
    expect(analysis.summary!.trimEnd()).toMatch(/[.!?…]$/);
  });

  it("keeps the raw transcript intact and separate from the cleaned one", () => {
    const analysis = readAnalysis(view());
    expect(analysis.rawTranscript).toBe(RAW_RU);
    expect(analysis.cleanTranscript).not.toBe(RAW_RU);
  });

  // §8 — a real title, never the placeholder.
  it("produces a content-bearing title without a trailing period", () => {
    const analysis = readAnalysis(view());
    expect(analysis.title).toBe("Лия и её годы учёбы в Алматы");
    expect(analysis.title).not.toMatch(/\.$/);
    expect(analysis.title).not.toMatch(/Жаңа аудиожазба|Новая аудиозапись/);
  });

  it("excludes the speaker from the people in the memory", () => {
    const analysis = readAnalysis(view());
    expect(analysis.people.map((person) => person.name)).toEqual(["Лия"]);
  });

  it("derives kinship from the relationship claim, not just the phrase", () => {
    const [liya] = readAnalysis(view()).people;
    expect(liya.relation).toBe("sibling");
    expect(liya.aliases).toContain("Аля");
    expect(liya.isNew).toBe(true);
    expect(liya.personId).toBe("person_liya");
  });

  it("ignores relationships that are no longer current", () => {
    const payload = view();
    payload.result.extraction.relationship_claims[0].relationship_state = "former";
    const [liya] = readAnalysis(payload).people;
    // Falls back to the spoken phrase rather than asserting a live edge.
    expect(liya.relation).toBe("sibling");
    expect(
      readAnalysis({
        ...payload,
        result: {
          ...payload.result,
          extraction: {
            ...payload.result.extraction,
            people_mentions: [
              { mention_id: "m_speaker", name: "Айсұлу", confidence: 0.9 },
              { mention_id: "m_x", name: "Серик", confidence: 0.5 },
            ],
          },
        },
      }).people[0].relation,
    ).toBe("unknown");
  });

  it("maps events and derives places from their locations", () => {
    const analysis = readAnalysis(view());
    expect(analysis.events).toHaveLength(1);
    expect(analysis.events[0].dateText).toBe("после окончания школы");
    expect(analysis.places.map((place) => place.name)).toEqual(["Алматы"]);
  });

  it("flags ambiguous mentions for review instead of asserting them", () => {
    const payload = view();
    payload.result.resolutions[1] = {
      mention_id: "m_liya",
      status: "ambiguous",
      person_id: null,
      reason: "multiple candidates",
    } as never;
    const [liya] = readAnalysis(payload).people;
    expect(liya.needsReview).toBe(true);
    expect(liya.isNew).toBe(false);
    expect(liya.personId).toBeNull();
    expect(readAnalysis(payload).needsReview).toBe(true);
  });

  it("treats open questions as needing review", () => {
    const payload = view();
    payload.result.extraction.unresolved_questions = [
      { question_id: "q1", question: "Как зовут вашего брата?", reason: "no name" },
    ] as never;
    expect(readAnalysis(payload).needsReview).toBe(true);
  });

  // §10 — the pipeline's language is passed through untouched.
  it("keeps a Russian summary in Russian", () => {
    const analysis = readAnalysis(view());
    expect(analysis.languages).toContain("ru");
    expect(analysis.summary).toMatch(/[а-яё]/i);
  });

  it("treats Core language_context as authoritative, not a client heuristic", () => {
    const payload = view();
    Object.assign(payload.result.transcript, { language_hints: ["kk", "ru"] });
    const analysis = readAnalysis(payload);

    // Core owns detection. Russian-looking text must not be promoted into the
    // canonical context while Core truthfully reports unknown.
    expect(analysis.languageContext.detected_audio_language).toBe("unknown");
    expect(analysis.languageContext.transcript_language).toBe("unknown");
    expect(analysis.languageContext.audio_language_applied).toBe(false);
    expect(analysis.languageContext.output_language_applied).toBe(false);
  });

  it("keeps a Kazakh summary in Kazakh", () => {
    const payload = view();
    payload.result.extraction.languages = ["kk"];
    payload.result.extraction.stories[0] = {
      story_id: "story_1",
      title: "Лия және Алматыдағы оқу жылдары",
      summary:
        "Әпкесі Лия бала кезінен кітап оқығанды ұнататын. Мектептен кейін ол " +
        "Алматыға оқуға кетті, бірақ демалыста үйге оралатын.",
    };
    const analysis = readAnalysis(payload);
    expect(analysis.languages).toContain("kk");
    // Characters that exist only in the Kazakh alphabet.
    expect(analysis.summary).toMatch(/[әіңғүұқөһ]/);
    expect(analysis.summary!.trimEnd()).toMatch(/[.!?…]$/);
  });

  it("survives partial, empty and malformed payloads", () => {
    for (const payload of [null, undefined, {}, { result: {} }, "nonsense", 42]) {
      const analysis = readAnalysis(payload);
      expect(analysis.people).toEqual([]);
      expect(analysis.summary).toBeNull();
      expect(isPresentable(analysis)).toBe(false);
    }
  });

  it("accepts a bare PipelineResult as well as the full view", () => {
    const bare = view().result;
    expect(readAnalysis(bare).summary).toBe(SUMMARY_RU);
  });

  it("is presentable once a summary or title exists", () => {
    expect(isPresentable(readAnalysis(view()))).toBe(true);
  });
});
