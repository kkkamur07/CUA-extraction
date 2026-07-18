"use client";

import { LabelSearch } from "@/components/LabelSearch";
import { VideoCanvas } from "@/components/VideoCanvas";
import type { CropROI, CursorRawEvent, TrackSelection } from "@/lib/types";

import { formatTime } from "./format";
import { LABEL_PRESETS, type CursorMode, type CursorWeightsStatus } from "./types";

type Props = {
  videoSrc: string;
  screen: TrackSelection;
  mode: CursorMode;
  currentTime: number;
  fps: number;
  stepFrames: number;
  label: string;
  ambiguous: boolean;
  autoAdvance: boolean;
  annotationCount: number;
  labelCounts: Record<string, number>;
  runDisabled: boolean;
  cursorRunning: boolean;
  cursorEvents: CursorRawEvent[];
  weights: CursorWeightsStatus | null;
  onModeChange: (mode: CursorMode) => void;
  onTimeUpdate: (t: number) => void;
  onMeta: (meta: { duration: number; width: number; height: number }) => void;
  onBbox: (box: CropROI, patchDataUrl: string) => void;
  onLabelChange: (label: string) => void;
  onAmbiguousChange: (v: boolean) => void;
  onAutoAdvanceChange: (v: boolean) => void;
  onStepFramesChange: (n: number) => void;
  onStep: (direction: -1 | 1) => void;
  onRunExtract: () => void;
};

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs ${
        ok
          ? "border-emerald-300 bg-emerald-50 text-emerald-900"
          : "border-amber-300 bg-amber-50 text-amber-950"
      }`}
    >
      <span aria-hidden>{ok ? "●" : "○"}</span>
      {label}
    </span>
  );
}

export function CursorTab({
  videoSrc,
  screen,
  mode,
  currentTime,
  fps,
  stepFrames,
  label,
  ambiguous,
  autoAdvance,
  annotationCount,
  labelCounts,
  runDisabled,
  cursorRunning,
  cursorEvents,
  weights,
  onModeChange,
  onTimeUpdate,
  onMeta,
  onBbox,
  onLabelChange,
  onAmbiguousChange,
  onAutoAdvanceChange,
  onStepFramesChange,
  onStep,
  onRunExtract,
}: Props) {
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onModeChange("labels")}
          className={`rounded px-3 py-1.5 text-sm ${
            mode === "labels"
              ? "bg-[var(--ink)] text-[var(--paper)]"
              : "bg-[var(--wash)] text-[var(--ink)]"
          }`}
        >
          Labels
        </button>
        <button
          type="button"
          onClick={() => onModeChange("extract")}
          className={`rounded px-3 py-1.5 text-sm ${
            mode === "extract"
              ? "bg-[var(--ink)] text-[var(--paper)]"
              : "bg-[var(--wash)] text-[var(--ink)]"
          }`}
        >
          Extract
        </button>
      </div>

      {mode === "labels" && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_260px]">
          <VideoCanvas
            videoSrc={videoSrc}
            mode="bbox"
            roi={screen.roi}
            cropToRoi={screen.roi}
            onBbox={onBbox}
            currentTime={currentTime}
            fps={fps}
            onTimeUpdate={onTimeUpdate}
            onMeta={onMeta}
          />
          <aside className="space-y-4 rounded border border-[var(--line)] bg-[var(--wash)] p-4">
            <p className="text-sm text-[var(--muted)]">
              Draw a tight box to save. {annotationCount} sample(s) total.
            </p>
            <div className="grid grid-cols-2 gap-2">
              {LABEL_PRESETS.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => onLabelChange(preset)}
                  className={`rounded border px-2 py-1.5 text-left text-xs ${
                    label === preset
                      ? "border-[var(--accent)] bg-[var(--paper)] text-[var(--ink)]"
                      : "border-[var(--line)] bg-[var(--paper)] text-[var(--muted)]"
                  }`}
                >
                  <span className="block font-medium">{preset}</span>
                  <span className="font-mono">{labelCounts[preset] ?? 0}</span>
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => onStep(-1)}
                className="flex-1 rounded border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5 text-sm"
              >
                ← Prev
              </button>
              <button
                type="button"
                onClick={() => onStep(1)}
                className="flex-1 rounded border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5 text-sm"
              >
                Next →
              </button>
            </div>
            <label className="block text-sm">
              <span className="text-xs uppercase tracking-wide text-[var(--muted)]">
                Step (frames)
              </span>
              <input
                type="number"
                min={1}
                max={300}
                value={stepFrames}
                onChange={(event) => onStepFramesChange(Number(event.target.value))}
                className="mt-1 w-full rounded border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5"
              />
            </label>
            <LabelSearch
              value={label}
              onChange={onLabelChange}
              knownLabels={[...LABEL_PRESETS, ...Object.keys(labelCounts)]}
              counts={labelCounts}
            />
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={autoAdvance}
                onChange={(event) => onAutoAdvanceChange(event.target.checked)}
              />
              Auto-advance after save
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={ambiguous}
                onChange={(event) => onAmbiguousChange(event.target.checked)}
              />
              Ambiguous / multiple cursors
            </label>
            <p className="font-mono text-xs text-[var(--muted)]">
              frame {Math.round(currentTime * fps)} · {currentTime.toFixed(3)}s
            </p>
          </aside>
        </div>
      )}

      {mode === "extract" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-4 rounded border border-[var(--line)] bg-[var(--wash)] p-4">
            <div className="min-w-0 flex-1">
              <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
                Cursor extraction
              </p>
              <p className="mt-1 text-sm">
                Runs YOLO over the Crop ROI + time range only. Train weights first if missing.
              </p>
              {weights && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <StatusPill
                    ok={weights.found}
                    label={
                      weights.found
                        ? `Weights found · ${weights.path}`
                        : `Weights missing · ${weights.path}`
                    }
                  />
                </div>
              )}
            </div>
            <button
              type="button"
              disabled={runDisabled || cursorRunning || weights?.found === false}
              onClick={onRunExtract}
              className="rounded bg-[var(--ink)] px-4 py-2 text-sm font-medium text-[var(--paper)] disabled:opacity-60"
            >
              {cursorRunning ? "Running…" : "Run cursor extraction"}
            </button>
          </div>
          {cursorEvents.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">No cursor events yet.</p>
          ) : (
            <ul className="max-h-[480px] overflow-y-auto rounded border border-[var(--line)] bg-[var(--paper)] p-3">
              {cursorEvents.map((event, index) => (
                <li
                  key={`c-${event.t}-${index}`}
                  className="grid grid-cols-[88px_1fr] gap-2 border-b border-[var(--line)] py-2 font-mono text-xs last:border-0"
                >
                  <span className="text-[var(--accent)]">cursor</span>
                  <span>
                    t={formatTime(event.t)} · ({Number(event.x).toFixed(0)},{" "}
                    {Number(event.y).toFixed(0)}) · conf{" "}
                    {Number(event.confidence).toFixed(2)}
                    {event.click_candidate ? " · click?" : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
