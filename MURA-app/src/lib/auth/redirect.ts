/**
 * Where to send the user after they sign in.
 *
 * Only same-origin, path-absolute destinations are honoured. Anything else --
 * an absolute URL, a protocol-relative `//evil.example`, a backslash variant
 * some parsers normalise to a slash -- is discarded in favour of the home
 * screen. An open redirect on a login page is how a convincing phishing hop is
 * built, and the convenience of "return where you were" is not worth it.
 */

const DEFAULT_DESTINATION = "/home";

export function safeRedirectPath(candidate: string | null | undefined): string {
  if (!candidate) return DEFAULT_DESTINATION;
  // Must be a single-slash absolute path. `//host` and `/\host` are not.
  if (!candidate.startsWith("/")) return DEFAULT_DESTINATION;
  if (candidate.startsWith("//") || candidate.startsWith("/\\")) return DEFAULT_DESTINATION;
  // A scheme cannot appear in a path-absolute URL; reject anything that has one.
  if (/^\/[a-zA-Z][a-zA-Z0-9+.-]*:/.test(candidate)) return DEFAULT_DESTINATION;
  return candidate;
}
