"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ActionIntentPair } from "@/lib/types";

import type { IntentJob, IntentProviderStatus } from "./types";

const ACTIVE = new Set([
  "starting",
  "running",
  "extracting",
  "transcribing",
  "summarizing",
]);

export function useIntentExtraction(projectId: string) {
  const [intentRunning, setIntentRunning] = useState(false);
  const [intentJob, setIntentJob] = useState<IntentJob | null>(null);
  const [intentSummary, setIntentSummary] = useState<string | null>(null);
  const [intentPairs, setIntentPairs] = useState<ActionIntentPair[]>([]);
  const [intentTranscript, setIntentTranscript] = useState<string | null>(null);
  const [intentErrors, setIntentErrors] = useState<Record<string, string>>({});
  const [providers, setProviders] = useState<IntentProviderStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const loadRef = useRef<() => Promise<unknown>>(async () => null);

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPoll = useCallback(() => {
    stopPoll();
    pollRef.current = setInterval(() => {
      loadRef.current().catch(() => undefined);
    }, 500);
  }, [stopPoll]);

  const loadIntent = useCallback(async () => {
    const res = await fetch(`/api/projects/${projectId}/extract/intent`);
    const json = await res.json();
    if (json.providers && typeof json.providers === "object") {
      setProviders(json.providers as IntentProviderStatus);
    }
    if (json.job && typeof json.job === "object") {
      setIntentJob(json.job as IntentJob);
    }
    setIntentSummary(typeof json.summary === "string" ? json.summary : null);
    setIntentPairs(Array.isArray(json.pairs) ? (json.pairs as ActionIntentPair[]) : []);
    const trimmed = json.speechTrimmed as { text?: string } | null;
    const full = json.speechFull as { text?: string } | null;
    setIntentTranscript(trimmed?.text || full?.text || null);

    const state = (json.job as IntentJob | null)?.state;
    if (state === "done" || state === "error") {
      setIntentRunning(false);
      stopPoll();
      if (state === "error" && json.job?.error) {
        setIntentErrors({ intent: String(json.job.error) });
      }
    } else if (state && ACTIVE.has(state)) {
      setIntentRunning(true);
      if (!pollRef.current) startPoll();
    }
    return json;
  }, [projectId, startPoll, stopPoll]);

  loadRef.current = loadIntent;

  useEffect(() => () => stopPoll(), [stopPoll]);

  const runIntentExtraction = async (
    opts: { selectionSaved: boolean; selectionDirty: boolean },
    onStatus: (msg: string) => void,
    onError: (msg: string) => void,
  ) => {
    if (!opts.selectionSaved) {
      onError("Save selection first.");
      return;
    }
    if (opts.selectionDirty) {
      onError("Save selection changes before running intent extraction.");
      return;
    }
    onError("");
    onStatus("");
    setIntentRunning(true);
    setIntentErrors({});
    try {
      const res = await fetch(`/api/projects/${projectId}/extract/intent`, {
        method: "POST",
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Failed to start intent extraction");
      if (json.job) setIntentJob(json.job as IntentJob);
      onStatus(json.message || "Intent extraction started");
      startPoll();
      await loadIntent();
    } catch (err) {
      setIntentRunning(false);
      onError(err instanceof Error ? err.message : "Intent extraction failed");
    }
  };

  return {
    intentRunning,
    intentJob,
    intentSummary,
    intentPairs,
    intentTranscript,
    intentErrors,
    providers,
    loadIntent,
    runIntentExtraction,
  };
}
