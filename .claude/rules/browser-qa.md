# Browser QA

## The rule

For meaningful **frontend behaviour or visual changes**, do not call the work
complete based on code and tests alone. Verify in a real browser.

This does **not** apply to trivial non-UI backend changes, pure refactors with no
rendered output, or documentation. Don't burn a browser session on those.

## Which tool

The two tools are not interchangeable — use each where it is strongest, and don't run
the same check twice.

**Claude-in-Chrome** — real authenticated journeys.
Uses the actual Chrome profile with existing Clerk login state. Use it for sign-in /
sign-up / sign-out, family creation and selection, the record → submit → processing
journey, forms, and anything cookie- or session-dependent.

**Glance** — systematic, repeatable inspection.
Use it for screenshots, accessibility snapshots, console messages, network requests,
visual baselines and comparisons, and scripted scenarios.

## Viewports

Check the three that matter: **390px** mobile · **768px** tablet · **1440px** desktop.

⚠️ Glance's viewport is fixed by `.mcp.json`
(`BROWSER_VIEWPORT_WIDTH` / `BROWSER_VIEWPORT_HEIGHT`, currently 1440×900) and changing
it requires editing that file and restarting the MCP server. For multi-viewport work
use Claude-in-Chrome's `resize_window`, which needs user permission.

Look for: horizontal overflow, clipped controls, unreadable text, broken navigation,
poor hierarchy, mobile-only layout stranded in a wide viewport, and dead empty space.
Remember the app is currently capped at 430px, so wide viewports will show the
"phone UI floating in a desktop page" problem until that is deliberately addressed.

## Always check console and network

Capture and report: console errors and warnings, failed requests, 401/403/404/5xx,
repeated or duplicated calls, and polling loops.

Expected and benign on a dev run: React DevTools info, Clerk telemetry notices, and
the Clerk **development keys** warning. Anything else deserves scrutiny.

Signed out, `/api/mura/*` should never be called at all.

## Starting the app

Frontend: `npm run dev` in `MURA-app` (Turbopack, ready in ~3s). Reuse a running
server rather than starting a second one, and stop any server you started when you are
done.

Core needs `DATABASE_URL`, which is **not** currently in `Mura_project/.env`, so the
backend will not start as-is. Demo surfaces (`/tree`, `/story`, `/ask`, `/home` signed
out) render fine without it.

Never start live ML providers or trigger expensive processing just to look at the UI.

## Don't get stuck

Stop and ask the user if you hit: tool calls failing 2–3 times, no response from the
extension, elements not responding, pages timing out, or unexpected tangential
complexity. Explain what you tried and what went wrong instead of retrying the same
failing action or wandering into unrelated pages.

Never trigger JavaScript `alert` / `confirm` / `prompt` or browser modal dialogs —
they block all further browser events and kill the session.

## Report honestly

If a viewport, journey or check could not be run — permission denied, service not
running, credentials missing — say so explicitly and label it unverified. Do not
present a static reading of the code as though it were a runtime observation.
