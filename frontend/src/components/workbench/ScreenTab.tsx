"use client";

import { VideoCanvas } from "@/components/VideoCanvas";
import type { TrackSelection } from "@/lib/types";

type Props = {
  videoSrc: string;
  screen: TrackSelection;
  duration: number;
  currentTime: number;
  fps: number;
  saving: boolean;
  selectionDirty: boolean;
  onTimeUpdate: (t: number) => void;
  onMeta: (meta: { duration: number; width: number; height: number }) => void;
  onRoiChange: (roi: TrackSelection["roi"]) => void;
  onPatch: (patch: Partial<TrackSelection>) => void;
  onFpsChange: (fps: number) => void;
  onSave: () => void;
};

export function ScreenTab({
  videoSrc,
  screen,
  duration,
  currentTime,
  fps,
  saving,
  selectionDirty,
  onTimeUpdate,
  onMeta,
  onRoiChange,
  onPatch,
  onFpsChange,
  onSave,
}: Props) {
  return (
    <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_260px]">
      <VideoCanvas
        videoSrc={videoSrc}
        mode="roi"
        roi={screen.roi}
        onRoiChange={(roi) => onRoiChange(roi)}
        currentTime={currentTime}
        fps={fps}
        onTimeUpdate={onTimeUpdate}
        onMeta={onMeta}
      />
      <aside className="space-y-4 rounded border border-[var(--line)] bg-[var(--wash)] p-4">
        <p className="text-xs text-[var(--muted)]">
          Crop ROI + shared useful time range. Saving syncs start/end to the Keyboard track.
        </p>
        <div>
          <label className="text-xs uppercase tracking-wide text-[var(--muted)]">
            Crop ROI · preview (s)
          </label>
          <input
            type="range"
            min={0}
            max={Math.max(duration, currentTime, 1)}
            step={0.1}
            value={currentTime}
            onChange={(event) => {
              const value = Number(event.target.value);
              onTimeUpdate(value);
              onPatch({ preview_timestamp: value });
            }}
            className="mt-2 w-full"
          />
          <p className="mt-1 font-mono text-sm">{currentTime.toFixed(2)}s</p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm">
            <span className="text-xs uppercase tracking-wide text-[var(--muted)]">Start</span>
            <input
              type="number"
              min={0}
              max={duration}
              step={0.1}
              value={screen.start}
              onChange={(event) => onPatch({ start: Number(event.target.value) })}
              className="mt-1 w-full rounded border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5"
            />
          </label>
          <label className="text-sm">
            <span className="text-xs uppercase tracking-wide text-[var(--muted)]">End</span>
            <input
              type="number"
              min={0}
              max={duration}
              step={0.1}
              value={screen.end}
              onChange={(event) => onPatch({ end: Number(event.target.value) })}
              className="mt-1 w-full rounded border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5"
            />
          </label>
        </div>
        <div className="grid grid-cols-2 gap-2 font-mono text-xs text-[var(--muted)]">
          <span>x {screen.roi.x}</span>
          <span>y {screen.roi.y}</span>
          <span>w {screen.roi.width}</span>
          <span>h {screen.roi.height}</span>
        </div>
        <label className="block text-sm">
          <span className="text-xs uppercase tracking-wide text-[var(--muted)]">FPS</span>
          <input
            type="number"
            min={1}
            max={120}
            step={0.001}
            value={fps}
            onChange={(event) => onFpsChange(Number(event.target.value))}
            className="mt-1 w-full rounded border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5"
          />
        </label>
        <button
          type="button"
          disabled={saving}
          onClick={onSave}
          className="w-full rounded bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {saving ? "Saving…" : "Save Crop ROI + time range"}
        </button>
        {selectionDirty && (
          <p className="text-xs text-amber-800">Unsaved selection changes</p>
        )}
      </aside>
    </section>
  );
}
