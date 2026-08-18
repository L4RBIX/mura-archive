/**
 * The Clerk adapter's decision table and its cost, tested without Clerk.
 *
 * `toServerAuthSession` is pure over an injected auth state precisely so these
 * cases -- signed out, half-established session, template failure, cache reuse,
 * concurrent bootstrap -- can be exercised deterministically. The cost
 * assertions matter as much as the correctness ones: minting a template token
 * is a ~550ms Clerk Backend API call, measured against the live instance, so
 * "how many times did we mint" is a user-visible property.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  obtainCoreToken,
  toServerAuthSession,
  type ClerkAuthState,
} from "@/lib/auth/providers/clerk/adapter";
import {
  DEFAULT_CORE_AUDIENCE,
  DEFAULT_TOKEN_TEMPLATE,
  readClerkConfig,
} from "@/lib/auth/providers/clerk/config";
import {
  cacheToken,
  clearTokenCache,
  getCachedToken,
  readExpiryMs,
} from "@/lib/auth/providers/clerk/token-cache";
import { satisfiesAudience } from "@/lib/auth/providers/clerk/token-strategy";

const SESSION = "sess_abc123";
const USER = "user_clerk_abc123";
const TEMPLATE = "mura-core";
const AUDIENCE = "mura-core";
const options = { template: TEMPLATE, audience: AUDIENCE };

function encode(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

/** A structurally valid unsigned JWT. Only `exp`/`aud` are read locally. */
function token(expSeconds: number, payload: Record<string, unknown> = {}): string {
  return `${encode({ alg: "RS256", typ: "JWT" })}.${encode({ exp: expSeconds, ...payload })}.sig`;
}

function soon(offset = 600): number {
  return Math.floor(Date.now() / 1000) + offset;
}

/** Mirrors the live instance: session token has no `aud`, template token does. */
function clerkLike(overrides: Partial<ClerkAuthState> = {}): ClerkAuthState {
  return {
    userId: USER,
    sessionId: SESSION,
    getToken: vi.fn(async (o?: { template?: string }) =>
      o?.template ? token(soon(), { aud: AUDIENCE }) : token(soon()),
    ),
    ...overrides,
  };
}

/** Counts only template mints, which are the calls that cost a round trip. */
function countingState(sessionId = SESSION) {
  const mints = { count: 0 };
  const state = clerkLike({
    sessionId,
    getToken: vi.fn(async (o?: { template?: string }) => {
      if (o?.template) mints.count += 1;
      return o?.template ? token(soon(), { aud: AUDIENCE }) : token(soon());
    }),
  });
  return { state, mints };
}

beforeEach(() => clearTokenCache());
afterEach(() => {
  clearTokenCache();
  vi.unstubAllEnvs();
});

describe("mapping a Clerk session", () => {
  it("returns a token for an authenticated session", async () => {
    const session = await toServerAuthSession(clerkLike(), options);

    expect(session.status).toBe("authenticated");
    expect(session).toHaveProperty("accessToken");
  });

  it("is unauthenticated with no user", async () => {
    expect(await toServerAuthSession(clerkLike({ userId: null }), options)).toEqual({
      status: "unauthenticated",
    });
  });

  it("is unauthenticated with a user but no session", async () => {
    expect(await toServerAuthSession(clerkLike({ sessionId: null }), options)).toEqual({
      status: "unauthenticated",
    });
  });

  it("refuses when no token can be produced rather than sending nothing", async () => {
    const session = await toServerAuthSession(clerkLike({ getToken: async () => null }), options);

    expect(session).toEqual({ status: "unauthenticated" });
  });

  it("never asks Clerk for a token before a session exists", async () => {
    const getToken = vi.fn(async () => token(soon()));

    await toServerAuthSession(clerkLike({ userId: null, getToken }), options);

    expect(getToken).not.toHaveBeenCalled();
  });
});

describe("token strategy", () => {
  it("falls back to the template when the session token has no audience", async () => {
    // The live instance's behaviour today: Core requires `aud` and the session
    // token carries none, so the Backend API call is unavoidable.
    const state = clerkLike();

    const choice = await obtainCoreToken(state, options);

    expect(choice?.source).toBe("template");
    expect(state.getToken).toHaveBeenCalledWith({ template: TEMPLATE });
  });

  it("prefers the session token when it already carries the audience", async () => {
    // If the Clerk Dashboard adds `aud` to the session token, the ~550ms
    // Backend API round trip disappears with no code change here.
    const getToken = vi.fn(async () => token(soon(), { aud: AUDIENCE }));

    const choice = await obtainCoreToken(clerkLike({ getToken }), options);

    expect(choice?.source).toBe("session");
    expect(getToken).toHaveBeenCalledTimes(1);
    expect(getToken).toHaveBeenCalledWith();
  });

  it("accepts an audience array, as RFC 7519 allows", () => {
    expect(satisfiesAudience(token(soon(), { aud: [AUDIENCE, "x"] }), AUDIENCE)).toBe(true);
    expect(satisfiesAudience(token(soon(), { aud: ["x"] }), AUDIENCE)).toBe(false);
    expect(satisfiesAudience(token(soon()), AUDIENCE)).toBe(false);
    expect(satisfiesAudience("not-a-jwt", AUDIENCE)).toBe(false);
  });

  it("never sends a session token whose audience is wrong", async () => {
    // Sending it would trade a latency win for a guaranteed 401 from Core.
    const getToken = vi.fn(async (o?: { template?: string }) =>
      o?.template ? token(soon(), { aud: AUDIENCE }) : token(soon(), { aud: "someone-else" }),
    );

    expect((await obtainCoreToken(clerkLike({ getToken }), options))?.source).toBe("template");
  });

  it("uses the configured template name", async () => {
    const state = clerkLike();

    await obtainCoreToken(state, { template: "custom-template", audience: AUDIENCE });

    expect(state.getToken).toHaveBeenCalledWith({ template: "custom-template" });
  });
});

