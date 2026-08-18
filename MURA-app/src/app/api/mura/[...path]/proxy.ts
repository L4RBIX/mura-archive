/**
 * Server-side proxy to Mura Core.
 *
 * This is an allowlist, not a tunnel. Only the canonical application endpoints
 * the browser genuinely uses are reachable, each pinned to the methods it
 * supports. Operator surfaces (`/v1/operations/*`), transport surfaces
 * (`/v1/workers/*`), diagnostics (`/v1/jobs/{id}/trace`), deterministic replay
 * and `/v1/process-transcript` are deliberately absent: no product flow needs
 * them, Core classifies them as service-internal, and exposing them would hand
 * the browser release control and retention deletion.
 *
 * Since PR-03C the proxy also owns the session boundary. Every request carries
 * the *user's* bearer token, resolved server-side, and there is no fallback to
 * the Core service credential -- that fallback is precisely the authorization
 * hole the backend closed, and the frontend must not reintroduce it.
 */

import { readServerAuthSession } from "@/lib/auth/server-session";
import { AUTH_PROVIDER_UNCONFIGURED, AUTHENTICATION_REQUIRED } from "@/lib/auth/session";

const FAMILY = "[a-zA-Z0-9_-]{1,128}";
const USER = "user_[a-f0-9]{32}";
const RECORDING = "rec_[a-f0-9]{32}";
const JOB = "job_[a-f0-9]{32}";
const PERSON = "person_[a-f0-9]{32}";
/** Story and conflict ids are extraction-minted, so their shape is looser. */
const STORY = "[A-Za-z0-9_-]{1,128}";
const CONFLICT = "[A-Za-z0-9_-]{1,128}";

type Method = "GET" | "POST" | "PATCH" | "DELETE";

const ALLOWED: ReadonlyArray<{ method: Method; pattern: RegExp }> = [
  { method: "GET", pattern: new RegExp(`^v1/capabilities$`) },
  { method: "GET", pattern: new RegExp(`^v1/me$`) },
  { method: "GET", pattern: new RegExp(`^v1/families$`) },
  { method: "POST", pattern: new RegExp(`^v1/families$`) },
  { method: "GET", pattern: new RegExp(`^v1/families/${FAMILY}$`) },
  { method: "GET", pattern: new RegExp(`^v1/families/${FAMILY}/members$`) },
  { method: "PATCH", pattern: new RegExp(`^v1/families/${FAMILY}/members/${USER}$`) },
  { method: "DELETE", pattern: new RegExp(`^v1/families/${FAMILY}/members/${USER}$`) },
  { method: "POST", pattern: new RegExp(`^v1/families/${FAMILY}/recordings$`) },
  {
    method: "GET",
    pattern: new RegExp(`^v1/families/${FAMILY}/recordings/${RECORDING}$`),
  },
  {
    method: "GET",
    pattern: new RegExp(`^v1/families/${FAMILY}/recordings/${RECORDING}/review-items$`),
  },
  { method: "GET", pattern: new RegExp(`^v1/families/${FAMILY}/jobs/${JOB}$`) },

  // PR-06 archive surfaces. These are what let Tree, Person, Story and Review
  // stop rendering fixtures; each one is a family-scoped read on Core.
  { method: "GET", pattern: new RegExp(`^v1/families/${FAMILY}/archive$`) },
  { method: "GET", pattern: new RegExp(`^v1/families/${FAMILY}/people$`) },
  { method: "GET", pattern: new RegExp(`^v1/families/${FAMILY}/relationships$`) },
  { method: "GET", pattern: new RegExp(`^v1/families/${FAMILY}/profiles/${PERSON}$`) },
  { method: "GET", pattern: new RegExp(`^v1/families/${FAMILY}/stories$`) },
  { method: "GET", pattern: new RegExp(`^v1/families/${FAMILY}/stories/${STORY}$`) },
  { method: "GET", pattern: new RegExp(`^v1/families/${FAMILY}/review-items$`) },
  {
    method: "GET",
    pattern: new RegExp(`^v1/families/${FAMILY}/recordings/${RECORDING}/audio$`),
  },
  { method: "GET", pattern: new RegExp(`^v1/families/${FAMILY}/conflicts$`) },
  { method: "GET", pattern: new RegExp(`^v1/families/${FAMILY}/conflicts/${CONFLICT}$`) },
  {
    method: "POST",
    pattern: new RegExp(`^v1/families/${FAMILY}/conflicts/${CONFLICT}/resolve$`),
  },
  {
    method: "POST",
    pattern: new RegExp(`^v1/families/${FAMILY}/conflicts/${CONFLICT}/dismiss$`),
  },
  {
    method: "POST",
    pattern: new RegExp(`^v1/families/${FAMILY}/conflicts/${CONFLICT}/reopen$`),
  },
];

