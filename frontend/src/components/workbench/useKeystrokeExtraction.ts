"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { KeystrokeJob } from "@/components/workbench/types";
import type { KeystrokeRawEvent } from "@/lib/types";

export function useKeystrokeExtraction(projectId: string) {
  const [kbRunning, setKbRunning] = useState(false);
  const [kbJob, setKbJob] = useState<KeystrokeJob | null>(null);
  const [keystrokes, setKeystrokes] = useState<KeystrokeRawEvent[]>([]);
  const [kbSelected, setKbSelected] = useState<number | null>(null);
  const kbPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopKbPoll = useCallback(() => {
    if (kbPollRef.current) {
      clearInterval(kbPollRef.current);
      kbPollRef.current = null;
    }
  }, []);

  const loadKeystrokes = useCallback(async () => {
    const res = await fetch(`/api/projects/${projectId}/extract/keystrokes`);
    const json = await res.json();
    if (json.job) setKbJob(json.job as KeystrokeJob);
    const events = Array.isArray(json.events)
      ? (json.events as KeystrokeRawEvent[]).map((e) => ({
          type: "keystroke" as const,
          key: String(e.key),
          press_t: Number(e.press_t),
          release_t: Number(e.release_t),
          clipped: Boolean(e.clipped),
        }))
      : [];
    setKeystrokes(events);
    const state = json.job?.state as string | undefined;
    if (state === "done" || state === "error") {
      setKbRunning(false);
      stopKbPoll();
    } else if (state === "running" || state === "starting" || state === "detecting") {
      setKbRunning(true);
    }
    return json;
  }, [projectId, stopKbPoll]);

  const startKbPoll = useCallback(() => {
    stopKbPoll();
    kbPollRef.current = setInterval(() => {
      loadKeystrokes().catch(() => undefined);
    }, 400);
  }, [loadKeystrokes, stopKbPoll]);

  useEffect(() => () => stopKbPoll(), [stopKbPoll]);

  const runKeyboardExtraction = async (
    opts: { selectionSaved: boolean; selectionDirty: boolean },
    onStatus: (msg: string) => void,
    onError: (msg: string) => void,
  ) => {
    if (!opts.selectionSaved) {
      onError("Save selection first (Screen + Keyboard ROI).");
      return;
    }
    if (opts.selectionDirty) {
      onError("Save selection changes before running keyboard extraction.");
      return;
    }
    onError("");
    onStatus("");
    setKbRunning(true);
    setKbSelected(null);
    try {
      const res = await fetch(`/api/projects/${projectId}/extract/keystrokes`, {
        method: "POST",
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Failed to start keyboard extraction");
      onStatus(json.message || "Keyboard extraction started");
      startKbPoll();
      await loadKeystrokes();
    } catch (err) {
      setKbRunning(false);
      onError(err instanceof Error ? err.message : "Keyboard extraction failed");
    }
  };

  return {
    kbRunning,
    kbJob,
    keystrokes,
    kbSelected,
    setKbSelected,
    loadKeystrokes,
    stopKbPoll,
    runKeyboardExtraction,
  };
}
