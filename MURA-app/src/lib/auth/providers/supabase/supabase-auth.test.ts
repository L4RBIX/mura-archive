import { describe, expect, it } from "vitest";
import { toStoredSession } from "@/lib/auth/providers/supabase/adapter";
import { isSupabaseAuthConfigured, readSupabaseAuthConfig } from "@/lib/auth/providers/supabase/config";
import {
  decodeSession,
  encodeSession,
  isExpired,
  type StoredSession,
} from "@/lib/auth/providers/supabase/session-cookie";

const VALID = {
  NEXT_PUBLIC_SUPABASE_URL: "https://abcdef.supabase.co",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: "anon-key",
};

describe("configuration", () => {
  it("accepts a complete project configuration", () => {
    expect(isSupabaseAuthConfigured(VALID)).toBe(true);
  });

  it("is unconfigured rather than partially configured", () => {
    // A URL with no key must not select the provider: half a configuration
    // would make every request fail as unauthenticated instead of saying why.
    expect(isSupabaseAuthConfigured({ ...VALID, NEXT_PUBLIC_SUPABASE_ANON_KEY: "" })).toBe(false);
    expect(isSupabaseAuthConfigured({})).toBe(false);
  });

  it("rejects a project URL that is not a Supabase origin", () => {
    const result = readSupabaseAuthConfig({ ...VALID, NEXT_PUBLIC_SUPABASE_URL: "https://evil.example.com" });
    expect(result).toEqual({ ok: false, reason: "invalid_NEXT_PUBLIC_SUPABASE_URL" });
  });

  it("strips a trailing slash so derived endpoints never double up", () => {
    const result = readSupabaseAuthConfig({ ...VALID, NEXT_PUBLIC_SUPABASE_URL: "https://abcdef.supabase.co/" });
    expect(result.ok && result.config.projectUrl).toBe("https://abcdef.supabase.co");
  });
});

describe("token payload mapping", () => {
  it("maps a Supabase token response onto a session", () => {
    const session = toStoredSession(
      { access_token: "a", refresh_token: "r", expires_in: 3600 },
      1_000,
    );
    expect(session).toEqual({ accessToken: "a", refreshToken: "r", expiresAt: 4_600 });
  });

  it("refuses a response missing either token", () => {
    expect(toStoredSession({ access_token: "a", expires_in: 60 })).toBeNull();
    expect(toStoredSession({ refresh_token: "r", expires_in: 60 })).toBeNull();
    expect(toStoredSession({})).toBeNull();
  });
});

describe("session cookie", () => {
  const session: StoredSession = { accessToken: "a", refreshToken: "r", expiresAt: 5_000 };

  it("round-trips", () => {
    expect(decodeSession(encodeSession(session))).toEqual(session);
  });

  it("treats a malformed cookie as no session, never as an error", () => {
    expect(decodeSession("not-base64url!!")).toBeNull();
    expect(decodeSession(undefined)).toBeNull();
    expect(decodeSession(Buffer.from('{"accessToken":1}').toString("base64url"))).toBeNull();
  });

  it("refreshes ahead of expiry rather than racing the deadline", () => {
    // 30s of life left is already expired: a request in flight would outlive it.
    expect(isExpired(session, 4_970)).toBe(true);
    expect(isExpired(session, 4_000)).toBe(false);
  });
});
