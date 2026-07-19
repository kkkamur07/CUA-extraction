"use client";

import { useState } from "react";

import { VideoCanvas } from "@/components/VideoCanvas";
import type { CornerMasks, TrackSelection } from "@/lib/types";

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
  cornerMasks: CornerMasks;
  onCornerMasksChange: (masks: CornerMasks) => void;
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
  cornerMasks,
  onCornerMasksChange,
  onSave,
}: Props) {
  const [drawingMask, setDrawingMask] = useState<
    "bottom_left" | "bottom_right" | null
  >(null);

  const updateMask = (
    side: "bottom_left" | "bottom_right",
    key: keyof TrackSelection["roi"],
    value: number,
  ) => {
    onCornerMasksChange({
      ...cornerMasks,
      [side]: {
        ...cornerMasks[side],
        [key]: Math.max(0, Math.round(value) || 0),
      },
    });
  };

  const drawMask = (box: TrackSelection["roi"]) => {
    if (!drawingMask) return;
    const left = Math.max(0, Math.min(screen.roi.width, box.x - screen.roi.x));
    const top = Math.max(0, Math.min(screen.roi.height, box.y - screen.roi.y));
    const right = Math.max(
      left,
      Math.min(screen.roi.width, box.x + box.width - screen.roi.x),
    );
    const bottom = Math.max(
      top,
      Math.min(screen.roi.height, box.y + box.height - screen.roi.y),
    );
    onCornerMasksChange({
      ...cornerMasks,
      [drawingMask]: {
        x: left,
        y: top,
        width: right - left,
        height: bottom - top,
      },
    });
    setDrawingMask(null);
  };

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
        interactionMode={drawingMask ? "mask" : "roi"}
        onMaskChange={drawMask}
        overlays={[cornerMasks.bottom_left, cornerMasks.bottom_right].map((mask) => ({
          x: screen.roi.x + mask.x,
          y: screen.roi.y + mask.y,
          width: mask.width,
          height: mask.height,
        }))}
      />
      <aside className="space-y-4 rounded border border-[var(--line)] bg-[var(--wash)] p-4">
        <p className="text-xs text-[var(--muted)]">
          Set the screen crop and shared start/end range. Draw the two white
          boxes here; they are applied to the generated video.
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
        <div className="space-y-3 border-t border-[var(--line)] pt-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-[var(--muted)]">
              Final video white corner masks
            </p>
            <p className="mt-1 text-xs text-[var(--muted)]">
              Coordinates are relative to the saved screen crop. These rectangles
              are filled white in the final silent H.264 video.
            </p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {(
                [
                  ["bottom_left", "Draw bottom-left"],
                  ["bottom_right", "Draw bottom-right"],
                ] as const
              ).map(([side, label]) => (
                <button
                  key={side}
                  type="button"
                  onClick={() => setDrawingMask(side)}
                  className={`rounded border px-2 py-1.5 text-xs ${
                    drawingMask === side
                      ? "border-blue-600 bg-blue-50 text-blue-800"
                      : "border-[var(--line)] bg-[var(--paper)]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {drawingMask && (
              <p className="mt-2 text-xs text-blue-800">
                Drag a rectangle on the video. It will replace the selected mask.
              </p>
            )}
          </div>
          {(
            [
              ["bottom_left", "Bottom left"],
              ["bottom_right", "Bottom right"],
            ] as const
          ).map(([side, label]) => (
            <fieldset key={side} className="rounded border border-[var(--line)] p-2">
              <legend className="px-1 text-xs font-medium">{label}</legend>
              <div className="grid grid-cols-2 gap-2">
                {(["x", "y", "width", "height"] as const).map((key) => (
                  <label key={key} className="text-xs text-[var(--muted)]">
                    {key}
                    <input
                      type="number"
                      min={0}
                      step={1}
                      value={cornerMasks[side][key]}
                      onChange={(event) =>
                        updateMask(side, key, Number(event.target.value))
                      }
                      className="mt-1 w-full rounded border border-[var(--line)] bg-[var(--paper)] px-2 py-1 font-mono text-xs text-[var(--ink)]"
                    />
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
        </div>
        <button
          type="button"
          disabled={saving}
          onClick={onSave}
          className="w-full rounded bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {saving ? "Saving…" : "Save Crop ROI + masks + time range"}
        </button>
        {selectionDirty && (
          <p className="text-xs text-amber-800">Unsaved selection changes</p>
        )}
      </aside>
    </section>
  );
}
