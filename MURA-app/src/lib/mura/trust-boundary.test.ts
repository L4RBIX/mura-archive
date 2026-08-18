/**
 * A trust boundary is only real if it cannot be crossed by accident.
 *
 * These read the source tree rather than exercise behaviour, because the things
 * being forbidden are re-introductions: one `process.env.MURA_CORE_API_KEY` in a
 * new route handler, or one revived `TRANSITIONAL_FAMILY_ID` default, and the
 * authorization model quietly reverts. A behavioural test would only catch that
 * on the specific path it happened to cover.
 */

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SOURCE_ROOT = "src";

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(entry) ? [path] : [];
  });
}

const PRODUCTION_FILES = sourceFiles(SOURCE_ROOT).filter((path) => !path.includes(".test."));

function offenders(needle: string | RegExp): string[] {
  const pattern = typeof needle === "string" ? null : needle;
  return PRODUCTION_FILES.filter((path) => {
    const source = readFileSync(path, "utf8");
    return pattern ? pattern.test(source) : source.includes(needle as string);
  });
}

describe("the Core service credential", () => {
  it("is never read by production code", () => {
    // The frontend has no service-internal consumer, so holding this credential
    // would buy nothing and reopen the authorization hole PR-03B closed.
    expect(offenders("process.env.MURA_CORE_API_KEY")).toEqual([]);
  });

  it("is not part of the environment contract", () => {
    expect(configuredEnvNames()).not.toContain("MURA_CORE_API_KEY");
  });
});

function configuredEnvNames(): string[] {
  return readFileSync(".env.example", "utf8")
    .split("\n")
    .filter((line) => line.trim() && !line.trim().startsWith("#"))
    .map((line) => line.split("=")[0].trim());
}

