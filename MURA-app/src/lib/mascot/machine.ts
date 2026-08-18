import type { MascotEventType, MascotState } from "@/lib/mascot/types";

/**
 * The whole state machine, as one table. A transition that is not listed is a
 * no-op — so a late `SETTLE` from an audio clip that was already interrupted
 * can never knock the mascot out of the state it moved on to.
 */
const TRANSITIONS: Record<
  MascotState,
  Partial<Record<MascotEventType, MascotState>>
> = {
  idle: {
    GREET: "greeting",
    LISTEN: "listening",
    PROCESS: "processing",
    // Work can already be underway when she finishes a sentence and settles,
    // so idle has to be able to rejoin it mid-stage.
    THINK: "thinking",
    SEARCH: "searching",
    SPEAK: "speaking",
    FAIL: "error",
  },
  greeting: {
    SPEAK: "speaking",
    LISTEN: "listening",
    SETTLE: "idle",
    FAIL: "error",
  },
  listening: {
    PROCESS: "processing",
    SETTLE: "idle",
    FAIL: "error",
  },
  processing: {
    THINK: "thinking",
    SEARCH: "searching",
    SPEAK: "speaking",
    SUCCEED: "success",
    FAIL: "error",
  },
  thinking: {
    SEARCH: "searching",
    SPEAK: "speaking",
    SUCCEED: "success",
    FAIL: "error",
  },
  searching: {
    SPEAK: "speaking",
    SUCCEED: "success",
    FAIL: "error",
  },
  speaking: {
    SETTLE: "idle",
    SUCCEED: "success",
    LISTEN: "listening",
    FAIL: "error",
  },
  success: {
    SETTLE: "idle",
    LISTEN: "listening",
    GREET: "greeting",
    FAIL: "error",
  },
  error: {
    RESET: "idle",
    LISTEN: "listening",
    GREET: "greeting",
  },
};

/** Deterministic: same state + same event always yields the same next state. */
export function transition(
  state: MascotState,
  event: MascotEventType,
): MascotState {
  return TRANSITIONS[state][event] ?? state;
}

export function canTransition(
  state: MascotState,
  event: MascotEventType,
): boolean {
  return TRANSITIONS[state][event] !== undefined;
}


/** States that mean "working on it" — all share the thinking motion family. */
export const BUSY_STATES: ReadonlySet<MascotState> = new Set<MascotState>([
  "processing",
  "thinking",
  "searching",
]);
