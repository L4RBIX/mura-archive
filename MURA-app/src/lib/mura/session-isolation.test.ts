/**
 * Local recordings belong to the session that made them.
 *
 * The reported bug: a locally recorded memory stayed after sign-out and was
 * visible — and playable — to whoever signed in next. Local recordings lived
 * under one global localStorage key and one global IndexedDB store, with no
 * notion of who made them.
 *
 * The policy these tests pin down:
 *
 *   unsent draft            -> dropped when the account changes
 *   local SavedMemory/audio -> deleted on that account's own logout
 *   canonical Core recording-> untouched; logout issues no backend request
 *
 * And one deliberate non-behaviour: another account signing in does *not*
 * delete a third party's namespace. Scoped reads already make it unreachable,
 * and destroying someone else's data because a different person logged in
 * would be vandalism dressed up as hygiene.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getMemoryOwner,
  getSavedMemories,
  onMemoryOwnerChange,
  purgeLocalRecordingsFor,
  saveMemory,
  setMemoryOwner,
  type SavedMemory,
} from "@/lib/memory-store";

const USER_A = `user_${"a".repeat(32)}`;
const USER_B = `user_${"b".repeat(32)}`;
const PREFIX = "mura-saved-memories-v1";
const LEGACY_KEY = PREFIX;

function memory(id: string): SavedMemory {
  return {
    id,
    createdAt: new Date().toISOString(),
    ui_language_at_creation: "ru",
    audio_language: "auto",
    detected_audio_language: "unknown",
    transcript_language: "unknown",
    output_language: "same_as_transcript",
    title: "Воспоминание",
    summary: "",
    transcript: "тайна",
    people: [],
    durationSec: 3,
    source: "mura_core",
    status: "processing",
    analyzed: false,
  } as SavedMemory;
}

/** A localStorage stand-in; the node test environment has no DOM. */
function installStorage(initial: Record<string, string> = {}) {
  const map = new Map(Object.entries(initial));
  vi.stubGlobal("window", {
    localStorage: {
      get length() {
        return map.size;
      },
      key: (index: number) => [...map.keys()][index] ?? null,
      getItem: (key: string) => map.get(key) ?? null,
      setItem: (key: string, value: string) => void map.set(key, value),
      removeItem: (key: string) => void map.delete(key),
    },
  });
  return map;
}

beforeEach(() => {
  setMemoryOwner(null);
  // Audio lives in IndexedDB, which this environment does not provide.
  vi.stubGlobal("indexedDB", undefined);
});

afterEach(() => {
  setMemoryOwner(null);
  vi.unstubAllGlobals();
});

describe("recordings are addressed by account", () => {
  it("shows nothing while signed out", () => {
    installStorage({ [`${PREFIX}::${USER_A}`]: JSON.stringify([memory("local-1")]) });

    setMemoryOwner(null);

    expect(getSavedMemories()).toEqual([]);
  });

  it("shows only the signed-in account's own recordings", () => {
    installStorage({
      [`${PREFIX}::${USER_A}`]: JSON.stringify([memory("local-a")]),
      [`${PREFIX}::${USER_B}`]: JSON.stringify([memory("local-b")]),
    });

    setMemoryOwner(USER_A);
    expect(getSavedMemories().map((item) => item.id)).toEqual(["local-a"]);

    setMemoryOwner(USER_B);
    expect(getSavedMemories().map((item) => item.id)).toEqual(["local-b"]);
  });

  it("refuses to save a recording with nobody signed in", async () => {
    // Writing it would create exactly the unattributed data that leaked.
    installStorage();
    setMemoryOwner(null);

    await expect(saveMemory(memory("local-x"), new Blob(["x"]))).rejects.toThrow();
  });
});

describe("logging out deletes that account's local recordings", () => {
  it("physically removes the departing account's entries", async () => {
    const store = installStorage({
      [`${PREFIX}::${USER_A}`]: JSON.stringify([memory("local-a")]),
    });
    setMemoryOwner(USER_A);

    // Sign-out: the store is pointed at nobody, then that account is erased.
    setMemoryOwner(null);
    await purgeLocalRecordingsFor(USER_A);

    expect(store.has(`${PREFIX}::${USER_A}`)).toBe(false);
  });

  it("does not resurrect the recording when that account signs back in", async () => {
    // The product requirement in one test: local recordings do not come back.
    const store = installStorage({
      [`${PREFIX}::${USER_A}`]: JSON.stringify([memory("local-a")]),
    });
    setMemoryOwner(USER_A);
    setMemoryOwner(null);
    await purgeLocalRecordingsFor(USER_A);

    setMemoryOwner(USER_A);

    expect(getSavedMemories()).toEqual([]);
    expect(store.has(`${PREFIX}::${USER_A}`)).toBe(false);
  });

  it("purges legacy unscoped entries, whose owner is unknowable", async () => {
    const store = installStorage({ [LEGACY_KEY]: JSON.stringify([memory("legacy-1")]) });

    await purgeLocalRecordingsFor(USER_A);

    expect(store.has(LEGACY_KEY)).toBe(false);
  });

  it("leaves another account's namespace alone", async () => {
    // A logging out is not a reason to destroy B's data. B cannot read it
    // anyway; only B's own logout clears it.
    const store = installStorage({
      [`${PREFIX}::${USER_A}`]: JSON.stringify([memory("mine")]),
      [`${PREFIX}::${USER_B}`]: JSON.stringify([memory("theirs")]),
    });

    await purgeLocalRecordingsFor(USER_A);

    expect(store.has(`${PREFIX}::${USER_A}`)).toBe(false);
    expect(store.has(`${PREFIX}::${USER_B}`)).toBe(true);
  });

  it("does not delete anyone's namespace merely because someone signs in", async () => {
    // Sign-in purges legacy only, which is what the provider passes.
    const store = installStorage({
      [`${PREFIX}::${USER_A}`]: JSON.stringify([memory("a")]),
      [`${PREFIX}::${USER_B}`]: JSON.stringify([memory("b")]),
      [LEGACY_KEY]: JSON.stringify([memory("legacy")]),
    });

    await purgeLocalRecordingsFor(null);

    expect(store.has(`${PREFIX}::${USER_A}`)).toBe(true);
    expect(store.has(`${PREFIX}::${USER_B}`)).toBe(true);
    expect(store.has(LEGACY_KEY)).toBe(false);
  });

  it("leaves unrelated storage alone", async () => {
    // Preferences and demo content are not session-sensitive; wiping them
    // would be collateral damage, not security.
    const store = installStorage({
      "mura.selectedFamilyId": "family_x",
      "mura-ui-locale": "kk",
      [LEGACY_KEY]: "[]",
    });

    await purgeLocalRecordingsFor(USER_A);

    expect(store.has("mura.selectedFamilyId")).toBe(true);
    expect(store.has("mura-ui-locale")).toBe(true);
  });
});