describe("the identity provider", () => {
  it("never exposes its secret key to the browser", () => {
    // A NEXT_PUBLIC_ prefix ships the value in the client bundle. On the Clerk
    // secret that is an account takeover, so it is asserted rather than left to
    // review.
    for (const name of configuredEnvNames()) {
      if (name.startsWith("NEXT_PUBLIC_")) expect(name).not.toMatch(/SECRET/i);
    }
    expect(offenders(/NEXT_PUBLIC_[A-Z_]*SECRET/)).toEqual([]);
  });

  it("stays behind the provider-neutral seam", () => {
    // Product code must not import Clerk. Only the adapter directory, the
    // framework-level provider and middleware, and the auth screens may.
    const allowed = [
      join("src", "lib", "auth", "providers", "clerk"),
      join("src", "lib", "auth", "server-session.ts"),
      join("src", "app", "layout.tsx"),
      join("src", "middleware.ts"),
      join("src", "app", "sign-in"),
      join("src", "app", "sign-up"),
      join("src", "components", "family", "account-section.tsx"),
    ];

    for (const path of offenders(/@clerk\//)) {
      expect(
        allowed.some((prefix) => path.startsWith(prefix)),
        `${path} imports Clerk outside the adapter boundary`,
      ).toBe(true);
    }
  });

  it("puts no MURA authorization into the provider layer", () => {
    // Families, roles and person ids live in PostgreSQL. A claim baked into a
    // token would be stale the moment an owner changed a role.
    const clerkFiles = PRODUCTION_FILES.filter((path) =>
      path.startsWith(join("src", "lib", "auth", "providers", "clerk")),
    );

    expect(clerkFiles.length).toBeGreaterThan(0);
    for (const path of clerkFiles) {
      expect(readFileSync(path, "utf8")).not.toMatch(
        /family_id|speaker_person_id|"owner"|"editor"|"viewer"/,
      );
    }
  });
});

describe("the transitional family", () => {
  it("is gone from the source tree", () => {
    // Not merely unused: a surviving constant is a fallback waiting to be
    // reached for the next time a family id is missing.
    expect(offenders("TRANSITIONAL_FAMILY_ID")).toEqual([]);
    expect(offenders("family_mura_app")).toEqual([]);
  });

  it("left no default family argument behind", () => {
    // `familyId: string = something` is how a hardcoded scope survives a
    // migration: the call site keeps compiling and silently reads elsewhere.
    expect(offenders(/familyId\s*:\s*string\s*=/)).toEqual([]);
  });
});

describe("token handling", () => {
  it("never persists a bearer in browser storage", () => {
    // The browser never receives a token at all -- the proxy attaches it
    // server-side -- so any storage write near a token is a regression.
    expect(offenders(/localStorage\.setItem\([^)]*[Tt]oken/)).toEqual([]);
    expect(offenders(/sessionStorage\.setItem\([^)]*[Tt]oken/)).toEqual([]);
  });

  it("keeps server-session resolution in one module", () => {
    const readers = offenders("readServerAuthSession");

    expect(readers.sort()).toEqual(
      [
        join("src", "app", "api", "mura", "[...path]", "proxy.ts"),
        join("src", "lib", "auth", "server-session.ts"),
      ].sort(),
    );
  });
});

describe("user identity is never archive identity", () => {
  it("never assigns a user id to a person field", () => {
    expect(offenders(/speaker_person_id["']?\s*[:,]\s*.*user[_.]?[Ii]d/)).toEqual([]);
    expect(offenders(/speakerPersonId\s*[:=]\s*.*user[_.]?[Ii]d/)).toEqual([]);
  });
});

describe("account creation is reachable", () => {
  // Clerk renders the "Нет аккаунта? Создать аккаунт" footer only when it knows
  // where the other flow lives. Without these it silently hides the link, which
  // is why sign-up looked absent from the app.
  const signIn = join("src", "app", "sign-in", "[[...sign-in]]", "page.tsx");
  const signUp = join("src", "app", "sign-up", "[[...sign-up]]", "page.tsx");

  it("points the sign-in page at sign-up", () => {
    const source = readFileSync(signIn, "utf8");

    expect(source).toContain("signUpUrl");
    expect(source).toContain("/sign-up");
  });

  it("points the sign-up page at sign-in", () => {
    const source = readFileSync(signUp, "utf8");

    expect(source).toContain("signInUrl");
    expect(source).toContain("/sign-in");
  });

  it("declares both flows once, app-wide, on the provider", () => {
    const layout = readFileSync(join("src", "app", "layout.tsx"), "utf8");

    expect(layout).toContain('signInUrl="/sign-in"');
    expect(layout).toContain('signUpUrl="/sign-up"');
  });

  it("carries the return destination through the cross-link", () => {
    // Following "create an account" from /record must still come back to /record.
    for (const path of [signIn, signUp]) {
      expect(readFileSync(path, "utf8")).toContain("redirect_url=");
    }
  });
});

describe("the assistant voice is gone", () => {
  it("leaves no reference to the performers or their clips", () => {
    expect(offenders(/alina|ariana/i)).toEqual([]);
    expect(offenders(/clipUrl|clipsForVoice|mascotAudio|VoicePicker/)).toEqual([]);
  });

  it("has no speech synthesis or automatic playback path", () => {
    // Nothing may make MURA speak: not a mount, not a state change, not an
    // error. There is no speech engine left to call.
    expect(offenders(/speechSynthesis|SpeechSynthesisUtterance/)).toEqual([]);
    expect(offenders(/\.play\(/)).toEqual([]);
    expect(offenders(/new Audio\(/)).toEqual([]);
  });

  it("ships no voice-over assets", () => {
    expect(existsSync(join("public", "audio"))).toBe(false);
  });

  it("leaves no dangling voice modules", () => {
    for (const gone of [
      join("src", "lib", "mascot", "audio-manager.ts"),
      join("src", "lib", "mascot", "clips.ts"),
      join("src", "lib", "mascot", "cues.ts"),
      join("src", "lib", "mascot", "voice-store.ts"),
      join("src", "hooks", "use-mascot-subtitle.ts"),
      join("src", "hooks", "use-audio-energy.ts"),
      join("src", "components", "mascot", "voice-picker.tsx"),
      join("src", "components", "mascot", "mascot-subtitle.tsx"),
    ]) {
      expect(existsSync(gone)).toBe(false);
    }
  });

  it("keeps microphone recording, which is input and not output", () => {
    // ASR input is a different feature from assistant speech, and only the
    // speaking half was removed.
    const recorder = readFileSync(join("src", "hooks", "use-recorder.ts"), "utf8");

    expect(recorder).toContain("getUserMedia");
    expect(recorder).toContain("MediaRecorder");
    expect(recorder).toContain("track.stop()");
  });
});
