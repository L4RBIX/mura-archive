"use client";

/**
 * Where search lives, so every screen gets it without wiring it nine times.
 *
 * The dialog is mounted once in the shell and opened either from the header
 * button or with Cmd/Ctrl+K. Focus is captured on open and restored to whatever
 * opened it on close, because a dialog that drops focus back onto `<body>`
 * leaves a keyboard user at the top of the page with no idea where they are.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ArchiveSearch } from "@/components/search/archive-search";

interface SearchContextValue {
  open: () => void;
}

const SearchContext = createContext<SearchContextValue | null>(null);

/** Null outside the provider, so pre-product screens simply have no search. */
export function useArchiveSearch(): SearchContextValue | null {
  return useContext(SearchContext);
}

export function SearchProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLElement | null>(null);

  const show = useCallback(() => {
    opener.current = document.activeElement as HTMLElement | null;
    setOpen(true);
  }, []);

  const hide = useCallback(() => {
    setOpen(false);
    // Back to the control that opened it, not to the top of the document.
    opener.current?.focus?.();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((current) => {
          if (!current) opener.current = document.activeElement as HTMLElement | null;
          return true;
        });
      } else if (event.key === "Escape") {
        setOpen((current) => {
          if (current) opener.current?.focus?.();
          return false;
        });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <SearchContext.Provider value={{ open: show }}>
      {children}
      {open && <ArchiveSearch onClose={hide} />}
    </SearchContext.Provider>
  );
}
