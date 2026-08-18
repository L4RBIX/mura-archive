"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { transition } from "@/lib/mascot/machine";
import type { MascotEventType, MascotState } from "@/lib/mascot/types";

/**
 * The swallow's pose, and nothing else.
 *
 * She used to speak: pre-recorded voice-over clips, played automatically on
 * mount through a Web Audio engine, with a choice of two performers in
 * settings. That whole feature is gone -- MURA does not talk. What remains is
 * the visual state machine, which is what the screens actually needed from her:
 * a pose that follows the work being done.
 *
 * There is deliberately no `speak`, no autoplay, and no audio to unblock, so
 * there is no path by which mounting a screen can make a sound.
 */

export interface UseMascotOptions {
  /**
   * Fired once the surface is ready to proceed.
   *
   * It exists because screens used to wait for her greeting to finish before
   * advancing. With no greeting there is nothing to wait for, so it fires
   * immediately -- a caller gated on it must never hang.
   */
  onIntroFinish?: () => void;
}

export interface MascotController {
  state: MascotState;
  isSpeaking: boolean;
  send: (event: MascotEventType) => void;
}

export function useMascot(options: UseMascotOptions = {}): MascotController {
  const { onIntroFinish } = options;
  const [state, setState] = useState<MascotState>("idle");

  // The reducer reads through a ref so `send` stays referentially stable and
  // never re-triggers the effects that depend on it.
  const stateRef = useRef<MascotState>("idle");
  const mounted = useRef(true);

  const send = useCallback((event: MascotEventType) => {
    const next = transition(stateRef.current, event);
    if (next === stateRef.current) return;
    stateRef.current = next;
    if (mounted.current) setState(next);
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Read through a ref so changing the callback does not re-fire it.
  const introFinish = useRef(onIntroFinish);
  introFinish.current = onIntroFinish;

  useEffect(() => {
    introFinish.current?.();
  }, []);

  return useMemo(
    // Nothing is ever spoken, so she is never speaking. Screens that dim
    // themselves while she talks simply never dim.
    () => ({ state, isSpeaking: false, send }),
    [state, send],
  );
}
