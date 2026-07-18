"use client";

import { useCallback, useState } from "react";

import type { CropROI, CursorRawEvent, TrackSelection } from "@/lib/types";

import type { CursorWeightsStatus } from "./types";

type AnnotationOpts = {
  label: string;
  ambiguous: boolean;
  autoAdvance: boolean;
  stepFrames: number;
  fps: number;
  currentTime: number;
  screen: TrackSelection;
};

export function useCursorExtraction(projectId: string) {
  const [cursorRunning, setCursorRunning] = useState(false);
  const [cursorEvents, setCursorEvents] = useState<CursorRawEvent[]>([]);
  const [annotationCount, setAnnotationCount] = useState(0);
  const [labelCounts, setLabelCounts] = useState<Record<string, number>>({});
  const [weights, setWeights] = useState<CursorWeightsStatus | null>(null);

  const loadCursor = useCallback(async () => {
    const res = await fetch(`/api/projects/${projectId}/extract/cursor`);
    const json = await res.json();
    if (json.weights && typeof json.weights === "object") {
      setWeights(json.weights as CursorWeightsStatus);
    }
    setCursorEvents(Array.isArray(json.events) ? (json.events as CursorRawEvent[]) : []);
  }, [projectId]);

  const loadAnnotationCounts = useCallback(async () => {
    const res = await fetch(`/api/projects/${projectId}/annotations`);
    const json = await res.json();
    setAnnotationCount(json.count ?? 0);
    const counts: Record<string, number> = {};
    for (const record of json.records ?? []) {
      const key = String(record.label ?? "unknown");
      counts[key] = (counts[key] ?? 0) + 1;
    }
    setLabelCounts(counts);
  }, [projectId]);

  const runCursorExtraction = async (
    opts: { selectionSaved: boolean; selectionDirty: boolean },
    onStatus: (msg: string) => void,
    onError: (msg: string) => void,
  ) => {
    if (!opts.selectionSaved) {
      onError("Save selection first.");
      return;
    }
    if (opts.selectionDirty) {
      onError("Save selection changes before running cursor extraction.");
      return;
    }
    setCursorRunning(true);
    onError("");
    onStatus("Running YOLO cursor extraction…");
    try {
      const res = await fetch(`/api/projects/${projectId}/extract/cursor`, {
        method: "POST",
      });
      const json = await res.json();
      if (json.weights && typeof json.weights === "object") {
        setWeights(json.weights as CursorWeightsStatus);
      }
      if (!res.ok || !json.ok) throw new Error(json.error || "Cursor extraction failed");
      setCursorEvents(Array.isArray(json.events) ? (json.events as CursorRawEvent[]) : []);
      onStatus(json.message || `Wrote ${json.events?.length ?? 0} cursor events`);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Cursor extraction failed");
    } finally {
      setCursorRunning(false);
    }
  };

  const saveAnnotation = async (
    box: CropROI,
    patchDataUrl: string,
    opts: AnnotationOpts,
    onStatus: (msg: string) => void,
    onError: (msg: string) => void,
    onAdvance: (next: number) => void,
  ) => {
    const frameNumber = Math.round(opts.currentTime * opts.fps);
    try {
      const res = await fetch(`/api/projects/${projectId}/annotations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: opts.label,
          frame_number: frameNumber,
          timestamp_seconds: opts.currentTime,
          x: box.x,
          y: box.y,
          width: box.width,
          height: box.height,
          ambiguous: opts.ambiguous,
          track: "screen",
          image_data_url: patchDataUrl,
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Annotation failed");
      setAnnotationCount((count) => count + 1);
      setLabelCounts((prev) => ({
        ...prev,
        [opts.label]: (prev[opts.label] ?? 0) + 1,
      }));
      onStatus(`Saved ${opts.label} @ frame ${frameNumber}`);
      onError("");
      if (opts.autoAdvance) {
        const delta = opts.stepFrames / opts.fps;
        const next = Math.min(
          opts.screen.end,
          Math.max(opts.screen.start, opts.currentTime + delta),
        );
        onAdvance(next);
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Annotation failed");
    }
  };

  return {
    cursorRunning,
    cursorEvents,
    annotationCount,
    labelCounts,
    weights,
    loadCursor,
    loadAnnotationCounts,
    runCursorExtraction,
    saveAnnotation,
  };
}
