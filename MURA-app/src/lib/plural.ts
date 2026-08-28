/**
 * Russian and Kazakh plural agreement.
 *
 * "2 рассказов" is wrong, and it was appearing on the home screen. Russian
 * picks a form from the last two digits — one, few (2–4) or many — with a
 * genuine exception for the teens, where 11 takes the *many* form despite
 * ending in 1. Concatenating a count with a fixed word gets this wrong for
 * most numbers a family archive will actually reach.
 *
 * Kazakh does not inflate the noun after a numeral at all, so its three keys
 * carry the same word and this returns whichever; keeping the same call shape
 * for both languages avoids a per-locale branch at every call site.
 *
 * English has two forms, not three. It reuses `many` as its plural bucket
 * rather than gaining a fourth name, so the three dictionary keys stay the
 * same shape in every language and no call site has to know how many forms the
 * current locale actually distinguishes.
 */

export type PluralForm = "one" | "few" | "many";

export function pluralForm(count: number, locale: string): PluralForm {
  if (locale === "kk") return "one";
  // Note this is `=== 1`, not "ends in 1": English says "21 people", and 0
  // takes the plural ("0 people"), unlike the Russian rule below.
  if (locale === "en") return Math.abs(count) === 1 ? "one" : "many";

  const absolute = Math.abs(Math.trunc(count));
  const lastTwo = absolute % 100;
  // 11–14 take the many form even though 11 and 12 end in 1 and 2.
  if (lastTwo >= 11 && lastTwo <= 14) return "many";

  const last = absolute % 10;
  if (last === 1) return "one";
  if (last >= 2 && last <= 4) return "few";
  return "many";
}
