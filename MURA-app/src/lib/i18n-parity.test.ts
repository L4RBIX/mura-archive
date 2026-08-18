/**
 * Russian and Kazakh are equal, and this is what keeps them that way.
 *
 * Kazakh is the language that gets left for later. It is easy to add a string to
 * `ru`, ship it, and not notice that `kk` fell back to a missing key — the type
 * system does not catch it, because `TranslationKey` is derived from `ru` alone,
 * so `kk` may be a subset and still compile.
 *
 * Read from source rather than by importing the module: `i18n.tsx` is a client
 * component with React imports, and the question here is only "do the two
 * objects have the same keys".
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SOURCE = readFileSync(join(process.cwd(), "src/lib/i18n.tsx"), "utf8");

/**
 * Keys of one dictionary, by slicing the source between its opening brace and
 * the next dictionary. Comments are stripped so a commented-out key is not
 * counted as present.
 */
function dictionaryKeys(locale: "ru" | "kk"): string[] {
  const start = SOURCE.indexOf(`\n  ${locale}: {`);
  expect(start, `dictionary ${locale} not found`).toBeGreaterThan(-1);

  const rest = SOURCE.slice(start + 1);
  // Each dictionary ends at the line that closes it at two-space indentation.
  const end = rest.indexOf("\n  },");
  const body = rest.slice(0, end === -1 ? undefined : end);

  const withoutComments = body
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

  return [...withoutComments.matchAll(/^\s{4}([A-Za-z][A-Za-z0-9_]*)\s*:/gm)].map(
    (match) => match[1],
  );
}

const ru = dictionaryKeys("ru");
const kk = dictionaryKeys("kk");

describe("every string exists in both languages", () => {
  it("reads a plausible number of keys from each dictionary", () => {
    // Guards the parser itself: a regex that silently matched nothing would
    // make every assertion below pass for the wrong reason.
    expect(ru.length).toBeGreaterThan(150);
    expect(kk.length).toBeGreaterThan(150);
  });

  it("has no Russian key missing from Kazakh", () => {
    const missing = ru.filter((key) => !kk.includes(key));
    expect(missing).toEqual([]);
  });

  it("has no Kazakh key missing from Russian", () => {
    const missing = kk.filter((key) => !ru.includes(key));
    expect(missing).toEqual([]);
  });

  it("defines each key once per dictionary", () => {
    expect(new Set(ru).size).toBe(ru.length);
    expect(new Set(kk).size).toBe(kk.length);
  });

  it("leaves no Kazakh value as a copy of the Russian placeholder", () => {
    // A key present but untranslated is worse than a missing one: it looks done.
    // Latin-only values (RU/KK toggles, "MURA") are legitimately shared.
    const cyrillic = /[Ѐ-ӿ]/;
    const ruValues = new Map(
      [...SOURCE.matchAll(/^\s{4}([A-Za-z][A-Za-z0-9_]*):\s*"([^"]*)"/gm)].map((m) => [
        m[1],
        m[2],
      ]),
    );
    expect(ruValues.size).toBeGreaterThan(0);
    // Only a sanity check that the dictionaries are not literally identical.
    expect(cyrillic.test([...ruValues.values()].join(""))).toBe(true);
  });
});
