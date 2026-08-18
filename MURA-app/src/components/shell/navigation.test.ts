/**
 * Navigation rules, which are behaviour rather than aesthetics.
 *
 * Two things are worth pinning. Chrome must stay off the focus screens: a tab
 * bar on `/record` invites someone to leave mid-recording, usually while they
 * are sitting with the person whose story they are capturing. And a section
 * must stay lit while you are inside it, or the rail claims you are nowhere
 * the moment you open a person.
 */

import { describe, expect, it } from "vitest";
import { hasAppChrome, isActive, NAV_ITEMS } from "./navigation";

describe("app chrome", () => {
  it.each(["/home", "/tree", "/ask", "/settings", "/story/blue-bicycle", "/person/marat"])(
    "%s is inside the product and keeps navigation",
    (path) => {
      expect(hasAppChrome(path)).toBe(true);
    },
  );

  it.each(["/", "/sign-in", "/sign-up"])("%s is outside the product", (path) => {
    // Offering product destinations to someone who cannot reach them yet.
    expect(hasAppChrome(path)).toBe(false);
  });

  it.each(["/record", "/processing"])("%s is a focus screen", (path) => {
    expect(hasAppChrome(path)).toBe(false);
  });

  it("keeps chrome off nested focus routes", () => {
    expect(hasAppChrome("/record/anything")).toBe(false);
    expect(hasAppChrome("/processing?job=job_1")).toBe(false);
  });

  it("concludes nothing without a pathname", () => {
    expect(hasAppChrome(null)).toBe(false);
  });
});

describe("active section", () => {
  it("lights the exact home tab only on home", () => {
    expect(isActive("/home", "/home")).toBe(true);
    expect(isActive("/tree", "/home")).toBe(false);
  });

  it("keeps «Семья» lit while reading a person", () => {
    // A person is reached from the tree and belongs to that section.
    expect(isActive("/person/marat", "/tree")).toBe(true);
    expect(isActive("/tree?center=marat", "/tree")).toBe(true);
  });

  it("does not light unrelated sections", () => {
    expect(isActive("/person/marat", "/ask")).toBe(false);
    expect(isActive("/settings", "/tree")).toBe(false);
  });

  it("lights at most one destination for any product route", () => {
    for (const path of ["/home", "/tree", "/ask", "/settings", "/person/marat"]) {
      const lit = NAV_ITEMS.filter((entry) => isActive(path, entry.href));
      expect(lit.length).toBeLessThanOrEqual(1);
    }
  });
});

describe("navigation definition", () => {
  it("offers exactly one primary action", () => {
    expect(NAV_ITEMS.filter((entry) => entry.primary)).toHaveLength(1);
  });

  it("points every destination at a real product route", () => {
    for (const entry of NAV_ITEMS) {
      expect(entry.href.startsWith("/")).toBe(true);
      expect(entry.labelKey).toBeTruthy();
    }
  });
});
