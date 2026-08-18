"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMemoryOwner } from "@/lib/memory-store";

export type RecorderStatus = "idle" | "recording" | "paused";

function supportedMimeType() {
  return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"].find((type) =>
    MediaRecorder.isTypeSupported(type),
  );
}

/** Real microphone recorder with pause/resume and a final uploadable audio Blob. */
export function useRecorder() {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (status !== "recording") return;
    const id = setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => clearInterval(id);
  }, [status]);

  const stopTracks = useCallback(() => {
    if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current);
    animationFrameRef.current = null;
    void audioContextRef.current?.close();
    audioContextRef.current = null;
    setLevel(0);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const track = stream.getAudioTracks()[0];
      if (!track || track.readyState !== "live") {
        stream.getTracks().forEach((item) => item.stop());
        throw new Error("microphone_track_unavailable");
      }
      const mimeType = supportedMimeType();
      const recorder = new MediaRecorder(
        stream,
        mimeType ? { mimeType, audioBitsPerSecond: 64_000 } : undefined,
      );
      const audioContext = new AudioContext();
      if (audioContext.state === "suspended") {
        await audioContext.resume().catch(() => undefined);
      }
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.2;
      audioContext.createMediaStreamSource(stream).connect(analyser);
      const samples = new Uint8Array(analyser.frequencyBinCount);
      const updateLevel = () => {
        analyser.getByteTimeDomainData(samples);
        let sum = 0;
        for (const sample of samples) {
          const normalized = (sample - 128) / 128;
          sum += normalized * normalized;
        }
        setLevel(Math.min(1, Math.sqrt(sum / samples.length) * 4));
        animationFrameRef.current = requestAnimationFrame(updateLevel);
      };
      audioContextRef.current = audioContext;
      updateLevel();
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        setError("microphone_unavailable");
      };
      recorder.start(500);
      streamRef.current = stream;
      recorderRef.current = recorder;
      setStatus("recording");
    } catch {
      setError("microphone_unavailable");
      setStatus("idle");
    }
  }, []);

  const pause = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder?.state === "recording") {
      recorder.pause();
      setStatus("paused");
    }
  }, []);

  const resume = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder?.state === "paused") {
      recorder.resume();
      setStatus("recording");
    }
  }, []);

  const finish = useCallback(async (): Promise<Blob | null> => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return null;
    return new Promise((resolve) => {
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        stopTracks();
        recorderRef.current = null;
        setStatus("idle");
        resolve(blob.size > 0 ? blob : null);
      };
      recorder.stop();
    });
  }, [stopTracks]);

  /**
   * Throw away whatever is being recorded, without producing a Blob.
   *
   * `finish` is the deliberate path that yields audio to upload; this is the
   * other one -- the take is abandoned and the bytes are dropped.
   */
  const discard = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      // Detach first: the final dataavailable must not repopulate the chunks
      // we are about to drop.
      recorder.ondataavailable = null;
      recorder.onstop = null;
      recorder.stop();
    }
    recorderRef.current = null;
    chunksRef.current = [];
    stopTracks();
    setSeconds(0);
    setError(null);
    setStatus("idle");
  }, [stopTracks]);

  // An unsent take belongs to the session that started it. If the account
  // changes -- signing out, or switching user in another tab -- the audio is
  // dropped and the microphone released rather than carried into the next
  // session.
  const owner = useMemoryOwner();
  const firstOwner = useRef(true);
  useEffect(() => {
    if (firstOwner.current) {
      firstOwner.current = false;
      return;
    }
    discard();
  }, [owner, discard]);

  const restart = useCallback(async () => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    stopTracks();
    recorderRef.current = null;
    chunksRef.current = [];
    setSeconds(0);
    await start();
  }, [start, stopTracks]);

  useEffect(
    () => () => {
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") recorder.stop();
      stopTracks();
    },
    [stopTracks],
  );

  return { status, seconds, level, error, start, pause, resume, restart, finish, discard };
}
