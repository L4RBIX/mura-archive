/**
 * The family selection matrix.
 *
 * The invariant under test throughout: a remembered family id is a hint, and the
 * authorized list from Core is the authority. Every case below is a way that
 * distinction could be lost.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import type { FamilyRole, FamilyView } from "@/lib/mura/core-api";
import {
  CREATE_RECORDING,
  MANAGE_MEMBERS,
  SELECTED_FAMILY_STORAGE_KEY,
  chooseFamilyId,
  familyAllows,
  readRememberedFamilyId,
  rememberFamilyId,
  resolveFamilySession,
  selectFamily,
} from "@/lib/mura/family-session";

const A = `family_${"a".repeat(32)}`;
const B = `family_${"b".repeat(32)}`;
const GONE = `family_${"c".repeat(32)}`;

function family(
  id: string,
  role: FamilyRole = "owner",
  capabilities: string[] = ["read_recordings", "create_recording", "manage_members"],
): FamilyView {
  return { family_id: id, name: `Family ${id.slice(7, 8)}`, role, capabilities };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// --------------------------------------------------------------- zero / one

describe("no authorized family", () => {
  it("selects nothing and says so", () => {
    const session = resolveFamilySession([], null);

    expect(session.status).toBe("no_families");
    expect(session.selectedFamilyId).toBeNull();
    expect(session.selectedFamily).toBeNull();
  });

  it("does not resurrect a remembered family that Core no longer lists", () => {
    // The user was removed between sessions. The stale preference must not
    // become the scope of the next request.
    const session = resolveFamilySession([], GONE);

    expect(session.status).toBe("no_families");
    expect(session.selectedFamilyId).toBeNull();
  });
});

describe("exactly one authorized family", () => {
  it("selects it without asking", () => {
    const session = resolveFamilySession([family(A)], null);

    expect(session.status).toBe("ready");
    expect(session.selectedFamilyId).toBe(A);
    expect(session.selectedFamily?.family_id).toBe(A);
  });

  it("ignores a remembered id that is not the one authorized family", () => {
    const session = resolveFamilySession([family(A)], B);

    expect(session.selectedFamilyId).toBe(A);
  });
});

// ----------------------------------------------------------------- multiple

describe("several authorized families", () => {
  it("restores a remembered selection that is still authorized", () => {
    const session = resolveFamilySession([family(A), family(B)], B);

    expect(session.selectedFamilyId).toBe(B);
  });

  it("falls back safely when the remembered family was revoked", () => {
    const session = resolveFamilySession([family(A), family(B)], GONE);

    expect(session.status).toBe("ready");
    expect(session.selectedFamilyId).toBe(A);
  });

  it("switches only to a family the server authorized", () => {
    const session = resolveFamilySession([family(A), family(B)], null);

    expect(selectFamily(session, B).selectedFamilyId).toBe(B);
    // A forged id changes nothing rather than becoming the request scope.
    expect(selectFamily(session, GONE).selectedFamilyId).toBe(A);
    expect(selectFamily(session, "").selectedFamilyId).toBe(A);
  });

  it("keeps the selected family object in step with the selected id", () => {
    // The two must never disagree: rendering family A's name while scoping
    // requests to family B is exactly the confusion this guards against.
    const switched = selectFamily(resolveFamilySession([family(A), family(B)], null), B);

    expect(switched.selectedFamily?.family_id).toBe(switched.selectedFamilyId);
  });
});

describe("choice function", () => {
  it("never invents a family", () => {
    expect(chooseFamilyId([], null)).toBeNull();
    expect(chooseFamilyId([], "family_mura_app")).toBeNull();
  });

  it("never returns an id outside the authorized list", () => {
    const authorized = [family(A), family(B)];

    for (const remembered of [null, "", GONE, "family_mura_app", "../etc"]) {
      const chosen = chooseFamilyId(authorized, remembered);
      expect(authorized.some((entry) => entry.family_id === chosen)).toBe(true);
    }
  });
});

// --------------------------------------------------------------- preference

describe("stored preference", () => {
  function storage(initial: Record<string, string> = {}) {
    const map = new Map(Object.entries(initial));
    return {
      getItem: (key: string) => map.get(key) ?? null,
      setItem: (key: string, value: string) => void map.set(key, value),
      removeItem: (key: string) => void map.delete(key),
      read: (key: string) => map.get(key) ?? null,
    };
  }

  it("round-trips the selected family id", () => {
    const store = storage();
    vi.stubGlobal("window", { localStorage: store });

    rememberFamilyId(B);

    expect(store.read(SELECTED_FAMILY_STORAGE_KEY)).toBe(B);
    expect(readRememberedFamilyId()).toBe(B);
  });

  it("clears the preference when nothing is selected", () => {
    const store = storage({ [SELECTED_FAMILY_STORAGE_KEY]: B });
    vi.stubGlobal("window", { localStorage: store });

    rememberFamilyId(null);

    expect(store.read(SELECTED_FAMILY_STORAGE_KEY)).toBeNull();
  });

  it("survives storage being unavailable", () => {
    // Private-mode Safari throws on write. A preference is never worth a crash.
    vi.stubGlobal("window", {
      localStorage: {
        getItem: () => {
          throw new Error("denied");
        },
        setItem: () => {
          throw new Error("denied");
        },
        removeItem: () => {
          throw new Error("denied");
        },
      },
    });

    expect(readRememberedFamilyId()).toBeNull();
    expect(() => rememberFamilyId(A)).not.toThrow();
  });

  it("reads nothing during server rendering", () => {
    vi.stubGlobal("window", undefined);

    expect(readRememberedFamilyId()).toBeNull();
    expect(() => rememberFamilyId(A)).not.toThrow();
  });

  it("is a hint and never an authorization", () => {
    const store = storage({ [SELECTED_FAMILY_STORAGE_KEY]: GONE });
    vi.stubGlobal("window", { localStorage: store });

    // Someone edited localStorage to a family they are not a member of.
    const session = resolveFamilySession([family(A)], readRememberedFamilyId());

    expect(session.selectedFamilyId).toBe(A);
  });
});

// -------------------------------------------------------- capability gating

describe("presentational capability gating", () => {
  it("reads the capability list Core sent rather than re-deriving roles", () => {
    const viewer = family(B, "viewer", ["read_recordings", "read_jobs"]);

    expect(familyAllows(viewer, CREATE_RECORDING)).toBe(false);
    expect(familyAllows(viewer, MANAGE_MEMBERS)).toBe(false);
    expect(familyAllows(family(A, "editor", ["create_recording"]), CREATE_RECORDING)).toBe(
      true,
    );
  });

  it("allows nothing when no family is selected", () => {
    expect(familyAllows(null, CREATE_RECORDING)).toBe(false);
  });
});
