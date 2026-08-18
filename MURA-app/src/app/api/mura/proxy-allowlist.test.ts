import { describe, expect, it } from "vitest";
import { isAllowedCoreRoute } from "./[...path]/proxy";

const FAMILY = `family_${"a".repeat(32)}`;
const USER = `user_${"c".repeat(32)}`;
const RECORDING = `rec_${"a".repeat(32)}`;
const JOB = `job_${"b".repeat(32)}`;

describe("proxy allowlist", () => {
  it("allows the canonical application endpoints", () => {
    expect(isAllowedCoreRoute("GET", "v1/capabilities")).toBe(true);
    expect(isAllowedCoreRoute("GET", "v1/me")).toBe(true);
    expect(isAllowedCoreRoute("GET", "v1/families")).toBe(true);
    expect(isAllowedCoreRoute("POST", "v1/families")).toBe(true);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}`)).toBe(true);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/members`)).toBe(true);
    expect(isAllowedCoreRoute("PATCH", `v1/families/${FAMILY}/members/${USER}`)).toBe(true);
    expect(isAllowedCoreRoute("DELETE", `v1/families/${FAMILY}/members/${USER}`)).toBe(true);
    expect(isAllowedCoreRoute("POST", `v1/families/${FAMILY}/recordings`)).toBe(true);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/recordings/${RECORDING}`)).toBe(
      true,
    );
    expect(
      isAllowedCoreRoute("GET", `v1/families/${FAMILY}/recordings/${RECORDING}/review-items`),
    ).toBe(true);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/jobs/${JOB}`)).toBe(true);
  });

  it("rejects obsolete application routes", () => {
    expect(isAllowedCoreRoute("GET", "v1/health")).toBe(false);
    expect(isAllowedCoreRoute("POST", `v1/jobs/${JOB}/retry`)).toBe(false);
    expect(isAllowedCoreRoute("GET", "v1/demo/fixtures")).toBe(false);
    expect(isAllowedCoreRoute("POST", "v1/demo/replay")).toBe(false);
    expect(isAllowedCoreRoute("POST", "v1/recordings")).toBe(false);
    expect(isAllowedCoreRoute("GET", `v1/jobs/${JOB}`)).toBe(false);
  });

  it("never exposes service-internal, operator or worker surfaces to the browser", () => {
    // Core classifies these three as service-internal: they answer to the
    // application credential, which this app deliberately does not hold.
    expect(isAllowedCoreRoute("POST", "v1/process-transcript")).toBe(false);
    expect(isAllowedCoreRoute("GET", `v1/jobs/${JOB}/trace`)).toBe(false);
    expect(isAllowedCoreRoute("POST", `v1/families/${FAMILY}/replays`)).toBe(false);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/replays`)).toBe(false);

    expect(isAllowedCoreRoute("GET", "v1/operations/release")).toBe(false);
    expect(isAllowedCoreRoute("POST", "v1/operations/release/activate")).toBe(false);
    expect(isAllowedCoreRoute("POST", "v1/operations/release/rollback")).toBe(false);
    expect(isAllowedCoreRoute("GET", "v1/operations/retention")).toBe(false);
    expect(isAllowedCoreRoute("POST", "v1/operations/retention/apply")).toBe(false);

    expect(isAllowedCoreRoute("POST", "v1/workers/register")).toBe(false);
    expect(isAllowedCoreRoute("GET", "v1/workers/current")).toBe(false);
  });

  it("opens family surfaces only once a screen consumes them", () => {
    // The rule is unchanged -- an allowlist entry without a consumer is attack
    // surface bought for nothing -- but PR-06 gave these consumers: the tree,
    // person, story and review screens read them instead of fixtures.
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/archive`)).toBe(true);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/people`)).toBe(true);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/relationships`)).toBe(true);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/stories`)).toBe(true);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/review-items`)).toBe(true);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/conflicts`)).toBe(true);
  });

  it("still refuses family surfaces nothing consumes", () => {
    // Deterministic replay is release tooling. Family membership does not
    // grant it, and no screen asks for it.
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/replays`)).toBe(false);
    expect(isAllowedCoreRoute("POST", `v1/families/${FAMILY}/replays`)).toBe(false);
  });

  it("pins archive reads to GET", () => {
    // Nothing in the archive is mutated from a browser except a conflict
    // decision, which has its own explicit POST entries.
    expect(isAllowedCoreRoute("POST", `v1/families/${FAMILY}/people`)).toBe(false);
    expect(isAllowedCoreRoute("DELETE", `v1/families/${FAMILY}/stories`)).toBe(false);
    expect(isAllowedCoreRoute("POST", `v1/families/${FAMILY}/relationships`)).toBe(false);
  });

  it("rejects traversal and malformed paths", () => {
    expect(isAllowedCoreRoute("GET", "v1/../v1/operations/release")).toBe(false);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}//recordings`)).toBe(false);
    expect(isAllowedCoreRoute("GET", "/v1/capabilities")).toBe(false);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/recordings/rec_nothex`)).toBe(
      false,
    );
    expect(isAllowedCoreRoute("GET", `v1/families/bad family/jobs/${JOB}`)).toBe(false);
    expect(isAllowedCoreRoute("GET", "")).toBe(false);
  });

  it("pins each route to the method it supports", () => {
    expect(isAllowedCoreRoute("POST", "v1/capabilities")).toBe(false);
    expect(isAllowedCoreRoute("POST", "v1/me")).toBe(false);
    expect(isAllowedCoreRoute("GET", `v1/families/${FAMILY}/recordings`)).toBe(false);
    expect(isAllowedCoreRoute("DELETE", `v1/families/${FAMILY}/jobs/${JOB}`)).toBe(false);
    expect(isAllowedCoreRoute("DELETE", `v1/families/${FAMILY}`)).toBe(false);
    // Adding a member needs an invitation lifecycle Core does not have.
    expect(isAllowedCoreRoute("POST", `v1/families/${FAMILY}/members`)).toBe(false);
  });

  it("only accepts a canonical Core user id in the membership path", () => {
    expect(isAllowedCoreRoute("PATCH", `v1/families/${FAMILY}/members/not-a-user`)).toBe(false);
    expect(isAllowedCoreRoute("DELETE", `v1/families/${FAMILY}/members/user_short`)).toBe(false);
  });
});
