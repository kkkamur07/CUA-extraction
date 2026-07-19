"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";

import type { CropROI } from "@/lib/types";

type Mode = "roi" | "bbox";
type InteractionMode = "roi" | "mask";

type Props = {
  videoSrc: string;
  mode: Mode;
  roi: CropROI;
  onRoiChange?: (roi: CropROI) => void;
  onBbox?: (box: CropROI, patchDataUrl: string) => void;
  onMaskChange?: (box: CropROI) => void;
  interactionMode?: InteractionMode;
  overlays?: CropROI[];
  currentTime: number;
  /**
   * When set, frames are fetched by frame number (round(currentTime * fps))
   * through the same decoder used for training export, so the previewed
   * pixels match the trained pixels exactly.
   */
  fps?: number;
  onTimeUpdate: (time: number) => void;
  onMeta: (meta: {
    duration: number;
    width: number;
    height: number;
    fpsHint: number;
  }) => void;
  /** When mode=bbox, crop display to this ROI. */
  cropToRoi?: CropROI | null;
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function VideoCanvas({
  videoSrc,
  mode,
  roi,
  onRoiChange,
  onBbox,
  onMaskChange,
  interactionMode = "roi",
  overlays = [],
  currentTime,
  fps,
  onMeta,
  cropToRoi = null,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<ImageBitmap | null>(null);
  const naturalRef = useRef({ width: 0, height: 0 });
  const metaSentRef = useRef(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const dragRef = useRef<{ x: number; y: number } | null>(null);
  const draftRef = useRef<CropROI | null>(null);
  const [draft, setDraft] = useState<CropROI | null>(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const frame = frameRef.current;
    const { width: nw, height: nh } = naturalRef.current;
    if (!canvas || !frame || !nw || !nh) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (mode === "bbox" && cropToRoi) {
      canvas.width = cropToRoi.width;
      canvas.height = cropToRoi.height;
      ctx.drawImage(
        frame,
        cropToRoi.x,
        cropToRoi.y,
        cropToRoi.width,
        cropToRoi.height,
        0,
        0,
        cropToRoi.width,
        cropToRoi.height,
      );
    } else {
      canvas.width = nw;
      canvas.height = nh;
      ctx.drawImage(frame, 0, 0, nw, nh);
      const box = draft ?? roi;
      ctx.strokeStyle = "#e11d48";
      ctx.lineWidth = Math.max(2, Math.round(nw / 600));
      ctx.strokeRect(box.x, box.y, box.width, box.height);
      for (const overlay of overlays) {
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(overlay.x, overlay.y, overlay.width, overlay.height);
      }
    }

    if (mode === "bbox" && draft) {
      ctx.strokeStyle = "#e11d48";
      ctx.lineWidth = 2;
      ctx.strokeRect(draft.x, draft.y, draft.width, draft.height);
    }
    if (interactionMode === "mask" && draft) {
      ctx.strokeStyle = "#2563eb";
      ctx.lineWidth = 3;
      ctx.setLineDash([8, 5]);
      ctx.strokeRect(draft.x, draft.y, draft.width, draft.height);
      ctx.setLineDash([]);
    }
    setReady(true);
  }, [cropToRoi, draft, interactionMode, mode, overlays, roi]);

  useEffect(() => {
    draw();
  }, [draw]);

  useEffect(() => {
    metaSentRef.current = false;
    naturalRef.current = { width: 0, height: 0 };
    frameRef.current?.close();
    frameRef.current = null;
  }, [videoSrc]);

  const frameNumber =
    fps && fps > 0 ? Math.round(currentTime * fps) : null;

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    // Debounce scrubbing so we don't spawn a decoder on every slider tick.
    const timer = window.setTimeout(async () => {
      setReady(false);
      setError("");
      try {
        const url =
          frameNumber !== null
            ? `${videoSrc}/frame?frame=${frameNumber}`
            : `${videoSrc}/frame?t=${encodeURIComponent(String(currentTime))}`;
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok) {
          const body = (await res.json().catch(() => null)) as {
            error?: string;
          } | null;
          throw new Error(body?.error || `Frame request failed (${res.status})`);
        }
        const blob = await res.blob();
        if (cancelled) return;
        const bitmap = await createImageBitmap(blob);
        if (cancelled) {
          bitmap.close();
          return;
        }
        frameRef.current?.close();
        frameRef.current = bitmap;
        naturalRef.current = { width: bitmap.width, height: bitmap.height };
        if (!metaSentRef.current) {
          metaSentRef.current = true;
          onMeta({
            duration: 0,
            width: bitmap.width,
            height: bitmap.height,
            fpsHint: 30,
          });
        }
        draw();
      } catch (err) {
        if (cancelled || (err instanceof DOMException && err.name === "AbortError")) {
          return;
        }
        setReady(false);
        setError(err instanceof Error ? err.message : "Failed to decode frame");
      }
    }, 100);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      controller.abort();
    };
    // draw/onMeta intentionally omitted — load once per time/src; draw effect handles overlays.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoSrc, currentTime, frameNumber]);

  const pointFromEvent = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    // Avoid divide-by-zero before the first frame paints (canvas defaults to 300×150).
    const cssW = rect.width || 1;
    const cssH = rect.height || 1;
    const scaleX = (canvas.width || cssW) / cssW;
    const scaleY = (canvas.height || cssH) / cssH;
    return {
      x: clamp((event.clientX - rect.left) * scaleX, 0, canvas.width || cssW),
      y: clamp((event.clientY - rect.top) * scaleY, 0, canvas.height || cssH),
    };
  };

  const commitDraft = useCallback(() => {
    const box = draftRef.current;
    dragRef.current = null;
    draftRef.current = null;
    setDraft(null);
    if (!box || box.width < 2 || box.height < 2) return;
    if (interactionMode === "mask") {
      onMaskChange?.(box);
    } else if (mode === "roi") {
      onRoiChange?.(box);
    } else if (mode === "bbox" && onBbox && canvasRef.current) {
      const canvas = canvasRef.current;
      const patch = document.createElement("canvas");
      patch.width = box.width;
      patch.height = box.height;
      const ctx = patch.getContext("2d");
      if (ctx) {
        ctx.drawImage(
          canvas,
          box.x,
          box.y,
          box.width,
          box.height,
          0,
          0,
          box.width,
          box.height,
        );
        onBbox(box, patch.toDataURL("image/png"));
      }
    }
  }, [interactionMode, mode, onBbox, onMaskChange, onRoiChange]);

  const onPointerDown = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = pointFromEvent(event);
    dragRef.current = point;
    const next = { x: point.x, y: point.y, width: 0, height: 0 };
    draftRef.current = next;
    setDraft(next);
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!dragRef.current) return;
    const point = pointFromEvent(event);
    const left = Math.min(dragRef.current.x, point.x);
    const top = Math.min(dragRef.current.y, point.y);
    const width = Math.abs(point.x - dragRef.current.x);
    const height = Math.abs(point.y - dragRef.current.y);
    const next = {
      x: Math.round(left),
      y: Math.round(top),
      width: Math.round(width),
      height: Math.round(height),
    };
    draftRef.current = next;
    setDraft(next);
  };

  const onPointerUp = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    commitDraft();
  };

  return (
    <div className="relative space-y-2">
      <canvas
        ref={canvasRef}
        tabIndex={0}
        className="max-h-[70vh] w-full cursor-crosshair touch-none rounded border border-[var(--line)] bg-black outline-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      />
      {!ready && !error && (
        <p className="text-sm text-[var(--muted)]">Decoding video frame…</p>
      )}
      {error && <p className="text-sm text-rose-700">{error}</p>}
      <p className="text-sm text-[var(--muted)]">
        {interactionMode === "mask"
          ? "Drag on the frame to draw the selected white mask."
          : mode === "roi"
          ? "Drag on the frame to set the crop ROI."
          : "Drag a tight box around the cursor to save a label. Use ←/→ to step frames."}
      </p>
    </div>
  );
}
