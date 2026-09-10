import { NextResponse } from "next/server";
import { SESSION_COOKIE, cookieOptions } from "@/lib/auth/providers/supabase/session-cookie";

/**
 * Drop the session cookie.
 *
 * POST only: a GET sign-out can be triggered by any image tag on any page.
 */
export async function POST(request: Request): Promise<Response> {
  const response = NextResponse.redirect(new URL("/", request.url), { status: 303 });
  response.cookies.set(SESSION_COOKIE, "", cookieOptions(0));
  return response;
}
