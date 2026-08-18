import { describe, expect, it } from "vitest";
import {
  AUTH_PROVIDER_UNCONFIGURED,
  AUTHENTICATION_REQUIRED,
  INVALID_TOKEN,
  isSignedIn,
  sessionFromFailure,
  shouldRetryAfter,
} from "@/lib/auth/session";

describe("session status from a failed /v1/me", () => {
  it("treats a missing or rejected token as signed out", () => {
    expect(sessionFromFailure(401, AUTHENTICATION_REQUIRED)).toEqual({
      status: "unauthenticated",
    });
    expect(sessionFromFailure(401, INVALID_TOKEN)).toEqual({ status: "unauthenticated" });
  });

  it("distinguishes an unconfigured provider from a signed-out user", () => {
    // There is nothing to sign into yet, so prompting for a login would be a
    // lie and blaming an outage would be a different lie.
    expect(sessionFromFailure(401, AUTH_PROVIDER_UNCONFIGURED)).toEqual({
      status: "provider_unconfigured",
    });
  });

  it("does not turn a Core outage into a signed-out session", () => {
    expect(sessionFromFailure(503, "service_unavailable")).toEqual({
      status: "error",
      code: "service_unavailable",
    });
    expect(sessionFromFailure(500, "internal_error").status).toBe("error");
    expect(sessionFromFailure(504, "upstream_timeout").status).toBe("error");
  });

  it("does not treat a role refusal as a broken session", () => {
    // 403 means the user is authenticated and simply lacks the capability.
    // Signing them out would be the wrong remedy for the wrong problem.
    expect(sessionFromFailure(403, "insufficient_family_role")).toEqual({
      status: "error",
      code: "insufficient_family_role",
    });
  });
});

describe("retry discipline", () => {
  it("stops retrying once there is nothing that could succeed", () => {
    // No provider means no refresh, so a retry would resend the same rejected
    // token forever.
    expect(shouldRetryAfter({ status: "unauthenticated" })).toBe(false);
    expect(shouldRetryAfter({ status: "provider_unconfigured" })).toBe(false);
  });

  it("still allows retrying a transient failure", () => {
    expect(shouldRetryAfter({ status: "error", code: "service_unavailable" })).toBe(true);
    expect(shouldRetryAfter({ status: "loading" })).toBe(true);
  });
});

describe("sign-in predicate", () => {
  it("is true only for an authenticated session", () => {
    expect(
      isSignedIn({
        status: "authenticated",
        user: { userId: `user_${"a".repeat(32)}`, email: null, displayName: null },
      }),
    ).toBe(true);
    expect(isSignedIn({ status: "loading" })).toBe(false);
    expect(isSignedIn({ status: "unauthenticated" })).toBe(false);
    expect(isSignedIn({ status: "provider_unconfigured" })).toBe(false);
    expect(isSignedIn({ status: "error", code: "boom" })).toBe(false);
  });
});
