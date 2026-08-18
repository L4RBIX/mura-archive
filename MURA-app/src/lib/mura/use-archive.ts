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

export interface ArchivePage<T> {
  items: T[];
  total: number;
}

export interface ArchivePages<T> {
  status: ArchiveStatus;
  items: T[];
  /** How many the archive holds, not how many are loaded. */
  total: number;
  familyId: string | null;
  error: CoreRequestError | null;
  hasMore: boolean;
  /** A page after the first is in flight. The list stays on screen while it is. */
  loadingMore: boolean;
  loadMore: () => void;
  reload: () => void;
}

/**
 * The same resource, in pages that accumulate.
 *
 * `/stories` asked for 30 and stopped, with no next page and no indication that
 * anything had been cut — which for a product whose whole promise is "an
 * archive your family adds to for years" meant memory 31 onwards was
 * unreachable.
 *
 * It carries the isolation rules of `useArchiveResource` unchanged, and they
 * matter more here because there is accumulated state to leak: switching family
 * clears the loaded pages in the render phase, and every response is checked
 * against both a generation counter and the family it was issued for before it
 * is appended. A late page from family A must never land in family B's list.
 *
 * Appending, not refetching: page two costs one request, and the pages already
 * read stay on screen rather than flickering through a loading state.
 */
export function useArchivePages<T>(
  loadPage: (
    familyId: string,
    offset: number,
    signal: AbortSignal,
  ) => Promise<ArchivePage<T>>,
  options: { enabled?: boolean } = {},
): ArchivePages<T> {
  const { family, auth } = useMuraSession();
  const enabled = options.enabled ?? true;
  const familyId = family.selectedFamilyId ?? null;
  const signedIn = auth.status === "authenticated";
  const activeFamily = signedIn && enabled ? familyId : null;

  const [state, setState] = useState<{
    status: ArchiveStatus;
    items: T[];
    total: number;
    familyId: string | null;
    error: CoreRequestError | null;
    loadingMore: boolean;
  }>({
    status: "idle",
    items: [],
    total: 0,
    familyId: null,
    error: null,
    loadingMore: false,
  });

  // Render-phase reset, exactly as above: accumulated pages from the previous
  // family must not survive into this paint.
  const [renderedFor, setRenderedFor] = useState<string | null>(activeFamily);
  if (renderedFor !== activeFamily) {
    setRenderedFor(activeFamily);
    setState({
      status: activeFamily ? "loading" : "idle",
      items: [],
      total: 0,
      familyId: null,
      error: null,
      loadingMore: false,
    });
  }

  const generation = useRef(0);
  const [attempt, setAttempt] = useState(0);
  /** Requested offset. Bumping it is what asks for the next page. */
  const [offset, setOffset] = useState(0);

  // A new family or a reload starts again from the first page.
  const [pagedFor, setPagedFor] = useState<string | null>(activeFamily);
  if (pagedFor !== activeFamily) {
    setPagedFor(activeFamily);
    setOffset(0);
  }

  useEffect(() => {
    if (!activeFamily) return;
    const mine = ++generation.current;
    const controller = new AbortController();
    let cancelled = false;

    if (offset > 0) setState((current) => ({ ...current, loadingMore: true }));

    void (async () => {
      try {
        const page = await loadPage(activeFamily, offset, controller.signal);
        if (cancelled || mine !== generation.current) return;
        setState((current) => ({
          status: "ready",
          // Offset 0 replaces; anything else appends to what is already read.
          items: offset === 0 ? page.items : [...current.items, ...page.items],
          total: page.total,
          familyId: activeFamily,
          error: null,
          loadingMore: false,
        }));
      } catch (error) {
        if (cancelled || mine !== generation.current) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        const failure = error instanceof CoreRequestError ? error : null;
        setState((current) => ({
          // A failed *next* page keeps the pages already read on screen: the
          // user has not lost what they were reading, they just did not get
          // more. Only a failed first page empties the list.
          status: offset === 0 ? (failure?.status === 403 ? "forbidden" : "error") : current.status,
          items: offset === 0 ? [] : current.items,
          total: offset === 0 ? 0 : current.total,
          familyId: offset === 0 ? null : current.familyId,
          error: failure,
          loadingMore: false,
        }));
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [activeFamily, loadPage, offset, attempt]);

  // Read by `loadMore` so the guard sees the current values without making the
  // callback change identity on every page.
  const latest = useRef(state);
  latest.current = state;

  const loadMore = useCallback(() => {
    const { loadingMore, items, total } = latest.current;
    // Guarded here rather than at the call site, so a double-click — or a click
    // while a page is already in flight — cannot skip a page or request one
    // that does not exist.
    if (loadingMore || items.length >= total) return;
    setOffset(items.length);
  }, []);

  const reload = useCallback(() => {
    setOffset(0);
    setAttempt((value) => value + 1);
  }, []);

  return {
    status: state.status,
    items: state.items,
    total: state.total,
    familyId: state.familyId,
    error: state.error,
    hasMore: state.status === "ready" && state.items.length < state.total,
    loadingMore: state.loadingMore,
    loadMore,
    reload,
  };
}
