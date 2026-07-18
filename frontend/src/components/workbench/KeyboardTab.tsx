"use client";

import { KeystrokeDensityTimeline } from "@/components/KeystrokeDensityTimeline";
import { VideoCanvas } from "@/components/VideoCanvas";
import type { KeystrokeRawEvent, TrackSelection } from "@/lib/types";

import { formatTime } from "./format";
import type { KeystrokeJob } from "./types";

type Props = {
  videoSrc: string;
  keyboard: TrackSelection;
  duration: number;
  currentTime: number;
  fps: number;
  saving: boolean;
  runDisabled: boolean;
  kbRunning: boolean;
  kbJob: KeystrokeJob | null;
  keystrokes: KeystrokeRawEvent[];
  kbSelected: number | null;
  onTimeUpdate: (t: number) => void;
  onMeta: (meta: { duration: number; width: number; height: number }) => void;
  onRoiChange: (roi: TrackSelection["roi"]) => void;
  onPatch: (patch: Partial<TrackSelection>) => void;
  onSave: () => void;
  onRun: () => void;
  onSelectEvent: (event: KeystrokeRawEvent, index: number) => void;
};

export function KeyboardTab({
  videoSrc,
  keyboard,
  duration,
  currentTime,
  fps,
  saving,
  runDisabled,
  kbRunning,
  kbJob,
  keystrokes,
  kbSelected,
  onTimeUpdate,
  onMeta,
  onRoiChange,
  onPatch,
  onSave,
  onRun,
  onSelectEvent,
}: Props) {
  const kbProgress = Math.round((kbJob?.progress ?? 0) * 100);

  return (
    <section className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_260px]">
        <VideoCanvas
          videoSrc={videoSrc}
          mode="roi"
          roi={keyboard.roi}
          onRoiChange={onRoiChange}
          currentTime={currentTime}
          fps={fps}
          onTimeUpdate={onTimeUpdate}
          onMeta={onMeta}
        />
        <aside className="space-y-4 rounded border border-[var(--line)] bg-[var(--wash)] p-4">
          <p className="text-xs text-[var(--muted)]">
            Keyboard ROI only. Uses the shared time range from Screen extraction.
          </p>
          <div>
            <label className="text-xs uppercase tracking-wide text-[var(--muted)]">
              Crop ROI · preview (s)
            </label>
            <input
              type="range"
              min={0}
              max={Math.max(duration || 0, currentTime, 1)}
              step={0.1}
              value={Number.isFinite(currentTime) ? currentTime : 0}
              onChange={(event) => {
                const value = Number(event.target.value);
                onTimeUpdate(value);
                onPatch({ preview_timestamp: value });
              }}
              className="mt-2 w-full accent-[var(--accent)]"
            />
            <p className="mt-1 font-mono text-sm">{currentTime.toFixed(2)}s</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {(
              [
                ["x", keyboard.roi.x],
                ["y", keyboard.roi.y],
                ["w", keyboard.roi.width],
                ["h", keyboard.roi.height],
              ] as const
            ).map(([key, value]) => (
              <label key={key} className="text-sm">
                <span className="text-xs uppercase tracking-wide text-[var(--muted)]">
                  {key}
                </span>
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={value}
                  onChange={(event) => {
                    const n = Math.max(0, Math.round(Number(event.target.value) || 0));
                    const roi = { ...keyboard.roi };
                    if (key === "x") roi.x = n;
                    else if (key === "y") roi.y = n;
                    else if (key === "w") roi.width = Math.max(1, n);
                    else roi.height = Math.max(1, n);
                    onRoiChange(roi);
                  }}
                  className="mt-1 w-full rounded border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5 font-mono text-sm"
                />
              </label>
            ))}
          </div>
          <p className="font-mono text-xs text-[var(--muted)]">
            range {keyboard.start.toFixed(1)}s – {keyboard.end.toFixed(1)}s
          </p>
          <button
            type="button"
            disabled={saving}
            onClick={onSave}
            className="w-full rounded border border-[var(--line)] bg-[var(--paper)] px-3 py-2 text-sm disabled:opacity-60"
          >
            {saving ? "Saving…" : "Save Keyboard ROI"}
          </button>
          <button
            type="button"
            disabled={runDisabled || kbRunning}
            onClick={onRun}
            className="w-full rounded bg-[var(--ink)] px-3 py-2 text-sm font-medium text-[var(--paper)] disabled:opacity-60"
          >
            {kbRunning ? "Extracting…" : "Run keyboard extraction"}
          </button>
          {(kbRunning || kbJob) && (
            <div className="space-y-2">
              <div className="h-2 overflow-hidden rounded bg-[var(--line)]">
                <div
                  className="h-full bg-[var(--accent)] transition-[width] duration-300"
                  style={{ width: `${kbJob?.state === "done" ? 100 : kbProgress}%` }}
                />
              </div>
              <p className="text-xs text-[var(--muted)]">
                {kbJob?.message || (kbRunning ? `Extracting… ${kbProgress}%` : "")}
              </p>
            </div>
          )}
        </aside>
      </div>

      {keystrokes.length > 0 && (
        <div className="space-y-4 rounded border border-[var(--line)] bg-[var(--paper)] p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-[family-name:var(--font-display)] text-xl tracking-tight">
              Keystroke results
            </h2>
            <p className="text-xs text-[var(--muted)]">
              {keystrokes.length} events · density by key
            </p>
          </div>
          <KeystrokeDensityTimeline
            events={keystrokes}
            startT={keyboard.start}
            endT={keyboard.end}
            onSelect={onSelectEvent}
          />
          <div className="max-h-[360px] overflow-y-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-[var(--paper)] text-xs uppercase tracking-wide text-[var(--muted)]">
                <tr>
                  <th className="py-2 pr-2">#</th>
                  <th className="py-2 pr-2">Key</th>
                  <th className="py-2 pr-2">Press</th>
                  <th className="py-2 pr-2">Release</th>
                  <th className="py-2">ms</th>
                </tr>
              </thead>
              <tbody className="font-mono text-xs">
                {keystrokes.map((e, i) => (
                  <tr
                    key={`${e.key}-${e.press_t}-${i}`}
                    className={`cursor-pointer border-t border-[var(--line)] ${
                      kbSelected === i ? "bg-[var(--wash)]" : ""
                    }`}
                    onClick={() => onSelectEvent(e, i)}
                  >
                    <td className="py-1.5 pr-2">{i + 1}</td>
                    <td className="py-1.5 pr-2 font-sans font-medium">{e.key}</td>
                    <td className="py-1.5 pr-2">{formatTime(e.press_t)}</td>
                    <td className="py-1.5 pr-2">
                      {formatTime(e.release_t)}
                      {e.clipped ? " ⚠" : ""}
                    </td>
                    <td className="py-1.5">
                      {Math.round((e.release_t - e.press_t) * 1000)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
