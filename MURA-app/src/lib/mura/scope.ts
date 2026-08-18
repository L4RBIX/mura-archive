/**
 * Narrator metadata for a recording.
 *
 * Family scope used to live here as a hardcoded id. It does not any more: the
 * family a request is scoped to now comes from the authorized list Core returns
 * for the signed-in user, through the family session. There is deliberately no
 * fallback constant left to fall back *to*, because a fallback family id is how
 * a request quietly reaches an archive nobody authorized.
 *
 * What remains is the narrator, and the invariant that governs it: a MURA
 * account is not an archive Person. `speaker_person_id` is therefore never
 * derived from the signed-in user. Core mints canonical `person_<32hex>` ids
 * through entity resolution, and the browser must never manufacture one.
 */

/*
 * The demo narrator is gone.
 *
 * `TRANSITIONAL_DEMO_NARRATOR` supplied the constant name «Айсұлу» as the
 * speaker of every recording, in every family — so an archive could hold a
 * memory told by someone's grandfather and label it with a stranger's name, in
 * permanent server data. Its own comment said it stood in "until the product
 * asks the user who is speaking". The record screen asks now, so the stand-in
 * has been removed rather than left where a future caller could reach it.
 */

/**
 * The canonical archive person for the narrator, when one is genuinely known.
 *
 * Always null today. Nothing in the browser can establish a canonical person,
 * and the authenticated account is emphatically not one -- mapping `user_id` to
 * `speaker_person_id` would invent an archive entity out of a login. Sending
 * null makes Core treat the narrator as not-yet-canonical and resolve it
 * properly, which is the honest behaviour.
 */
export function currentSpeakerPersonId(): string | null {
  return null;
}
