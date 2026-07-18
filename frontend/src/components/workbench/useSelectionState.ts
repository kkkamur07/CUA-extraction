"use client";

import { useCallback, useState } from "react";

import {
  defaultTrack,
  flattenScreen,
  type ProjectSelection,
  type TrackKind,
  type TrackSelection,
} from "@/lib/types";

export function useSelectionState(projectId: string, videoName: string) {
  const [duration, setDuration] = useState(0);
  const [width, setWidth] = useState(1920);
  const [height, setHeight] = useState(1080);
  const [fps, setFps] = useState(30);
  const [currentTime, setCurrentTime] = useState(0);
  const [saving, setSaving] = useState(false);
  const [screen, setScreen] = useState<TrackSelection | null>(null);
  const [keyboard, setKeyboard] = useState<TrackSelection | null>(null);
  const [selectionSaved, setSelectionSaved] = useState(false);
  const [selectionDirty, setSelectionDirty] = useState(false);

  const ensureTracks = useCallback((w: number, h: number, d: number) => {
    setScreen((prev) => prev ?? defaultTrack(w, h, d));
    setKeyboard((prev) => {
      if (prev) return prev;
      const kh = Math.min(240, h);
      return {
        ...defaultTrack(w, kh, d),
        roi: { x: 0, y: Math.max(0, h - kh), width: w, height: kh },
      };
    });
  }, []);

  const onMeta = useCallback(
    ({ duration: d, width: w, height: h }: { duration: number; width: number; height: number }) => {
      // Frame preview may report duration 0 — don't clobber ffprobe duration.
      setDuration((prev) => (d > 0 ? d : prev));
      setWidth(w);
      setHeight(h);
      ensureTracks(w, h, d > 0 ? d : 0);
    },
    [ensureTracks],
  );

  const patchTrack = useCallback(
    (kind: TrackKind, patch: Partial<TrackSelection>) => {
      const setter = kind === "keyboard" ? setKeyboard : setScreen;
      setter((prev) => (prev ? { ...prev, ...patch } : prev));
      if (selectionSaved) setSelectionDirty(true);
    },
    [selectionSaved],
  );

  const applyLoadedSelection = (selection: ProjectSelection) => {
    setScreen(selection.screen);
    setKeyboard(selection.keyboard);
    setFps(selection.fps || 30);
    setWidth(selection.frame_width);
    setHeight(selection.frame_height);
    setCurrentTime(selection.screen.preview_timestamp || selection.screen.start || 0);
    setSelectionSaved(true);
    setSelectionDirty(false);
  };

  const saveSelection = async (
    opts: { syncRangeFromScreen: boolean; tab: "screen" | "keyboard" | string },
    onStatus: (msg: string) => void,
    onError: (msg: string) => void,
  ) => {
    if (!screen || !keyboard) {
      onError("Wait for the video to load before saving.");
      return;
    }
    setSaving(true);
    onError("");
    onStatus("");

    const nextScreen = {
      ...screen,
      preview_timestamp:
        opts.tab === "screen" ? currentTime : screen.preview_timestamp,
    };
    let nextKeyboard = {
      ...keyboard,
      preview_timestamp:
        opts.tab === "keyboard" ? currentTime : keyboard.preview_timestamp,
    };
    if (opts.syncRangeFromScreen) {
      nextKeyboard = {
        ...nextKeyboard,
        start: nextScreen.start,
        end: nextScreen.end,
      };
    }

    const payload = flattenScreen({
      id: projectId,
      video: `video/${videoName}`,
      fps,
      frame_width: width,
      frame_height: height,
      preview_timestamp: nextScreen.preview_timestamp,
      roi: nextScreen.roi,
      start: nextScreen.start,
      end: nextScreen.end,
      screen: nextScreen,
      keyboard: nextKeyboard,
    });
    try {
      const res = await fetch(`/api/projects/${projectId}/selection`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Save failed");
      setScreen(json.screen);
      setKeyboard(json.keyboard);
      setSelectionSaved(true);
      setSelectionDirty(false);
      onStatus(`Saved runs/${projectId}/selection.json`);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return {
    duration,
    width,
    height,
    fps,
    setFps,
    currentTime,
    setCurrentTime,
    saving,
    screen,
    keyboard,
    selectionSaved,
    selectionDirty,
    setSelectionDirty,
    onMeta,
    patchTrack,
    applyLoadedSelection,
    saveSelection,
  };
}
