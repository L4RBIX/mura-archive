/**
 * Which family the app is acting in, and how it got there.
 *
 * The rule that shapes this module: the authorized family list comes from Core
 * and nothing else. A remembered id is a UI convenience, never a claim — it is
 * checked against the server's list before it is allowed to scope a request, so
 * editing localStorage cannot point the app at somebody else's archive. Core
 * would refuse anyway, but sending the request at all would be a bug worth
 * catching here.
 *
 * The selection logic is deliberately pure so the whole matrix (none, one,
 * several, stale preference, revoked family) is testable without React.
 */

import type { FamilyView } from "@/lib/mura/core-api";

export const SELECTED_FAMILY_STORAGE_KEY = "mura.selectedFamilyId";

export type FamilySessionStatus =
  | "loading"
  | "ready"
  /** Signed in, but Core authorizes no family yet. */
  | "no_families"
  | "auth_required"
  | "error";

export interface FamilySession {
  status: FamilySessionStatus;
  families: FamilyView[];
  selectedFamilyId: string | null;
  selectedFamily: FamilyView | null;
  errorCode: string | null;
}

export const INITIAL_FAMILY_SESSION: FamilySession = {
  status: "loading",
  families: [],
  selectedFamilyId: null,
  selectedFamily: null,
  errorCode: null,
};

/**
 * Choose the family to act in.
 *
 * A remembered id survives only if the server still lists it; a family the user
 * was removed from between sessions therefore falls back rather than lingering
 * as a selection that produces 404s. With exactly one family there is nothing to
 * choose, so the chooser never appears. With several, the first authorized
 * family is a safe default: it is stable across reloads because Core orders the
 * list by creation, and any of them is one the user may genuinely read.
 */
export function chooseFamilyId(
  families: readonly FamilyView[],
  rememberedId: string | null,
): string | null {
  if (families.length === 0) return null;
  if (rememberedId && families.some((family) => family.family_id === rememberedId)) {
    return rememberedId;
  }
  return families[0].family_id;
}

/** Build the session state from an authorized list. Never trusts `rememberedId`. */
export function resolveFamilySession(
  families: readonly FamilyView[],
  rememberedId: string | null,
): FamilySession {
  const selectedFamilyId = chooseFamilyId(families, rememberedId);
  const selectedFamily =
    families.find((family) => family.family_id === selectedFamilyId) ?? null;
  return {
    status: families.length === 0 ? "no_families" : "ready",
    families: [...families],
    selectedFamilyId,
    selectedFamily,
    errorCode: null,
  };
}

/** Only an authorized family may be selected, whatever the caller passes. */
export function selectFamily(session: FamilySession, familyId: string): FamilySession {
  const target = session.families.find((family) => family.family_id === familyId);
  if (!target) return session;
  return { ...session, selectedFamilyId: target.family_id, selectedFamily: target };
}

// --------------------------------------------------------------- preference

/**
 * Read the remembered selection.
 *
 * Wrapped because localStorage throws in private-mode Safari and is absent
 * during server rendering, and a preference is never worth a crash.
 */
export function readRememberedFamilyId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(SELECTED_FAMILY_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function rememberFamilyId(familyId: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (familyId === null) window.localStorage.removeItem(SELECTED_FAMILY_STORAGE_KEY);
    else window.localStorage.setItem(SELECTED_FAMILY_STORAGE_KEY, familyId);
  } catch {
    // A preference that cannot be stored is not an error worth surfacing.
  }
}

// ------------------------------------------------------------- capabilities

/**
 * Presentational gating only.
 *
 * Core re-checks every request, so this exists to avoid offering a button that
 * will fail -- not to enforce anything. It reads the capability list Core sent
 * rather than reimplementing the role table, so the two cannot drift.
 */
export function familyAllows(family: FamilyView | null, capability: string): boolean {
  return family?.capabilities.includes(capability) ?? false;
}

export const CREATE_RECORDING = "create_recording";
export const MANAGE_MEMBERS = "manage_members";
export const RESOLVE_CONFLICTS = "resolve_conflicts";
