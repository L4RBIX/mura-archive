# Frontend rules — `MURA-app`

Next.js 15 (App Router, Turbopack) · React 19 · TypeScript · Tailwind 4 · Framer
Motion · Clerk · Vitest.

## Routes

`/` · `/home` · `/record` · `/processing` · `/settings` · `/sign-in` · `/sign-up` ·
`/tree` · `/person/[id]` · `/story/[id]` · `/ask` · `/api/mura/[...path]`.

There is no `/family` and no `/review` route. Only `/record` and `/processing` use
`FamilyGate`.

## Real vs demo — know before you touch

| Surface | Status | Source |
| --- | --- | --- |
| `/record`, `/processing`, `/settings`, auth | **REAL** | Core via proxy |
| `/home` | **HYBRID** | local SavedMemory + demo narrator/tree card |
| `/person/[id]` | **HYBRID** | demo fixtures + local SavedMemory |
| `/tree`, `/story/[id]` | **DEMO** | `src/data/*` fixtures |
| `/ask` | **DEMO** | scripted `mustafaDemoMemory`, timer-driven |
| review / conflicts | **MISSING** | backend API exists, not proxied, no UI |

`src/data/*` during development is fine. **Production authenticated paths must never
present demo family facts as the user's own.** `/home` does this correctly
(«Ниже — демонстрационный архив…»); `/tree` and `/ask` currently do not.

`src/lib/i18n.tsx` doubles as the demo-data provider. Separate localisation from
fixtures before making Tree/Person real.

## State ownership — don't add a second source of truth

| Owner | Responsibility |
| --- | --- |
| `MuraSessionProvider` | Clerk session ↔ Core principal ↔ family session |
| `family-session.ts` | authorized family list, selection, capability checks |
| `memory-store.ts` | local SavedMemory + IndexedDB audio, **owner-scoped** |
| `recording-workflow.ts`, `use-recorder.ts` | capture → submit → poll |
| `pipeline-state.ts`, `pipeline-result.ts` | job status projection |
| `use-mascot.ts`, `mascot/machine.ts` | mascot state |

`MuraSessionProvider` watches the Clerk session key so sign-in, sign-out and account
switch re-bootstrap **without a page reload**. This fixed a real bug where the app
stayed "signed out" behind a live Clerk session until a hard refresh. Do not
reintroduce mount-once identity resolution.

## Capture vs processing are different questions

`recording-availability.ts` keeps them separate, deliberately:

- **Capture** depends on the *user*: signed in, a family they may write to,
  `create_recording` capability, browser support, mic permission.
- **Processing** depends on the *deployment*: `ready` / `degraded_queueable` /
  `unconfigured` / `unavailable` / `unknown`.

Core queues durably, so a degraded recogniser still permits capture and submission.
Submission is refused **only** when nothing could ever process the result
(`unconfigured` / `unavailable`). `unknown` counts as degraded — silence is never
taken for health. Never merge these back into one flag: that is what silently disabled
the microphone before.

## Responsive

The app is currently a **fixed 430px mobile UI centred in any viewport**. The cap is
one line: `<main className="mx-auto w-full max-w-[430px]">` in `src/app/layout.tsx`.
Measured breakpoint usage app-wide: `sm:` 0, `md:` 1, `lg:` 1, `xl:` 0 — all in
`ui/button.tsx`.

Target: intentional mobile (near-native, ~44px touch targets, safe-area handling, no
horizontal overflow), a real tablet layout, and a desktop layout that uses space
(sidebar, split panels, wider reading column, large tree canvas). Same brand,
different spatial strategy — not a different app. Never ship a phone UI floating in a
1440px page.

## Visual system

Premium, warm, human, quiet, timeless, editorial. Not generic SaaS, dashboard, CRM,
crypto or "AI app". No purple/blue AI gradients, neon, glowing robots, floating-card
soup or "AI magic" copy. `/story` is the closest existing example of the target feel.

Keep one design language: shared typography scale, spacing rhythm, container widths,
button hierarchy, radius system, surface hierarchy, motion, and consistent empty/error
states. Don't let a page invent its own.

## Mascot & silence

The Lastochka swallow stays where it adds warmth, and must not dominate serious family
content. **MURA is silent.** The Alina/Ariana voice system was removed on purpose
(commit `3bc39da`). Never reintroduce TTS, a voice picker, auto voice-over or autoplay
speech. Microphone *recording* is a separate capability and stays.

## Accessibility

Semantic HTML first; don't scatter meaningless ARIA. `MotionConfig
reducedMotion="user"` is set globally — keep it. Maintain visible focus, reasonable
contrast and large touch targets. Note: `<html lang="ru">` is hard-coded even in
Kazakh — fix when touching the shell.

## Performance

Optimize measured problems only. Watch for repeated API requests, unnecessary token
minting, request waterfalls, client components that need not be client, hydration
instability, duplicate state sources and inefficient polling. Do not micro-optimize
without evidence.

## Verification

`npx vitest run` — 188 tests, ~2s. For meaningful UI behaviour or visual changes,
tests are not sufficient: verify in a browser (see `browser-qa.md`).
