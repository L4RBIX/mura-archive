"use client";

/**
 * What the browser will let us do with a microphone, without asking for it yet.
 *
 * Permission is only *queried*, never requested here: prompting on page load is
 * how a permission dialog appears before the user has expressed any intent, and
 * a dismissed prompt is much harder to recover from than an unasked one. The
 * actual request happens when the user taps record.
 *
 * The Permissions API is not universal, so an unknown permission is reported as
 * unknown rather than assumed denied — the recorder can still try, and the
 * browser will ask.
 */

import { useEffect, useState } from "react";
import type { MicrophoneState } from "@/lib/mura/recording-availability";

const INITIAL: MicrophoneState = { supported: true, permission: "unknown" };

export function useMicrophoneState(): MicrophoneState {
  const [state, setState] = useState<MicrophoneState>(INITIAL);

  useEffect(() => {
    let cancelled = false;

    const supported =
      typeof navigator !== "undefined" &&
      typeof navigator.mediaDevices?.getUserMedia === "function" &&
      typeof window !== "undefined" &&
      typeof window.MediaRecorder !== "undefined";

    if (!supported) {
      setState({ supported: false, permission: "unknown" });
      return;
    }

    const permissions = navigator.permissions;
    if (!permissions?.query) {
      setState({ supported: true, permission: "unknown" });
      return;
    }

    let status: PermissionStatus | null = null;
    const onChange = () => {
      if (!cancelled && status) {
        setState({ supported: true, permission: status.state as MicrophoneState["permission"] });
      }
    };

    permissions
      // Not every engine knows the "microphone" descriptor; a rejection here
      // means "cannot tell", which is exactly `unknown`.
      .query({ name: "microphone" as PermissionName })
      .then((result) => {
        if (cancelled) return;
        status = result;
        setState({ supported: true, permission: result.state as MicrophoneState["permission"] });
        result.addEventListener("change", onChange);
      })
      .catch(() => {
        if (!cancelled) setState({ supported: true, permission: "unknown" });
      });

    return () => {
      cancelled = true;
      status?.removeEventListener("change", onChange);
    };
  }, []);

  return state;
}
