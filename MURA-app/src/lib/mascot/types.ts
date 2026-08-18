/** The swallow's public vocabulary. Business logic speaks only in these terms. */

/** Every pose Ласточка can hold. The animation layer maps these to motion. */
export type MascotState =
  | "idle"
  | "greeting"
  | "listening"
  | "processing"
  | "thinking"
  | "searching"
  | "speaking"
  | "success"
  | "error";

export type MascotEventType =
  | "GREET"
  | "LISTEN"
  | "PROCESS"
  | "THINK"
  | "SEARCH"
  | "SPEAK"
  | "SETTLE"
  | "SUCCEED"
  | "FAIL"
  | "RESET";
