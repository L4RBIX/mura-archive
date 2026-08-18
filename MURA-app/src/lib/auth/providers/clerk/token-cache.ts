/**
 * A short-lived, server-only cache for Core tokens, plus single-flight minting.
 *
 * Why it exists: minting a `mura-core` template token calls Clerk's Backend API,
 * measured at ~550ms against the live development instance. Job polling runs
 * every 1.5s while a memory processes, so without a cache that cost is
 * continuous rather than occasional.
 *
 * Two problems this module fixes, both measured rather than assumed:
 *
 * 1. Clerk template tokens live 60 seconds. The previous 30-second safety
 *    margin threw away half of that, so a fresh ~550ms mint happened every 30s.
 *    The margin is now sized to the network hop it protects, not to half the
 *    token's life.
 *
 * 2. Bootstrap fires `/v1/me`, `/v1/families` and `/v1/capabilities` at once.
 *    All three missed the cache together and each minted its own token: three
 *    concurrent Backend API calls for one page load. Minting is now
 *    single-flight per session, so concurrent callers await one request.
 *
 * Safety is unchanged: entries are keyed by Clerk session id and only ever read
 * after `auth()` has confirmed that session is active, so a signed-out or
 * revoked session never reaches this map. Nothing is persisted; this is process
 * memory that dies with the instance and is never sent to the browser.
 */

interface Entry {
  token: string;
  /** Epoch milliseconds at which this token must no longer be handed out. */
  usableUntil: number;
}

/**
 * Discard a token this long before it actually expires.
 *
 * It covers the proxy -> Core hop plus clock skew, not half the token's life.
 * Core additionally allows 30s of skew, so a token accepted here is comfortably
 * valid on arrival.
 */
export const EXPIRY_MARGIN_MS = 10_000;

/**
 * Bounded so a long-lived instance serving many sessions cannot grow without
 * limit. Eviction is oldest-first and the cost of a miss is one Clerk call.
 */
const MAX_ENTRIES = 500;

const cache = new Map<string, Entry>();
const inFlight = new Map<string, Promise<string | null>>();

/** Read `exp` without verifying: Core does the verifying, this only schedules. */
export function readExpiryMs(token: string): number | null {
  const segments = token.split(".");
  if (segments.length !== 3) return null;
  try {
    const payload: unknown = JSON.parse(
      Buffer.from(segments[1], "base64url").toString("utf8"),
    );
    if (typeof payload !== "object" || payload === null) return null;
    const exp = (payload as { exp?: unknown }).exp;
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
}

export function getCachedToken(sessionId: string, now = Date.now()): string | null {
  const entry = cache.get(sessionId);
  if (!entry) return null;
  if (entry.usableUntil <= now) {
    cache.delete(sessionId);
    return null;
  }
  return entry.token;
}

export function cacheToken(sessionId: string, token: string, now = Date.now()): void {
  const expiry = readExpiryMs(token);
  // A token whose expiry cannot be read is used once and not stored: guessing a
  // lifetime for it could keep a dead token in play.
  if (expiry === null) return;
  const usableUntil = expiry - EXPIRY_MARGIN_MS;
  if (usableUntil <= now) return;

  if (cache.size >= MAX_ENTRIES && !cache.has(sessionId)) {
    const oldest = cache.keys().next();
    if (!oldest.done) cache.delete(oldest.value);
  }
  cache.set(sessionId, { token, usableUntil });
}

/**
 * Mint at most once per session at a time.
 *
 * Concurrent callers for the same session await the same promise; different
 * sessions are never serialised against each other. The in-flight entry is
 * always cleared, so one failure cannot wedge a session permanently.
 */
export async function mintOnce(
  key: string,
  mint: () => Promise<string | null>,
): Promise<string | null> {
  const pending = inFlight.get(key);
  if (pending) return pending;

  const promise = (async () => {
    try {
      return await mint();
    } finally {
      inFlight.delete(key);
    }
  })();
  inFlight.set(key, promise);
  return promise;
}

/** Drop a session's token, e.g. on sign-out or when Core stops accepting it. */
export function forgetToken(sessionId: string): void {
  cache.delete(sessionId);
}

/** Test seam only. */
export function clearTokenCache(): void {
  cache.clear();
  inFlight.clear();
}

/** Test/diagnostic seam: how many sessions currently hold a cached token. */
export function cachedSessionCount(): number {
  return cache.size;
}
