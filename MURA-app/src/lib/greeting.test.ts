import { describe, expect, it } from "vitest";
import { greetingKeyForHour } from "@/lib/i18n";

/**
 * The greeting used to read «Доброе утро» at 00:04, because the ladder started
 * at `hour < 12`. Every hour is checked rather than "a" time, so a future edit
 * to the boundaries cannot quietly reopen the same hole.
 */
describe("greetingKeyForHour", () => {
  it("greets the small hours as night, not morning", () => {
    for (const hour of [0, 1, 2, 3, 4]) {
      expect(greetingKeyForHour(hour)).toBe("goodNight");
    }
  });

  it("greets late evening as night", () => {
    expect(greetingKeyForHour(23)).toBe("goodNight");
  });

  it("covers every hour of the day exactly once", () => {
    const byKey: Record<string, number[]> = {};
    for (let hour = 0; hour < 24; hour += 1) {
      (byKey[greetingKeyForHour(hour)] ??= []).push(hour);
    }
    expect(byKey).toEqual({
      goodNight: [0, 1, 2, 3, 4, 23],
      goodMorning: [5, 6, 7, 8, 9, 10, 11],
      goodAfternoon: [12, 13, 14, 15, 16, 17],
      goodEvening: [18, 19, 20, 21, 22],
    });
  });

  it("names all four parts of the day", () => {
    const keys = new Set(
      Array.from({ length: 24 }, (_, hour) => greetingKeyForHour(hour)),
    );
    expect(keys.size).toBe(4);
  });
});
