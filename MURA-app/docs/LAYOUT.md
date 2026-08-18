# Layout

The visual language — palette, type scale, radii — lives in `src/app/globals.css`
and is not the subject of this document. This is the level below it: how wide a
page is, where its gutter comes from, and what changes at each breakpoint.

It exists because that level did not. Widths were decided per component, so the
product had three different answers to "how wide is a page" and nothing to stop
a fourth.

## Content widths

Declared once, in `@theme`, and chosen by name through `PageContainer`.

| Name | Value | For |
| --- | --- | --- |
| `reading` | `70ch` | long-form prose — story, local story |
| `form` | `560px` | a single column of controls — settings, auth, search dialog |
| `default` | `720px` | lists and cards — stories, review |
| `focus` | `520px` | one task, nothing beside it — the record column |
| `wide` | `1100px`, `1280px` from `2xl` | multi-column surfaces — home, person, settings |
| `full` | none | canvases that own the viewport — tree |
| `measure` | `46ch` | short helper text *inside* an already-bounded parent |

```tsx
<PageContainer width="wide">…</PageContainer>
```

`reading` and `measure` are in `ch` on purpose: the constraint is characters per
line, not pixels, so they survive a change to the type scale. Note that `ch`
resolves against the *container's* font (16px) while story prose is 18px —
`70ch` buys about 63 Cyrillic characters, which is why it is not `62ch`.

**Prose never widens past `reading`, at any breakpoint.** What grows on a large
window is the number of columns and the density, not the line length.

## Gutter

`px-page` — one utility, applied by `PageContainer`. 20px, 24px from `sm`, 32px
from `lg`, 40px from `2xl`. Do not write `px-5 sm:px-6 lg:px-8` by hand; that
convention was held together by copy-paste and a screen that missed a step just
had a different margin.

## Breakpoints

| | From | What changes |
| --- | --- | --- |
| `sm` | 640px | small typographic and alignment adjustments |
| `lg` | 1024px | the rail appears, the bottom tab bar goes, `AppHeader` switches to its desktop form, two-column page grids begin |
| `xl` | 1280px | second column inside a column — memory cards on home, standing facts beside memories on person |
| `2xl` | 1536px | wider `wide` container, roomier asides |

`md` is deliberately almost unused: between the phone layout and the rail there
is no third arrangement worth maintaining.

## Header

`AppHeader` — one component, two densities. Below `lg` it is a mobile title bar:
back button, centred title, actions. From `lg` the back button goes (the rail is
still on screen, so there is nothing to go back *from*) and the title becomes a
real page title aligned to the content column.

- `width` **must match the page's own container**, or the title will not line up.
- `ownTitle` for screens that already render their own title (a story, a person),
  so no screen shows two.
- `standalone` for screens deliberately without the rail (record, processing) —
  the back button is their only way out and stays at every width.

## Focus

`focus-ring`, one utility. Offset is a variable: `[--focus-ring-offset:8px]` on
elements that need the ring further out. Never write the four-class
`focus-visible:outline-…` string by hand — a test fails if you do.

## State colours

`danger`, `warning`, `success`, each with contrast measured on both `paper` and
`raised` (see `src/lib/contrast.test.ts`). Raw Tailwind status colours
(`text-red-700` and friends) are forbidden and enforced by test.

## Forbidden

- `max-w-[…]` outside `page-container.tsx`. The exception list lives in
  `src/lib/layout-system.test.ts` and every entry carries a written reason; add
  to it only with an argument, and only for a control or a measure — never for a
  page width.
- A hand-written focus ring.
- A raw Tailwind status colour.
- Prose that stretches with the window.
- Adding a string to `ru` without adding it to `kk`.

All five are enforced by `src/lib/layout-system.test.ts`,
`src/lib/i18n-parity.test.ts` and `src/lib/contrast.test.ts`.

## What is not covered

There is no visual-regression baseline. Adding one needs a browser driver
(Playwright) as a dev dependency, which the repository's resource policy says to
ask about first. See `docs/UI_AUDIT_RESULT.md`.
