import { useSyncExternalStore } from "react";
import {
  DEFAULT_AUDIO_LANGUAGE,
  DEFAULT_OUTPUT_LANGUAGE,
  isAudioLanguage,
  isDetectedLanguage,
  isOutputLanguage,
  isUiLanguage,
  type AudioLanguage,
  type DetectedLanguage,
  type OutputLanguage,
  type UiLanguage,
} from "@/lib/language";
import type { Story } from "@/lib/types";

export interface SavedMemoryPerson {
  name: string;
  relationship: string;
  /** Graph person id, when the pipeline resolved this mention to someone. */
  personId?: string;
  /** This recording is what introduced them to the family graph. */
  isNew?: boolean;
}

export interface SavedMemoryEvent {
  title: string;
  description: string;
  dateText: string | null;
  location: string | null;
}

/**
 * Mirrors the backend's job status so the UI can tell "still working" from
 * "finished" from "finished but unverified".
 */
export type SavedMemoryStatus =
  | "processing"
  | "completed"
  | "needs_review"
  | "failed";

export interface SavedMemory {
  id: string;
  createdAt: string;
  ui_language_at_creation: UiLanguage;
  audio_language: AudioLanguage;
  detected_audio_language: DetectedLanguage;
  transcript_language: DetectedLanguage;
  output_language: OutputLanguage;
  title: string;
  summary: string;
  transcript: string;
  people: SavedMemoryPerson[];
  durationSec: number;
  source: "mura_core" | "deepseek_fallback" | "audio_only";
  /** Punctuation-repaired transcript. The raw one stays in `transcript`. */
  cleanTranscript?: string;
  events?: SavedMemoryEvent[];
  places?: string[];
  status?: SavedMemoryStatus;
  /** True once a validated analysis replaced the placeholder title/summary. */
  analyzed?: boolean;
}

const STORAGE_PREFIX = "mura-saved-memories-v1";
/** The pre-PR-03F global key, written before recordings belonged to an account. */
const LEGACY_STORAGE_KEY = STORAGE_PREFIX;
const DB_NAME = "mura-audio-archive-v1";
const STORE_NAME = "recordings";

/**
 * Whose recordings this browser is currently holding.
 *
 * Recordings used to live under one global key and one global audio store, so a
 * recording made by one account stayed on screen -- and stayed playable -- for
 * whoever signed in next. That is the leak this scoping closes: every read and
 * write is now addressed by the authenticated MURA user id, and there is no
 * owner while signed out, so there is nothing to read.
 *
 * This is client-side draft state only. Once a recording has been accepted by
 * Core it is server data, and nothing here deletes any of it.
 */
let owner: string | null = null;

const ownerListeners = new Set<() => void>();

function notifyOwnerChanged() {
  ownerListeners.forEach((listener) => listener());
}

/** Subscribe to owner changes, so open screens can drop foreign state at once. */
export function onMemoryOwnerChange(listener: () => void): () => void {
  ownerListeners.add(listener);
  return () => {
    ownerListeners.delete(listener);
  };
}

export function getMemoryOwner(): string | null {
  return owner;
}

/**
 * The current owner, as reactive state.
 *
 * Screens use this as an effect dependency so a sign-out empties them at once
 * instead of on the next navigation. It is the same identity boundary the
 * session provider uses -- deliberately not a second notion of "user changed".
 */
export function useMemoryOwner(): string | null {
  return useSyncExternalStore(
    onMemoryOwnerChange,
    getMemoryOwner,
    () => null,
  );
}

/**
 * Point the store at an account, or at nobody.
 *
 * Called from the session provider on every identity transition, so sign-out
 * and account switch take effect immediately rather than on next reload.
 */
export function setMemoryOwner(userId: string | null): void {
  if (owner === userId) return;
  owner = userId;
  notifyOwnerChanged();
}

function storageKey(): string | null {
  return owner ? `${STORAGE_PREFIX}::${owner}` : null;
}

/** Audio is keyed by owner too, so one account cannot read another's blob. */
function audioKey(id: string): string | null {
  return owner ? `${owner}::${id}` : null;
}