export function isAllowedCoreRoute(method: string, route: string): boolean {
  // A decoded segment containing a slash or traversal would let a crafted path
  // escape the patterns above, so reject those before matching.
  if (route.includes("..") || route.includes("//") || route.startsWith("/")) return false;
  return ALLOWED.some((entry) => entry.method === method && entry.pattern.test(route));
}

/** Capabilities gate the record button, so it gets a shorter budget. */
const TIMEOUT_MS: Record<string, number> = { "v1/capabilities": 5_000 };
const DEFAULT_TIMEOUT_MS = 30_000;

/**
 * Core's base URL, and nothing else.
 *
 * MURA_CORE_API_KEY is deliberately not read here or anywhere in this app. The
 * frontend has no service-internal consumer, so it has no business holding a
 * credential that authorizes one.
 */
function coreBaseUrl(): string | null {
  return process.env.MURA_API_URL?.replace(/\/$/, "") || null;
}

/** Same envelope Core uses, so the client only ever parses one error shape. */
function envelope(
  code: string,
  message: string,
  retryable: boolean,
  requestId: string,
  status: number,
): Response {
  return Response.json(
    { error: { code, message, retryable, request_id: requestId } },
    {
      status,
      headers: {
        "x-request-id": requestId,
        // The success path already refuses caching; errors have to as well. A
        // cached 401 outlives the sign-in that fixes it, and the user goes on
        // being told to log in while holding a live session -- exactly the
        // stale mixed state the session rework removed elsewhere.
        "cache-control": "no-store, private",
      },
    },
  );
}

export async function handleCoreProxy(request: Request, path: string[]): Promise<Response> {
  const route = path.join("/");
  const requestId =
    request.headers.get("x-request-id") ?? `req_${crypto.randomUUID().replace(/-/g, "")}`;

  if (!isAllowedCoreRoute(request.method, route)) {
    return envelope("not_found", "Неизвестный маршрут.", false, requestId, 404);
  }

  const baseUrl = coreBaseUrl();
  if (!baseUrl) {
    return envelope("service_unavailable", "Сервис временно недоступен.", true, requestId, 503);
  }

  // Resolved from the server session only. Any Authorization header the caller
  // supplied is discarded: presenting your own bearer must not make the proxy
  // forward it.
  const session = await readServerAuthSession(request);
  if (session.status === "provider_unconfigured") {
    return envelope(
      AUTH_PROVIDER_UNCONFIGURED,
      "Вход пока не настроен.",
      false,
      requestId,
      401,
    );
  }
  if (session.status !== "authenticated") {
    return envelope(AUTHENTICATION_REQUIRED, "Требуется вход.", false, requestId, 401);
  }

  const headers = new Headers({
    Authorization: `Bearer ${session.accessToken}`,
    "x-request-id": requestId,
  });

  let body: BodyInit | undefined;
  if (request.method === "POST" || request.method === "PATCH") {
    const contentType = request.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      body = await request.text();
      headers.set("content-type", "application/json");
    } else {
      body = await request.formData();
    }
  }

  try {
    const response = await fetch(`${baseUrl}/${route}`, {
      method: request.method,
      headers,
      body,
      // Never cached: a shared cache entry would be a family's memories served
      // to whoever asked next.
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS[route] ?? DEFAULT_TIMEOUT_MS),
    });
    // The body is streamed rather than read as text. Family audio is bytes,
    // and `response.text()` would decode it as UTF-8 and hand the browser a
    // corrupted recording. Streaming also means a long recording is not
    // buffered in the proxy on its way through.
    return new Response(response.body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json",
        "x-request-id": response.headers.get("x-request-id") ?? requestId,
        // Never cached: a shared cache entry would be one family's memories
        // served to whoever asked next.
        "cache-control": "no-store, private",
      },
    });
  } catch (error) {
    // The upstream body is never forwarded here: a Cloudflare HTML page or a
    // Python traceback must not reach the browser. Neither is the error itself,
    // which for a request that carried a bearer can echo the request headers.
    const timedOut = error instanceof Error && error.name === "TimeoutError";
    return envelope(
      timedOut ? "upstream_timeout" : "service_unavailable",
      "Сервис временно недоступен.",
      true,
      requestId,
      timedOut ? 504 : 503,
    );
  }
}
