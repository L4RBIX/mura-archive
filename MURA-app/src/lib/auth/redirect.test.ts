/**
 * Post-login return paths.
 *
 * An open redirect on a login page is how a convincing phishing hop gets built:
 * the victim really did sign in to the real site, and is then handed to someone
 * else. Convenience does not outweigh that, so anything not provably
 * same-origin falls back to the home screen.
 */

import { describe, expect, it } from "vitest";
import { safeRedirectPath } from "@/lib/auth/redirect";

describe("safe redirect", () => {
  it("returns the user to the screen they wanted", () => {
    expect(safeRedirectPath("/record")).toBe("/record");
    expect(safeRedirectPath("/settings")).toBe("/settings");
    expect(safeRedirectPath("/story/blue-bicycle")).toBe("/story/blue-bicycle");
    expect(safeRedirectPath("/record?mode=transcript")).toBe("/record?mode=transcript");
  });

  it("falls back to home when nothing was requested", () => {
    expect(safeRedirectPath(null)).toBe("/home");
    expect(safeRedirectPath(undefined)).toBe("/home");
    expect(safeRedirectPath("")).toBe("/home");
  });

  it("refuses to leave the origin", () => {
    for (const hostile of [
      "https://evil.example/steal",
      "http://evil.example",
      "//evil.example",
      "//evil.example/path",
      "/\\evil.example",
      "javascript:alert(1)",
      "/javascript:alert(1)",
      "data:text/html,<script>",
      "evil.example",
      "../../etc",
    ]) {
      expect(safeRedirectPath(hostile)).toBe("/home");
    }
  });
});
