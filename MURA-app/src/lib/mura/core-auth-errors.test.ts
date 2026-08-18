/**
 * 401, 403 and 404 mean three different things and must never be merged.
 *
 * The failure this guards against is the old habit of catching everything and
 * showing "network error": a role refusal, an expired session and a family that
 * was revoked each need a different response from the app, and none of them is
 * a network problem.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AUTH_PROVIDER_UNCONFIGURED,
  AUTHENTICATION_REQUIRED,
  INVALID_TOKEN,
  sessionFromFailure,
} from "@/lib/auth/session";
import {
  CoreRequestError,
  createFamily,
  fetchFamilies,
  fetchFamilyMembers,
  fetchMe,
  fetchRecordingResult,
  removeMember,
  updateMemberRole,
} from "@/lib/mura/core-api";

const FAMILY = `family_${"a".repeat(32)}`;
const USER = `user_${"c".repeat(32)}`;
const RECORDING = `rec_${"a".repeat(32)}`;

function coreError(status: number, code: string, message = "…") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(
        JSON.stringify({ error: { code, message, retryable: false, request_id: "req_1" } }),
        { status, headers: { "content-type": "application/json" } },
      ),
    ),
  );
}

function ok(body: unknown, status = 200) {
  const spy = vi.fn(async () =>
    status === 204
      ? new Response(null, { status })
      : new Response(JSON.stringify(body), {
          status,
          headers: { "content-type": "application/json" },
        }),
  );
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("401 is a session problem", () => {
  it.each([AUTHENTICATION_REQUIRED, INVALID_TOKEN])(
    "maps %s to a signed-out session",
    async (code) => {
      coreError(401, code);

      const error = await fetchMe().catch((value) => value);

      expect(error).toBeInstanceOf(CoreRequestError);
      expect(sessionFromFailure(error.status, error.api.code).status).toBe("unauthenticated");
    },
  );

  it("maps the proxy's unconfigured-provider code to its own state", async () => {
    coreError(401, AUTH_PROVIDER_UNCONFIGURED);

    const error = await fetchMe().catch((value) => value);

    expect(sessionFromFailure(error.status, error.api.code).status).toBe(
      "provider_unconfigured",
    );
  });
});

describe("403 is a permission problem, not a session problem", () => {
  it("surfaces the role refusal without signing the user out", async () => {
    coreError(403, "insufficient_family_role");

    const error = await updateMemberRole(FAMILY, USER, "owner").catch((value) => value);

    expect(error.status).toBe(403);
    expect(error.api.code).toBe("insufficient_family_role");
    expect(sessionFromFailure(error.status, error.api.code).status).not.toBe(
      "unauthenticated",
    );
  });
});

describe("404 distinguishes a revoked family from a missing resource", () => {
  it("reports family_not_found when the selection is no longer authorized", async () => {
    coreError(404, "family_not_found");

    const error = await fetchFamilyMembers(FAMILY).catch((value) => value);

    expect(error.status).toBe(404);
    // The remedy is to reload the authorized list, not to sign out.
    expect(error.api.code).toBe("family_not_found");
  });

  it("reports a plain not_found for a resource inside an authorized family", async () => {
    coreError(404, "not_found");

    const error = await fetchRecordingResult(RECORDING, FAMILY).catch((value) => value);

    expect(error.status).toBe(404);
    expect(error.api.code).toBe("not_found");
  });
});

describe("errors are never flattened into a network failure", () => {
  it("keeps the canonical code and request id", async () => {
    coreError(409, "sole_owner_required");

    const error = await removeMember(FAMILY, USER).catch((value) => value);

    expect(error.api).toMatchObject({ code: "sole_owner_required", requestId: "req_1" });
    expect(error.message).not.toMatch(/network/i);
  });
});

describe("family client requests", () => {
  it("lists families from the authorized endpoint", async () => {
    const spy = ok([]);

    await fetchFamilies();

    expect((spy.mock.calls[0] as unknown as [string])[0]).toBe("/api/mura/v1/families");
  });

  it("sends only the name when creating a family", async () => {
    // The owner is the authenticated principal; the body cannot name one.
    const spy = ok({ family_id: FAMILY, name: "Отбасы", role: "owner", capabilities: [] });

    await createFamily("Отбасы");

    const [url, init] = spy.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/mura/v1/families");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ name: "Отбасы" });
  });

  it("handles the empty 204 body when removing a member", async () => {
    ok(null, 204);

    await expect(removeMember(FAMILY, USER)).resolves.toBeUndefined();
  });

  it("never exposes the provider subject or issuer through /v1/me", async () => {
    ok({ user_id: USER, email: null, display_name: "Айсұлу" });

    const me = await fetchMe();

    expect(me.user_id).toBe(USER);
    expect(Object.keys(me)).not.toContain("auth_subject");
    expect(Object.keys(me)).not.toContain("issuer");
  });
});
