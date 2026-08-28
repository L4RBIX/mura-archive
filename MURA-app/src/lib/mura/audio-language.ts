"use client";

import { useCallback, useEffect, useState } from "react";
import {
  DEFAULT_AUDIO_LANGUAGE,
  isAudioLanguage,
  type AudioLanguage,
} from "@/lib/language";

/**
 * What MURA should expect to hear — kept deliberately apart from the interface.
 *
 * ## The architecture this enforces
 *
 * Four languages, four separate questions, and this file owns exactly one:
 *
 *   UiLanguage         which language the interface is written in
 *   AudioLanguage      what the recogniser should expect to hear  ← here
 *   TranscriptLanguage what was actually detected in the audio
 *   OutputLanguage     which language a summary is presented in
 *
 * The interface language lives in `i18n.tsx` under the `mura-locale` key. This
 * lives under its own key and is read by the recorder, never by the interface.
 * Nothing reads one and writes the other, and no code path converts between
 * them — a Russian interface recording a Kazakh grandmother is the normal case
 * for this product, not an inconsistency to reconcile.
 *
 * ## What this fixes
 *
 * The value existed and was correct, but `record-view` held it as
 * `useState(DEFAULT_AUDIO_LANGUAGE)` with no setter and no control anywhere in
 * the product. The types said the user could choose; the interface never let
 * them. For a Kazakh-speaking family that meant the preference they needed was
 * unreachable by design.
 *
 * ## Why this is only a hint
 *
 * GigaAM has one shared character vocabulary and no documented per-call
 * language selection, so this steers the browser's live preview and travels
 * with the recording as a stated preference. It is not a promise that the
 * transcript comes back in the chosen language, and nothing in the interface
 * says it is.
 */

const STORAGE_KEY = "mura-audio-language";

/** Fired on change so a screen already open picks the new value up. */
const CHANGED_EVENT = "mura:audio-language-changed";

export function readAudioLanguagePreference(): AudioLanguage {
  if (typeof window === "undefined") return DEFAULT_AUDIO_LANGUAGE;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return isAudioLanguage(stored) ? stored : DEFAULT_AUDIO_LANGUAGE;
}

export function useAudioLanguage(): {
  audioLanguage: AudioLanguage;
  setAudioLanguage: (next: AudioLanguage) => void;
} {
  // Starts at the default rather than reading storage during render, so the
  // server-rendered markup and the first client render always agree.
  const [audioLanguage, setState] = useState<AudioLanguage>(DEFAULT_AUDIO_LANGUAGE);

  useEffect(() => {
    setState(readAudioLanguagePreference());
    const sync = () => setState(readAudioLanguagePreference());
    window.addEventListener(CHANGED_EVENT, sync);
    // Another tab changed it. `storage` does not fire in the tab that wrote.
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(CHANGED_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  const setAudioLanguage = useCallback((next: AudioLanguage) => {
    window.localStorage.setItem(STORAGE_KEY, next);
    setState(next);
    window.dispatchEvent(new Event(CHANGED_EVENT));
  }, []);

  return { audioLanguage, setAudioLanguage };
}

/** The choices offered, in the order they are shown. */
export const AUDIO_LANGUAGE_OPTIONS: ReadonlyArray<{
  value: AudioLanguage;
  labelKey: "audioLangAuto" | "audioLangRu" | "audioLangKk" | "audioLangMixed";
}> = [
  { value: "auto", labelKey: "audioLangAuto" },
  { value: "ru", labelKey: "audioLangRu" },
  { value: "kk", labelKey: "audioLangKk" },
  { value: "mixed", labelKey: "audioLangMixed" },
];
