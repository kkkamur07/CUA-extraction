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

type Props = {
  videoSrc: string;
  mode: Mode;
  roi: CropROI;
  onRoiChange?: (roi: CropROI) => void;
  onBbox?: (box: CropROI, patchDataUrl: string) => void;
  currentTime: number;
  onTimeUpdate: (time: number) => void;
  onMeta: (meta: { duration: number; width: number; height: number; fpsHint: number }) => void;
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
  currentTime,
  onTimeUpdate,
  onMeta,
  cropToRoi = null,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [natural, setNatural] = useState({ width: 0, height: 0 });
  const dragRef = useRef<{ x: number; y: number } | null>(null);
  const [draft, setDraft] = useState<CropROI | null>(null);

  const draw = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !natural.width) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (mode === "bbox" && cropToRoi) {
      canvas.width = cropToRoi.width;
      canvas.height = cropToRoi.height;
      ctx.drawImage(
        video,
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
      canvas.width = natural.width;
      canvas.height = natural.height;
      ctx.drawImage(video, 0, 0, natural.width, natural.height);
      const box = draft ?? roi;
      ctx.strokeStyle = "#e11d48";
      ctx.lineWidth = Math.max(2, Math.round(natural.width / 600));
      ctx.strokeRect(box.x, box.y, box.width, box.height);
    }

    if (mode === "bbox" && draft) {
      ctx.strokeStyle = "#e11d48";
      ctx.lineWidth = 2;
      ctx.strokeRect(draft.x, draft.y, draft.width, draft.height);
    }
  }, [cropToRoi, draft, mode, natural.height, natural.width, roi]);

  useEffect(() => {
    draw();
  }, [draw, currentTime]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    if (Math.abs(video.currentTime - currentTime) > 0.04) {
      video.currentTime = currentTime;
    }
  }, [currentTime]);

  const pointFromEvent = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
      x: clamp((event.clientX - rect.left) * scaleX, 0, canvas.width),
      y: clamp((event.clientY - rect.top) * scaleY, 0, canvas.height),
    };
  };

  const onPointerDown = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = pointFromEvent(event);
    dragRef.current = point;
    setDraft({ x: point.x, y: point.y, width: 0, height: 0 });
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!dragRef.current) return;
    const point = pointFromEvent(event);
    const left = Math.min(dragRef.current.x, point.x);
    const top = Math.min(dragRef.current.y, point.y);
    const width = Math.abs(point.x - dragRef.current.x);
    const height = Math.abs(point.y - dragRef.current.y);
    setDraft({
      x: Math.round(left),
      y: Math.round(top),
      width: Math.round(width),
      height: Math.round(height),
    });
  };

  const onPointerUp = () => {
    if (!draft || draft.width < 2 || draft.height < 2) {
      dragRef.current = null;
      setDraft(null);
      return;
    }
    if (mode === "roi") {
      onRoiChange?.(draft);
    } else if (mode === "bbox" && onBbox && canvasRef.current) {
      const canvas = canvasRef.current;
      const patch = document.createElement("canvas");
      patch.width = draft.width;
      patch.height = draft.height;
      const ctx = patch.getContext("2d");
      if (ctx) {
        ctx.drawImage(
          canvas,
          draft.x,
          draft.y,
          draft.width,
          draft.height,
          0,
          0,
          draft.width,
          draft.height,
        );
        onBbox(draft, patch.toDataURL("image/png"));
      }
    }
    dragRef.current = null;
    setDraft(null);
  };

  return (
    <div className="space-y-2">
      <video
        ref={videoRef}
        src={videoSrc}
        className="hidden"
        preload="auto"
        onLoadedMetadata={(event) => {
          const video = event.currentTarget;
          const width = video.videoWidth;
          const height = video.videoHeight;
          setNatural({ width, height });
          onMeta({
            duration: video.duration || 0,
            width,
            height,
            fpsHint: 30,
          });
          draw();
        }}
        onSeeked={draw}
        onTimeUpdate={(event) => onTimeUpdate(event.currentTarget.currentTime)}
      />
      <canvas
        ref={canvasRef}
        tabIndex={0}
        className="max-h-[70vh] w-full cursor-crosshair rounded border border-[var(--line)] bg-black outline-none"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      />
      <p className="text-sm text-[var(--muted)]">
        {mode === "roi"
          ? "Drag on the frame to set the crop ROI."
          : "Drag a tight box around the cursor to save a label. Use ←/→ to step frames."}
      </p>
    </div>
  );
}
