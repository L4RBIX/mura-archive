/**
 * Every interface language is equal, and this is what keeps them that way.
 *
 * Kazakh is the language that gets left for later, and English is now the one
 * that gets added to first. It is easy to add a string to `ru`, ship it, and not
 * notice the others fell back to a missing key — the type system does not catch
 * it, because `TranslationKey` is derived from `ru` alone, so any other
 * dictionary may be a subset and still compile.
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
function dictionaryKeys(locale: Locale): string[] {
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

type Locale = "ru" | "kk" | "en";

/** Russian is the reference: `TranslationKey` is derived from it. */
const REFERENCE: Locale = "ru";
const LOCALES: readonly Locale[] = ["ru", "kk", "en"];

/** Key to value for one dictionary, so locales can be compared to each other. */
function dictionaryValues(locale: Locale): Map<string, string> {
  const start = SOURCE.indexOf(`\n  ${locale}: {`);
  const rest = SOURCE.slice(start + 1);
  const end = rest.indexOf("\n  },");
  const body = rest
    .slice(0, end === -1 ? undefined : end)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "")
    // A value wrapped onto its own line is still one value.
    .replace(/:\s*\n\s+"/g, ': "');

  return new Map(
    [...body.matchAll(/^\s{4}([A-Za-z][A-Za-z0-9_]*):\s*"([^"]*)"/gm)].map((m) => [m[1], m[2]]),
  );
}

const byLocale = new Map<Locale, string[]>(
  LOCALES.map((locale) => [locale, dictionaryKeys(locale)]),
);
// Russian is the reference every other dictionary is compared against.
const ru = byLocale.get(REFERENCE) as string[];

describe("every string exists in every language", () => {
  it.each(LOCALES)("reads a plausible number of keys from %s", (locale) => {
    // Guards the parser itself: a regex that silently matched nothing would
    // make every assertion below pass for the wrong reason.
    expect(byLocale.get(locale)?.length ?? 0).toBeGreaterThan(150);
  });

  it.each(LOCALES.filter((locale) => locale !== REFERENCE))(
    "has no Russian key missing from %s",
    (locale) => {
      const keys = byLocale.get(locale) as string[];
      expect(ru.filter((key) => !keys.includes(key))).toEqual([]);
    },
  );

  it.each(LOCALES.filter((locale) => locale !== REFERENCE))(
    "has no %s key missing from Russian",
    (locale) => {
      const keys = byLocale.get(locale) as string[];
      expect(keys.filter((key) => !ru.includes(key))).toEqual([]);
    },
  );

  it.each(LOCALES)("defines each key once in %s", (locale) => {
    const keys = byLocale.get(locale) as string[];
    expect(new Set(keys).size).toBe(keys.length);
  });

  it.each(LOCALES.filter((locale) => locale !== REFERENCE))(
    "leaves no %s value as an untranslated copy of the Russian",
    (locale) => {
      // A key present but untranslated is worse than a missing one: it looks
      // done. Some values are legitimately shared — a name, a bare number, an
      // interval like «26 July 2026 · Astana» — so a handful of matches is
      // expected and only a wholesale copy is a failure.
      const reference = dictionaryValues(REFERENCE);
      const values = dictionaryValues(locale);

      const shared = [...values.entries()].filter(
        ([key, value]) => value.length > 3 && reference.get(key) === value,
      );

      expect(shared.length / values.size).toBeLessThan(0.05);
    },
  );

  it("writes each language in a script that language uses", () => {
    const cyrillic = /[\u0400-\u04FF]/;
    const joined = (locale: Locale) => [...dictionaryValues(locale).values()].join(" ");

    expect(cyrillic.test(joined("ru"))).toBe(true);
    expect(cyrillic.test(joined("kk"))).toBe(true);
    // Kazakh-specific letters, which Russian does not use — proof the Kazakh
    // dictionary is Kazakh and not Russian pasted into a second slot.
    expect(/[әғқңөұүһі]/.test(joined("kk"))).toBe(true);
    // English is Latin throughout; a stray Cyrillic string here is a value that
    // was never translated.
    expect(cyrillic.test(joined("en"))).toBe(false);
  });
});
