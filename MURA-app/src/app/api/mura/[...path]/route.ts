/**
 * Next.js adapter for the Core proxy.
 *
 * Kept deliberately thin: the allowlist, the session boundary and the forwarding
 * rules live in `proxy.ts` so they can be tested as plain functions rather than
 * through a framework route handler.
 */

import { handleCoreProxy } from "./proxy";

export const runtime = "nodejs";
/** A family's memories must never be served from a shared cache. */
export const dynamic = "force-dynamic";

// Nothing else may be exported here: Next.js route modules allow only route
// handlers and a fixed set of config exports, and re-exporting a helper makes
// the generated route types fail. Tests import it from `./proxy` directly.

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, context: Context): Promise<Response> {
  return handleCoreProxy(request, (await context.params).path);
}

export async function POST(request: Request, context: Context): Promise<Response> {
  return handleCoreProxy(request, (await context.params).path);
}

export async function PATCH(request: Request, context: Context): Promise<Response> {
  return handleCoreProxy(request, (await context.params).path);
}

export async function DELETE(request: Request, context: Context): Promise<Response> {
  return handleCoreProxy(request, (await context.params).path);
}
