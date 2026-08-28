"use client";

import { useState } from "react";
import { CreateFamily } from "@/components/family/family-gate";
import { FirstRun } from "@/components/home/first-run";
import { RoleStep } from "@/components/onboarding/role-step";
import { useNarratorRole } from "@/lib/mura/narrator-role";
import { useMuraSession } from "@/lib/mura/session-provider";

/**
 * First run, in place, on the screen the user already landed on.
 *
 * The four steps the product needs are account → family → role → first memory.
 * The first is the auth provider's, and the last is `/record`; these are the two
 * in between, and they happen here rather than in a wizard route of their own.
 *
 * That is deliberate. A separate `/onboarding` route has to be entered, guarded,
 * exited and kept in sync with what the session already knows — and it puts a
 * corridor between someone and the thing they came to do. Home already knows
 * whether a family exists and whether the archive is empty, so it can simply
 * show the next unanswered question and nothing else.
 *
 * Each step is skippable or self-completing, and none of them blocks the app:
 * the navigation, the recorder and the settings stay reachable throughout.
 */
export function FirstRunFlow() {
  const { family } = useMuraSession();
  const { role, resolved } = useNarratorRole();
  // Answering is not the only way past the role step; skipping is too, and a
  // skip must not be re-asked on the next render.
  const [dismissedRole, setDismissedRole] = useState(false);

  // Step 2. No family yet, so there is nothing else to offer — and until this
  // was here, a user who signed up and landed on Home had no way to make one.
  if (family.status === "no_families") {
    return <CreateFamily standalone={false} />;
  }

  // Step 3. Asked once, between the family existing and the first recording,
  // which is the only point at which the answer changes anything.
  if (resolved && role === null && !dismissedRole) {
    return <RoleStep onDone={() => setDismissedRole(true)} />;
  }

  // Step 4. What to say, and four openings to say it with.
  return <FirstRun />;
}
