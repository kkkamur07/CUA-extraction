"use client";

import { useEffect, useRef } from "react";

import type { KeystrokeRawEvent } from "@/lib/types";

type Props = {
  events: KeystrokeRawEvent[];
  startT: number;
  endT: number;
  onSelect?: (event: KeystrokeRawEvent, index: number) => void;
};

function formatTime(t: number): string {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

/** Keyboard-detector-style density timeline: one row per key, bars for press–release. */
export function KeystrokeDensityTimeline({ events, startT, endT, onSelect }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const keys = [...new Set(events.map((e) => e.key))];
    const rowH = 26;
    const pad = 90;
    const padT = 26;
    const cssW = canvas.clientWidth || 640;
    canvas.width = cssW * 2;
    canvas.height = padT + Math.max(1, keys.length) * rowH + 30;
    canvas.style.height = `${canvas.height / 2}px`;

    const t0 = startT;
    const t1 = endT > startT ? endT : startT + 1;
    const X = (t: number) => pad + ((t - t0) / (t1 - t0 || 1)) * (canvas.width - pad - 20);

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = "19px sans-serif";

    if (keys.length === 0) {
      ctx.fillStyle = "#6b6458";
      ctx.fillText("No keystrokes yet", pad, padT + 20);
      return;
    }

    keys.forEach((k, i) => {
      const y = padT + i * rowH;
      ctx.fillStyle = i % 2 ? "#ebe4d6" : "#f3efe6";
      ctx.fillRect(pad, y, canvas.width - pad - 20, rowH);
      ctx.fillStyle = "#6b6458";
      ctx.fillText(k, 8, y + rowH - 8, pad - 14);
    });

    ctx.fillStyle = "#0f6a5c";
    events.forEach((e) => {
      const i = keys.indexOf(e.key);
      if (i < 0) return;
      const x0 = X(e.press_t);
      const x1 = X(e.release_t);
      ctx.fillRect(x0, padT + i * rowH + 4, Math.max(3, x1 - x0), rowH - 8);
    });

    ctx.fillStyle = "#6b6458";
    for (let g = 0; g <= 6; g++) {
      const t = t0 + ((t1 - t0) * g) / 6;
      ctx.fillText(formatTime(t), X(t) - 30, canvas.height - 6);
    }
  }, [events, startT, endT]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full rounded border border-[var(--line)] bg-[var(--wash)]"
      role="img"
      aria-label="Keystroke density timeline"
      onClick={(event) => {
        if (!onSelect || events.length === 0) return;
        const canvas = canvasRef.current;
        if (!canvas) return;
        const rect = canvas.getBoundingClientRect();
        const ratio = canvas.width / rect.width;
        const x = (event.clientX - rect.left) * ratio;
        const pad = 90;
        const t0 = startT;
        const t1 = endT > startT ? endT : startT + 1;
        const t = t0 + ((x - pad) / (canvas.width - pad - 20 || 1)) * (t1 - t0);
        let best = 0;
        let bestDist = Infinity;
        events.forEach((e, i) => {
          const mid = (e.press_t + e.release_t) / 2;
          const d = Math.abs(mid - t);
          if (d < bestDist) {
            bestDist = d;
            best = i;
          }
        });
        onSelect(events[best], best);
      }}
    />
  );
}