describe("token cache", () => {
  it("reuses a live token instead of minting on every proxied request", async () => {
    // Job polling runs every 1.5s; without this each poll would pay a Clerk
    // round trip before it even reached Core.
    const { state, mints } = countingState();

    await toServerAuthSession(state, options);
    await toServerAuthSession(state, options);
    await toServerAuthSession(state, options);

    expect(mints.count).toBe(1);
  });

  it("mints once for a concurrent bootstrap instead of once per request", async () => {
    // /v1/me, /v1/families and /v1/capabilities start together on page load.
    // Before single-flight they all missed the cache and each minted its own.
    const { state, mints } = countingState();

    await Promise.all([
      toServerAuthSession(state, options),
      toServerAuthSession(state, options),
      toServerAuthSession(state, options),
    ]);

    expect(mints.count).toBe(1);
  });

  it("does not serialise unrelated sessions", async () => {
    const first = countingState("sess_one");
    const second = countingState("sess_two");

    await Promise.all([
      toServerAuthSession(first.state, options),
      toServerAuthSession(second.state, options),
    ]);

    expect(first.mints.count).toBe(1);
    expect(second.mints.count).toBe(1);
  });

  it("recovers from a failed mint instead of wedging the session", async () => {
    let attempt = 0;
    const state = clerkLike({
      getToken: vi.fn(async (o?: { template?: string }) => {
        if (!o?.template) return token(soon());
        attempt += 1;
        if (attempt === 1) throw new Error("clerk unavailable");
        return token(soon(), { aud: AUDIENCE });
      }),
    });

    await expect(toServerAuthSession(state, options)).rejects.toThrow();
    // The in-flight entry must have been cleared, or this would hang or reuse
    // the rejected promise forever.
    expect((await toServerAuthSession(state, options)).status).toBe("authenticated");
  });

  it("keeps most of a 60-second token rather than half of it", async () => {
    // Clerk template tokens live 60s. A 30s margin threw away half the life and
    // forced a ~550ms mint every 30s; the margin now covers the hop, not more.
    const now = Date.now();
    const mints = { count: 0 };
    const state = clerkLike({
      getToken: vi.fn(async (o?: { template?: string }) => {
        if (o?.template) mints.count += 1;
        const exp = Math.floor(now / 1000) + 60;
        return o?.template ? token(exp, { aud: AUDIENCE }) : token(exp);
      }),
    });

    await toServerAuthSession(state, { ...options, now });
    await toServerAuthSession(state, { ...options, now: now + 45_000 });

    expect(mints.count).toBe(1);
  });

  it("re-mints once the cached token nears expiry", async () => {
    const now = Date.now();
    const mints = { count: 0 };
    const state = clerkLike({
      getToken: vi.fn(async (o?: { template?: string }) => {
        if (o?.template) mints.count += 1;
        const exp = Math.floor(now / 1000) + 60;
        return o?.template ? token(exp, { aud: AUDIENCE }) : token(exp);
      }),
    });

    await toServerAuthSession(state, { ...options, now });
    // 55s later under 10s remains, so it is treated as gone: a token handed out
    // at the last second would arrive at Core expired.
    await toServerAuthSession(state, { ...options, now: now + 55_000 });

    expect(mints.count).toBe(2);
  });

  it("keeps sessions separate", () => {
    const now = Date.now();
    cacheToken("sess_a", token(soon()), now);

    expect(getCachedToken("sess_a", now)).not.toBeNull();
    expect(getCachedToken("sess_b", now)).toBeNull();
  });

  it("does not store a token whose expiry cannot be read", () => {
    const now = Date.now();

    cacheToken(SESSION, "not-a-jwt", now);
    cacheToken(SESSION, "header.payload", now);

    expect(getCachedToken(SESSION, now)).toBeNull();
  });

  it("does not store an already-expired token", () => {
    const now = Date.now();

    cacheToken(SESSION, token(Math.floor(now / 1000) - 10), now);

    expect(getCachedToken(SESSION, now)).toBeNull();
  });

  it("reads exp without needing a valid signature", () => {
    expect(readExpiryMs(token(1_700_000_000))).toBe(1_700_000_000_000);
    expect(readExpiryMs("garbage")).toBeNull();
  });
});

describe("configuration", () => {
  it("fails closed when Clerk keys are missing", () => {
    expect(readClerkConfig({}).ok).toBe(false);
    expect(readClerkConfig({ CLERK_SECRET_KEY: "sk" }).ok).toBe(false);
    expect(readClerkConfig({ NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "pk" }).ok).toBe(false);
  });

  it("names what is missing without echoing any value", () => {
    const result = readClerkConfig({ CLERK_SECRET_KEY: "sk_test_secret_value" });

    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.missing).toEqual(["NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"]);
    expect(JSON.stringify(result)).not.toContain("sk_test_secret_value");
  });

  it("defaults template and audience but lets a deployment override them", () => {
    const base = { NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: "pk", CLERK_SECRET_KEY: "sk" };

    const fallback = readClerkConfig(base);
    const overridden = readClerkConfig({
      ...base,
      CLERK_JWT_TEMPLATE: "other",
      MURA_CORE_AUDIENCE: "other-aud",
    });

    expect(fallback.ok && fallback.config.tokenTemplate).toBe(DEFAULT_TOKEN_TEMPLATE);
    expect(fallback.ok && fallback.config.audience).toBe(DEFAULT_CORE_AUDIENCE);
    expect(overridden.ok && overridden.config.tokenTemplate).toBe("other");
    expect(overridden.ok && overridden.config.audience).toBe("other-aud");
  });
});
