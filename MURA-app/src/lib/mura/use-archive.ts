"use client";

/**
 * Reading the family archive, with isolation as the first requirement.
 *
 * A family archive is the most private thing this product holds, so the
 * interesting part of this hook is not the fetching — it is everything that
 * makes one family's data unable to appear under another's name:
 *
 * *State resets on the same render the family changes.* Not in an effect
 * afterwards. If it waited for an effect, family B's screen would paint once
 * with family A's people still in state, and a stale flash of the wrong
 * family's relatives is exactly the failure this milestone exists to prevent.
 *
 * *Late responses are dropped, not merged.* Every load carries the family it
 * was issued for and a generation number. A slow request for A that lands
 * after the switch to B is discarded, because aborting is best-effort and a
 * response already in flight can still resolve.
 *
 * *Signing out is a family change to nothing.* No family, no data, no request.
 *
 * Deliberately not React Query or SWR. The product needs per-family
 * invalidation and hard isolation, which is a handful of lines here, and a
 * cache library would add a dependency plus a second place where family
 * identity has to be respected.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { CoreRequestError } from "@/lib/mura/core-api";
import { useMuraSession } from "@/lib/mura/session-provider";

export type ArchiveStatus = "idle" | "loading" | "ready" | "error" | "forbidden";

export interface ArchiveResource<T> {
  status: ArchiveStatus;
  data: T | null;
  /** The family this data belongs to. Never render `data` without it. */
  familyId: string | null;
  error: CoreRequestError | null;
  reload: () => void;
}

/**
 * Load one archive resource for the currently selected family.
 *
 * `load` must be stable (module-level function or `useCallback`), since it
 * takes part in the effect's dependencies.
 */
export function useArchiveResource<T>(
  load: (familyId: string, signal: AbortSignal) => Promise<T>,
  options: { enabled?: boolean } = {},
): ArchiveResource<T> {
  const { family, auth } = useMuraSession();
  const enabled = options.enabled ?? true;
  const familyId = family.selectedFamilyId ?? null;
  const signedIn = auth.status === "authenticated";
  const activeFamily = signedIn && enabled ? familyId : null;

  const [state, setState] = useState<{
    status: ArchiveStatus;
    data: T | null;
    familyId: string | null;
    error: CoreRequestError | null;
  }>({ status: "idle", data: null, familyId: null, error: null });

  // Render-phase reset. React re-runs the component immediately with cleared
  // state, so nothing from the previous family survives into this paint.
  const [renderedFor, setRenderedFor] = useState<string | null>(activeFamily);
  if (renderedFor !== activeFamily) {
    setRenderedFor(activeFamily);
    setState({ status: activeFamily ? "loading" : "idle", data: null, familyId: null, error: null });
  }

  const generation = useRef(0);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!activeFamily) return;
    const mine = ++generation.current;
    const controller = new AbortController();
    let cancelled = false;

    setState((current) =>
      current.status === "loading" && current.data === null
        ? current
        : { status: "loading", data: null, familyId: null, error: null },
    );

    void (async () => {
      try {
        const data = await load(activeFamily, controller.signal);
        // Two guards, both needed: the generation catches a response that
        // resolved after a newer load started, and the family check makes the
        // data unusable under any other archive even if it somehow arrives.
        if (cancelled || mine !== generation.current) return;
        setState({ status: "ready", data, familyId: activeFamily, error: null });
      } catch (error) {
        if (cancelled || mine !== generation.current) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        const failure = error instanceof CoreRequestError ? error : null;
        setState({
          // 403 is a real answer, not an outage: a viewer may simply not be
          // allowed this surface, and telling them the service is broken
          // would be false.
          status: failure?.status === 403 ? "forbidden" : "error",
          data: null,
          familyId: null,
          error: failure,
        });
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeFamily, load, attempt]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);

  return { ...state, reload };
}