describe("audio blobs follow the same rule", () => {
  /**
   * A minimal IndexedDB stand-in.
   *
   * Worth the setup: the audio blob is the part that was actually playable by
   * the next account, so "the list is empty" would be a hollow guarantee if the
   * bytes survived underneath it.
   */
  function installIndexedDb(initial: string[]) {
    const keys = new Set(initial);
    const store = {
      getAllKeys() {
        const request: Record<string, unknown> = { result: [...keys] };
        queueMicrotask(() => (request.onsuccess as (() => void) | undefined)?.());
        return request;
      },
      delete(key: string) {
        keys.delete(key);
      },
    };
    vi.stubGlobal("indexedDB", {
      open() {
        const request: Record<string, unknown> = {
          result: {
            objectStoreNames: { contains: () => true },
            createObjectStore: () => store,
            transaction() {
              const transaction: Record<string, unknown> = {
                objectStore: () => store,
              };
              // Completion must land after getAllKeys' own callback.
              queueMicrotask(() =>
                queueMicrotask(
                  () => (transaction.oncomplete as (() => void) | undefined)?.(),
                ),
              );
              return transaction;
            },
            close: () => undefined,
          },
        };
        queueMicrotask(() => (request.onsuccess as (() => void) | undefined)?.());
        return request;
      },
    });
    return keys;
  }

  it("deletes the departing account's audio and legacy audio, keeping others'", async () => {
    installStorage();
    const keys = installIndexedDb([
      `${USER_A}::local-a`,
      `${USER_B}::local-b`,
      "legacy-unowned-id",
    ]);

    await purgeLocalRecordingsFor(USER_A);

    expect(keys.has(`${USER_A}::local-a`)).toBe(false);
    expect(keys.has("legacy-unowned-id")).toBe(false);
    expect(keys.has(`${USER_B}::local-b`)).toBe(true);
  });

  it("removes only legacy audio when someone merely signs in", async () => {
    installStorage();
    const keys = installIndexedDb([`${USER_A}::local-a`, "legacy-unowned-id"]);

    await purgeLocalRecordingsFor(null);

    expect(keys.has("legacy-unowned-id")).toBe(false);
    expect(keys.has(`${USER_A}::local-a`)).toBe(true);
  });
});

describe("account switch", () => {
  it("never shows user A's recording to user B", async () => {
    const store = installStorage({
      [`${PREFIX}::${USER_A}`]: JSON.stringify([memory("a-secret")]),
    });
    setMemoryOwner(USER_A);

    setMemoryOwner(null);
    await purgeLocalRecordingsFor(USER_A);
    setMemoryOwner(USER_B);
    await purgeLocalRecordingsFor(null);

    expect(getSavedMemories()).toEqual([]);
    expect(store.has(`${PREFIX}::${USER_A}`)).toBe(false);
  });

  it("hides a dormant namespace even when logout never ran", async () => {
    // Browser closed without signing out: A's data is still on disk. B must
    // not see it, and B signing in must not delete it either.
    const store = installStorage({
      [`${PREFIX}::${USER_A}`]: JSON.stringify([memory("a-dormant")]),
    });

    setMemoryOwner(USER_B);
    await purgeLocalRecordingsFor(null);

    expect(getSavedMemories()).toEqual([]);
    expect(store.has(`${PREFIX}::${USER_A}`)).toBe(true);
  });

  it("notifies open screens the moment the owner changes", () => {
    // Without this the previous account's list stays on screen until the user
    // happens to navigate, and an unsent take is never dropped.
    installStorage();
    const seen: (string | null)[] = [];
    const unsubscribe = onMemoryOwnerChange(() => seen.push(getMemoryOwner()));

    setMemoryOwner(USER_A);
    setMemoryOwner(null);
    unsubscribe();
    setMemoryOwner(USER_B);

    expect(seen).toEqual([USER_A, null]);
  });
});

describe("logout is not a delete operation on the server", () => {
  it("issues no backend request at all", async () => {
    // Local cleanup is client-side only. A recording already accepted by Core
    // is server data with its own lifecycle: no RecordingRow, audio object,
    // job or pipeline result is affected by signing out.
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    installStorage({ [`${PREFIX}::${USER_A}`]: JSON.stringify([memory("local-1")]) });

    setMemoryOwner(USER_A);
    setMemoryOwner(null);
    await purgeLocalRecordingsFor(USER_A);

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
