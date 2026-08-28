"use client";

import { useCallback, useEffect, useState } from "react";
import type { TranslationKey } from "@/lib/i18n";

/**
 * Where the person holding the phone sits in the family.
 *
 * ## What this is not
 *
 * It is **not** an archive Person, and it never becomes one. A MURA account is
 * not a `person_id`: Core mints canonical people through entity resolution from
 * what was actually said, and an account claiming to be somebody's grandmother
 * is a claim nobody made out loud. Nothing here is sent to Core, nothing here
 * is written into a recording, and nothing here influences who a story is
 * attributed to — the recorder still asks who is speaking, every time, and
 * still refuses to submit until it is told.
 *
 * ## What it actually does
 *
 * It decides which questions the product offers first.
 *
 * That is the whole feature, and it is deliberately the whole feature. The
 * hardest part of recording a family memory is the first sentence, and the
 * useful opening is different depending on who is in the room: someone
 * recording their own life is asked about their own childhood, someone sitting
 * with an elder is handed questions to ask them. A preference that changed
 * nothing visible would be a form that pretends to configure something, which
 * is the same lie as a fabricated transcript.
 */

export type NarratorRole = "child" | "parent" | "grandparent" | "other";

const STORAGE_KEY = "mura-narrator-role";
const CHANGED_EVENT = "mura:narrator-role-changed";

export const NARRATOR_ROLES: ReadonlyArray<{
  value: NarratorRole;
  labelKey: TranslationKey;
}> = [
  { value: "child", labelKey: "roleAsChild" },
  { value: "parent", labelKey: "roleAsParent" },
  { value: "grandparent", labelKey: "roleAsGrandparent" },
  { value: "other", labelKey: "roleAsOther" },
];

export function isNarratorRole(value: unknown): value is NarratorRole {
  return value === "child" || value === "parent" || value === "grandparent" || value === "other";
}

export function readNarratorRole(): NarratorRole | null {
  if (typeof window === "undefined") return null;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return isNarratorRole(stored) ? stored : null;
}

export function useNarratorRole(): {
  role: NarratorRole | null;
  setRole: (next: NarratorRole) => void;
  /** False until the stored value has been read, so nothing flashes. */
  resolved: boolean;
} {
  const [role, setState] = useState<NarratorRole | null>(null);
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    setState(readNarratorRole());
    setResolved(true);
    const sync = () => setState(readNarratorRole());
    window.addEventListener(CHANGED_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(CHANGED_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const setRole = useCallback((next: NarratorRole) => {
    window.localStorage.setItem(STORAGE_KEY, next);
    setState(next);
    window.dispatchEvent(new Event(CHANGED_EVENT));
  }, []);

  return { role, setRole, resolved };
}

/**
 * The openings offered, ordered for whoever is in the room.
 *
 * Every entry is one of the prompts the recorder already carries — the role
 * reorders them, it does not invent a second set of questions that would then
 * have to be kept in step with the first in three languages.
 *
 * A grandparent is most likely recording their own life, so their own childhood
 * comes first. A child or grandchild is most likely sitting opposite someone
 * else, so the questions that open somebody up about their past come first.
 * `other` keeps the neutral order, which is also the order used before anyone
 * has answered.
 */
const NEUTRAL_ORDER: readonly TranslationKey[] = [
  "promptChildhoodHome",
  "promptFirstMemory",
  "promptParents",
  "promptMeeting",
  "promptHardYears",
  "promptHoliday",
  "promptFood",
  "promptAdvice",
];

const BY_ROLE: Record<NarratorRole, readonly TranslationKey[]> = {
  // Recording their own life.
  grandparent: [
    "promptChildhoodHome",
    "promptFirstMemory",
    "promptMeeting",
    "promptHardYears",
    "promptAdvice",
    "promptParents",
    "promptHoliday",
    "promptFood",
  ],
  parent: [
    "promptChildhoodHome",
    "promptParents",
    "promptMeeting",
    "promptHoliday",
    "promptFirstMemory",
    "promptFood",
    "promptHardYears",
    "promptAdvice",
  ],
  // Sitting with someone older, asking.
  child: [
    "promptParents",
    "promptChildhoodHome",
    "promptMeeting",
    "promptHardYears",
    "promptAdvice",
    "promptHoliday",
    "promptFirstMemory",
    "promptFood",
  ],
  other: NEUTRAL_ORDER,
};

export function promptsForRole(role: NarratorRole | null, limit?: number): TranslationKey[] {
  const ordered = role ? BY_ROLE[role] : NEUTRAL_ORDER;
  return [...(limit ? ordered.slice(0, limit) : ordered)];
}