type StoredMemoryRecord = Record<string, unknown>;

/**
 * Read both the original locale-based schema and the decoupled schema.
 * Existing transcript text is carried byte-for-byte; the old UI locale is
 * never guessed to be the transcript language.
 */
export function migrateSavedMemory(value: unknown): SavedMemory | null {
  if (typeof value !== "object" || value === null) return null;
  const item = value as StoredMemoryRecord;
  if (
    typeof item.id !== "string" ||
    typeof item.title !== "string" ||
    typeof item.createdAt !== "string" ||
    typeof item.transcript !== "string"
  ) {
    return null;
  }

  const uiLanguageAtCreation = isUiLanguage(item.ui_language_at_creation)
    ? item.ui_language_at_creation
    : isUiLanguage(item.locale)
      ? item.locale
      : "ru";
  const withoutLegacyLocale = { ...item };
  delete withoutLegacyLocale.locale;

  return {
    ...withoutLegacyLocale,
    ui_language_at_creation: uiLanguageAtCreation,
    audio_language: isAudioLanguage(item.audio_language)
      ? item.audio_language
      : DEFAULT_AUDIO_LANGUAGE,
    detected_audio_language: isDetectedLanguage(item.detected_audio_language)
      ? item.detected_audio_language
      : "unknown",
    transcript_language: isDetectedLanguage(item.transcript_language)
      ? item.transcript_language
      : "unknown",
    output_language: isOutputLanguage(item.output_language)
      ? item.output_language
      : DEFAULT_OUTPUT_LANGUAGE,
  } as SavedMemory;
}

function openAudioDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE_NAME)) {
        request.result.createObjectStore(STORE_NAME);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function saveAudio(id: string, audio: Blob) {
  const key = audioKey(id);
  if (!key) throw new Error("no signed-in account to save this audio to");
  const database = await openAudioDatabase();
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    transaction.objectStore(STORE_NAME).put(audio, key);
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
  });
  database.close();
}

export async function getMemoryAudio(id: string): Promise<Blob | null> {
  const key = audioKey(id);
  // No owner, no audio. This is the check that stops one account playing back
  // another's recording.
  if (!key) return null;
  const database = await openAudioDatabase();
  const audio = await new Promise<Blob | null>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readonly");
    const request = transaction.objectStore(STORE_NAME).get(key);
    request.onsuccess = () => resolve(request.result instanceof Blob ? request.result : null);
    request.onerror = () => reject(request.error);
  });
  database.close();
  return audio;
}

export function getSavedMemories(): SavedMemory[] {
  if (typeof window === "undefined") return [];
  const key = storageKey();
  // Signed out: there is no owner, so there is nothing of anyone's to show.
  if (!key) return [];
  try {
    const raw = window.localStorage.getItem(key) ?? "[]";
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const migrated = parsed
      .map(migrateSavedMemory)
      .filter((item): item is SavedMemory => item !== null);
    const serialized = JSON.stringify(migrated);
    if (serialized !== raw) window.localStorage.setItem(key, serialized);
    return migrated;
  } catch {
    return [];
  }
}

export function getSavedMemory(id: string): SavedMemory | null {
  return getSavedMemories().find((memory) => memory.id === id) ?? null;
}

export async function saveMemory(memory: SavedMemory, audio: Blob) {
  const key = storageKey();
  // Refusing beats writing an unattributed recording that the next account
  // would inherit.
  if (!key) throw new Error("no signed-in account to save this recording to");
  await saveAudio(memory.id, audio);
  const memories = getSavedMemories().filter((item) => item.id !== memory.id);
  window.localStorage.setItem(key, JSON.stringify([memory, ...memories].slice(0, 50)));
}

/**
 * Merge analysis into a memory that was already saved.
 *
 * The recording is written the moment it stops, before the pipeline has run,
 * so the title and summary start as placeholders. This is how the real ones
 * arrive. The audio blob and the raw transcript are never touched — a failed
 * or partial analysis must not be able to destroy what the user actually said.
 */
