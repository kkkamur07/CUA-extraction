"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { CursorTab } from "@/components/workbench/CursorTab";
import { IntentTab } from "@/components/workbench/IntentTab";
import { KeyboardTab } from "@/components/workbench/KeyboardTab";
import { ScreenTab } from "@/components/workbench/ScreenTab";
import {
  WORKBENCH_TABS,
  type CursorMode,
  type Tab,
} from "@/components/workbench/types";
import { useCursorExtraction } from "@/components/workbench/useCursorExtraction";
import { useIntentExtraction } from "@/components/workbench/useIntentExtraction";
import { useKeystrokeExtraction } from "@/components/workbench/useKeystrokeExtraction";
import { useSelectionState } from "@/components/workbench/useSelectionState";
import type { ProjectSelection } from "@/lib/types";

type Props = {
  id: string;
  videoName: string;
};

export function VideoWorkbench({ id, videoName }: Props) {
  const videoSrc = `/api/videos/${encodeURIComponent(videoName)}`;
  const [tab, setTab] = useState<Tab>("screen");
  const [cursorMode, setCursorMode] = useState<CursorMode>("labels");
  const [stepFrames, setStepFrames] = useState(15);
  const [label, setLabel] = useState("pencil");
  const [ambiguous, setAmbiguous] = useState(false);
  const [autoAdvance, setAutoAdvance] = useState(true);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const selection = useSelectionState(id, videoName);
  const kb = useKeystrokeExtraction(id);
  const intent = useIntentExtraction(id);
  const cursor = useCursorExtraction(id);

  const activeRoiTrack = tab === "keyboard" ? selection.keyboard : selection.screen;
  const runDisabled = !selection.selectionSaved || selection.selectionDirty;
  const setErr = useCallback((msg: string) => setError(msg), []);
  const setOk = useCallback((msg: string) => setStatus(msg), []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await fetch(`/api/projects/${id}/selection`);
      const json = await res.json();
      if (cancelled) return;
      // API returns either a selection object, or `{ selection: null }` when missing.
      const sel = (
        json && typeof json === "object" && "selection" in json
          ? json.selection
          : json
      ) as ProjectSelection | null;
      // Always probe duration/size via ffprobe — browser <video> seeking is unreliable
      // for large files, and saved selections don't store duration.
      const metaRes = await fetch(
        `/api/videos/${encodeURIComponent(videoName)}/meta`,
      );
      const meta = await metaRes.json();
      if (cancelled) return;
      if (!metaRes.ok) {
        throw new Error(meta.error || "Failed to load video metadata");
      }
      if (sel?.screen) {
        selection.applyLoadedSelection(sel);
      }
      selection.onMeta({
        duration: Number(meta.duration) || 0,
        width: Number(meta.width) || 1920,
        height: Number(meta.height) || 1080,
      });
      if (sel?.fps && sel.fps > 0) {
        selection.setFps(sel.fps);
      } else if (typeof meta.fps === "number" && meta.fps > 0) {
        selection.setFps(meta.fps);
      }
      await Promise.all([
        cursor.loadAnnotationCounts(),
        kb.loadKeystrokes(),
        intent.loadIntent(),
        cursor.loadCursor(),
      ]);
    })().catch((err: Error) => setError(err.message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount once per project
  }, [id, videoName]);

  const step = useCallback(
    (direction: -1 | 1) => {
      const track = tab === "keyboard" ? selection.keyboard : selection.screen;
      if (!track) return;
      const delta = (stepFrames / selection.fps) * direction;
      const next = Math.min(
        track.end,
        Math.max(track.start, selection.currentTime + delta),
      );
      selection.setCurrentTime(next);
      if (tab === "screen" || tab === "keyboard") {
        selection.patchTrack(tab, { preview_timestamp: next });
      }
    },
    [selection, stepFrames, tab],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (event.key === "ArrowRight" || event.key === "ArrowDown") {
        event.preventDefault();
        step(1);
      } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
        event.preventDefault();
        step(-1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step]);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.18em] text-[var(--accent)]">Project</p>
          <h1 className="font-[family-name:var(--font-display)] text-3xl tracking-tight">{id}</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">{videoName}</p>
        </div>
        <Link href="/" className="text-sm text-[var(--accent)] underline-offset-4 hover:underline">
          All videos
        </Link>
      </header>

      <nav className="flex flex-wrap gap-2 border-b border-[var(--line)] pb-3">
        {WORKBENCH_TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => {
              setTab(item.id);
              if (item.id === "keyboard" && selection.keyboard) {
                selection.setCurrentTime(
                  selection.keyboard.preview_timestamp || selection.keyboard.start || 0,
                );
              } else if (item.id === "screen" && selection.screen) {
                selection.setCurrentTime(
                  selection.screen.preview_timestamp || selection.screen.start || 0,
                );
              } else if (item.id === "cursor" && selection.screen) {
                selection.setCurrentTime(
                  selection.screen.preview_timestamp || selection.screen.start || 0,
                );
              }
            }}
            className={`rounded px-3 py-1.5 text-sm ${
              tab === item.id
                ? "bg-[var(--ink)] text-[var(--paper)]"
                : "bg-[var(--wash)] text-[var(--ink)] hover:bg-[var(--line)]"
            }`}
          >
            {item.label}
            {item.id === "keyboard" && kb.keystrokes.length > 0
              ? ` · ${kb.keystrokes.length}`
              : ""}
            {item.id === "intent" && intent.intentPairs.length > 0
              ? ` · ${intent.intentPairs.length}`
              : ""}
            {item.id === "cursor" && cursor.cursorEvents.length > 0
              ? ` · ${cursor.cursorEvents.length}`
              : ""}
          </button>
        ))}
      </nav>

      {tab === "screen" && selection.screen && (
        <ScreenTab
          videoSrc={videoSrc}
          screen={selection.screen}
          duration={selection.duration}
          currentTime={selection.currentTime}
          fps={selection.fps}
          saving={selection.saving}
          selectionDirty={selection.selectionDirty}
          onTimeUpdate={selection.setCurrentTime}
          onMeta={selection.onMeta}
          onRoiChange={(roi) =>
            selection.patchTrack("screen", {
              roi,
              preview_timestamp: selection.currentTime,
            })
          }
          onPatch={(patch) => selection.patchTrack("screen", patch)}
          onFpsChange={(value) => {
            selection.setFps(value);
            if (selection.selectionSaved) selection.setSelectionDirty(true);
          }}
          onSave={() =>
            selection.saveSelection(
              { syncRangeFromScreen: true, tab },
              setOk,
              setErr,
            )
          }
        />
      )}

      {tab === "keyboard" && selection.keyboard && (
        <KeyboardTab
          videoSrc={videoSrc}
          keyboard={selection.keyboard}
          duration={selection.duration}
          currentTime={selection.currentTime}
          fps={selection.fps}
          saving={selection.saving}
          runDisabled={runDisabled}
          kbRunning={kb.kbRunning}
          kbJob={kb.kbJob}
          keystrokes={kb.keystrokes}
          kbSelected={kb.kbSelected}
          onTimeUpdate={selection.setCurrentTime}
          onMeta={selection.onMeta}
          onRoiChange={(roi) =>
            selection.patchTrack("keyboard", {
              roi,
              preview_timestamp: selection.currentTime,
            })
          }
          onPatch={(patch) => selection.patchTrack("keyboard", patch)}
          onSave={() =>
            selection.saveSelection(
              { syncRangeFromScreen: false, tab },
              setOk,
              setErr,
            )
          }
          onRun={() =>
            kb.runKeyboardExtraction(
              {
                selectionSaved: selection.selectionSaved,
                selectionDirty: selection.selectionDirty,
              },
              setOk,
              setErr,
            )
          }
          onSelectEvent={(event, index) => {
            kb.setKbSelected(index);
            selection.setCurrentTime(event.press_t);
          }}
        />
      )}

      {tab === "intent" && (
        <IntentTab
          runDisabled={runDisabled}
          running={intent.intentRunning}
          job={intent.intentJob}
          summary={intent.intentSummary}
          pairs={intent.intentPairs}
          transcript={intent.intentTranscript}
          errors={intent.intentErrors}
          providers={intent.providers}
          onRun={() =>
            intent.runIntentExtraction(
              {
                selectionSaved: selection.selectionSaved,
                selectionDirty: selection.selectionDirty,
              },
              setOk,
              setErr,
            )
          }
        />
      )}

      {tab === "cursor" && selection.screen && (
        <CursorTab
          videoSrc={videoSrc}
          screen={selection.screen}
          mode={cursorMode}
          currentTime={selection.currentTime}
          fps={selection.fps}
          stepFrames={stepFrames}
          label={label}
          ambiguous={ambiguous}
          autoAdvance={autoAdvance}
          annotationCount={cursor.annotationCount}
          labelCounts={cursor.labelCounts}
          runDisabled={runDisabled}
          cursorRunning={cursor.cursorRunning}
          cursorEvents={cursor.cursorEvents}
          weights={cursor.weights}
          onModeChange={setCursorMode}
          onTimeUpdate={selection.setCurrentTime}
          onMeta={selection.onMeta}
          onBbox={(box, dataUrl) =>
            cursor.saveAnnotation(
              box,
              dataUrl,
              {
                label,
                ambiguous,
                autoAdvance,
                stepFrames,
                fps: selection.fps,
                currentTime: selection.currentTime,
                screen: selection.screen!,
              },
              setOk,
              setErr,
              selection.setCurrentTime,
            )
          }
          onLabelChange={setLabel}
          onAmbiguousChange={setAmbiguous}
          onAutoAdvanceChange={setAutoAdvance}
          onStepFramesChange={setStepFrames}
          onStep={step}
          onRunExtract={() =>
            cursor.runCursorExtraction(
              {
                selectionSaved: selection.selectionSaved,
                selectionDirty: selection.selectionDirty,
              },
              setOk,
              setErr,
            )
          }
        />
      )}

      {!activeRoiTrack && (tab === "screen" || tab === "keyboard") && (
        <p className="text-sm text-[var(--muted)]">Loading video metadata…</p>
      )}

      {(status || error) && (
        <div className="space-y-1 text-sm">
          {status && <p className="text-[var(--muted)]">{status}</p>}
          {error && <p className="text-rose-700">{error}</p>}
        </div>
      )}
    </div>
  );
}
