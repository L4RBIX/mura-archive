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