export function updateMemory(
  id: string,
  patch: Partial<Omit<SavedMemory, "id" | "createdAt" | "transcript">>,
): SavedMemory | null {
  return mergeMemory(id, patch);
}

/** Complete the one transition where authoritative Core ASR may write transcript. */
export function completeMemoryFromCore(
  id: string,
  completion: Partial<Omit<SavedMemory, "id" | "createdAt">> & {
    transcript: string;
  },
): SavedMemory | null {
  return mergeMemory(id, completion);
}

function mergeMemory(
  id: string,
  patch: Partial<Omit<SavedMemory, "id" | "createdAt">>,
): SavedMemory | null {
  const memories = getSavedMemories();
  const index = memories.findIndex((memory) => memory.id === id);
  if (index === -1) return null;
  const merged: SavedMemory = { ...memories[index], ...patch };
  memories[index] = merged;
  try {
    const key = storageKey();
    if (key) window.localStorage.setItem(key, JSON.stringify(memories));
  } catch {
    // Quota or private mode: the in-memory copy is still returned so the
    // current screen shows the analysis even if it cannot be persisted.
  }
  return merged;
}

export function savedMemoryToStory(
  memory: SavedMemory,
  uiLanguage: UiLanguage = memory.ui_language_at_creation,
): Story {
  const date = new Date(memory.createdAt);
  const dateLocale = uiLanguage === "kk" ? "kk-KZ" : "ru-RU";
  return {
    id: memory.id,
    title: memory.title,
    era: date.toLocaleDateString(dateLocale),
    recordedLabel: date.toLocaleTimeString(dateLocale, {
      hour: "2-digit",
      minute: "2-digit",
    }),
    durationSec: memory.durationSec,
    excerpt: memory.summary || memory.transcript,
    paragraphs: memory.transcript ? [memory.transcript] : [],
    mentions: [],
    isNew: true,
  };
}

/**
 * Delete this browser's local recordings for one account.
 *
 * The policy, stated exactly: signing out removes the local recordings of the
 * account that is leaving, and they do not come back on a later login. Local
 * copies are drafts and conveniences; the archive that matters lives in Core,
 * and nothing here touches it.
 *
 * Two things are removed. The departing account's own namespace -- list entries
 * and audio blobs alike -- and the legacy unscoped key from before recordings
 * were attributed to anyone, whose ownership is unknowable and which therefore
 * cannot be safely kept.
 *
 * Deliberately *not* removed: any other account's namespace. Someone else
 * signing in on this browser is not a reason to destroy a third party's data,
 * and scoped reads already make it unreachable. Only its owner's own logout
 * clears it.
 */
export async function purgeLocalRecordingsFor(userId: string | null): Promise<void> {
  if (typeof window === "undefined") return;

  const own = userId ? `${STORAGE_PREFIX}::${userId}` : null;
  try {
    // Legacy data is always dropped: it predates ownership, so it can never be
    // attributed to anyone and must not be inherited by the next account.
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
    if (own) window.localStorage.removeItem(own);
  } catch {
    // No storage access. Nothing was readable, so nothing leaked either.
  }

  await purgeLocalAudioFor(userId);
}

/** Remove the audio blobs belonging to one account, plus legacy unowned ones. */
async function purgeLocalAudioFor(userId: string | null): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  const prefix = userId ? `${userId}::` : null;
  try {
    const database = await openAudioDatabase();
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      const store = transaction.objectStore(STORE_NAME);
      const request = store.getAllKeys();
      request.onsuccess = () => {
        for (const key of request.result) {
          if (typeof key !== "string") {
            store.delete(key);
            continue;
          }
          // An un-prefixed key is legacy, from before audio belonged to an
          // account, and goes for the same reason as the legacy list.
          const legacy = !key.includes("::");
          const mine = prefix !== null && key.startsWith(prefix);
          if (legacy || mine) store.delete(key);
        }
      };
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
    });
    database.close();
  } catch {
    // A blocked or missing database means there is nothing readable to leak.
  }
}
