import { describe, expect, it } from "vitest";
import { pluralForm } from "./plural";

describe("Russian plural agreement", () => {
  it("uses the singular form for 1, 21, 101", () => {
    for (const count of [1, 21, 101, 1001]) {
      expect(pluralForm(count, "ru")).toBe("one");
    }
  });

  it("uses the few form for 2 through 4", () => {
    for (const count of [2, 3, 4, 22, 33, 104]) {
      expect(pluralForm(count, "ru")).toBe("few");
    }
  });

  it("uses the many form for 0, 5 through 20", () => {
    for (const count of [0, 5, 9, 20, 25, 100]) {
      expect(pluralForm(count, "ru")).toBe("many");
    }
  });

  it("treats the teens as many despite their last digit", () => {
    // The exception a naive `count % 10` check gets wrong: 11 ends in 1 but
    // does not take the singular, and 12–14 do not take the few form.
    for (const count of [11, 12, 13, 14, 111, 112]) {
      expect(pluralForm(count, "ru")).toBe("many");
    }
  });
});

describe("Kazakh", () => {
  it("does not inflect after a numeral", () => {
    for (const count of [1, 2, 5, 11, 21]) {
      expect(pluralForm(count, "kk")).toBe("one");
    }
  });
});

describe("English plural agreement", () => {
  it("uses the singular only for exactly one", () => {
    expect(pluralForm(1, "en")).toBe("one");
  });

  it("uses the plural for zero", () => {
    // Unlike the Russian rule, English says "0 people", not "0 person".
    expect(pluralForm(0, "en")).toBe("many");
  });

  it("uses the plural for every other count, including those ending in 1", () => {
    // "21 people", not "21 person" — the Russian last-digit rule would get
    // this wrong, which is why English is not routed through it.
    for (const count of [2, 5, 11, 21, 101, 1001]) {
      expect(pluralForm(count, "en")).toBe("many");
    }
  });
});
