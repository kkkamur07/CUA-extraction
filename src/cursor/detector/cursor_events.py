"""YOLO Cursor observation extraction for a Processing run.

Writes ``runs/<id>/cursor/cursor_events.jsonl`` — one Raw event JSON object per line.
Coordinates are **full-frame source** pixels (Crop ROI offset applied), not
Crop-ROI-relative.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
from ultralytics import YOLO

from ..workflow.models import CropROI, ProjectSelection
from ..workflow.workflow import CURSOR_EVENTS_FILENAME, load_project_selection

DEFAULT_MODEL_PATH = Path("artifacts/models/cursor/weights/best.pt")


def resolve_repo_path(path: Path, run_dir: Path) -> Path:
    """Resolve a path relative to the repository root when possible.

    If ``run_dir`` is ``.../runs/<id>``, relative paths resolve against the
    parent of ``runs/``. Otherwise they resolve against the current working
    directory.
    """
    path = Path(path)
    if path.is_absolute():
        return path
    run_dir = Path(run_dir).resolve()
    if run_dir.parent.name == "runs":
        return (run_dir.parent.parent / path).resolve()
    return (Path.cwd() / path).resolve()


def _resolve_model_path(model_path: Path | str | None, run_dir: Path) -> Path:
    raw = Path(model_path) if model_path is not None else DEFAULT_MODEL_PATH
    if raw.is_absolute():
        candidates = [raw]
    else:
        candidates = [resolve_repo_path(raw, run_dir)]
        cwd_candidate = (Path.cwd() / raw).resolve()
        if cwd_candidate not in candidates:
            candidates.append(cwd_candidate)
    resolved = next((path for path in candidates if path.is_file()), candidates[0])
    if not resolved.is_file():
        hint = DEFAULT_MODEL_PATH.as_posix()
        raise FileNotFoundError(
            f"Trained YOLO weights not found: {resolved}\n"
            f"Train a cursor detector first, e.g.:\n"
            f"  .venv/bin/python scripts/train_yolo.py "
            f"--selection runs/<id>/selection.json\n"
            f"Expected default weights at: {hint}"
        )
    return resolved


def _crop_roi_and_range(selection: ProjectSelection) -> tuple[CropROI, float, float]:
    """Crop ROI and useful time range from project selection (screen track)."""
    return selection.screen.roi, selection.screen.start, selection.screen.end


def extract_cursor_events(
    run_dir: Path | str,
    model_path: Path | str | None = None,
    *,
    imgsz: int = 1024,
    batch: int = 8,
    conf: float = 0.25,
    max_frames: int | None = None,
    full_video: bool = False,
    debug_video_path: Path | str | None = None,
    detections_path: Path | str | None = None,
) -> Path:
    """Run YOLO over the selection Crop ROI + time range; write cursor_events.jsonl.

    Each line is a Cursor Raw event::

        {"type": "cursor", "t": 1.23, "x": 100.0, "y": 200.0,
         "confidence": 0.9, "click_candidate": false}

    ``x`` / ``y`` are the detection box center in **full-frame source** pixels.

    Returns the path to ``cursor_events.jsonl``.
    """
    run_dir = Path(run_dir)
    selection = load_project_selection(run_dir)
    video_path = resolve_repo_path(Path(selection.video), run_dir)
    weights = _resolve_model_path(model_path, run_dir)

    roi, start_s, end_s = _crop_roi_and_range(selection)
    out_path = run_dir / CURSOR_EVENTS_FILENAME
    out_path.parent.mkdir(parents=True, exist_ok=True)

    video = cv2.VideoCapture(str(video_path))
    if not video.isOpened():
        raise FileNotFoundError(f"Could not open video: {video_path}")

    fps = float(video.get(cv2.CAP_PROP_FPS)) or float(selection.fps)
    width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))

    start_frame = 0 if full_video else int(round(start_s * fps))
    end_frame = total_frames if full_video else int(round(end_s * fps))
    end_frame = min(end_frame, total_frames)
    if max_frames is not None:
        end_frame = min(end_frame, start_frame + max_frames)
    video.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    writer = None
    debug_path = Path(debug_video_path) if debug_video_path else None
    if debug_path is not None:
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            str(debug_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            video.release()
            raise ValueError(f"Could not create output video: {debug_path}")

    det_path = Path(detections_path) if detections_path else None
    if det_path is not None:
        det_path.parent.mkdir(parents=True, exist_ok=True)

    import torch

    if torch.cuda.is_available():
        device: str | int = 0
    elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    model = YOLO(str(weights))

    processed = 0
    event_count = 0
    crops: list[Any] = []
    frames: list[Any] = []
    frame_numbers: list[int] = []

    out_path.parent.mkdir(parents=True, exist_ok=True)

    def flush_batch(
        events_file: Any,
        detections_file: Any | None,
    ) -> None:
        nonlocal processed, event_count
        if not frames:
            return
        results = model.predict(
            source=crops,
            imgsz=imgsz,
            batch=len(crops),
            conf=conf,
            device=device,
            verbose=False,
        )
        for frame, frame_number, result in zip(frames, frame_numbers, results):
            t = frame_number / fps
            boxes = result.boxes
            if boxes is not None:
                for box, confidence in zip(
                    boxes.xyxy.cpu().tolist(),
                    boxes.conf.cpu().tolist(),
                ):
                    left, top, right, bottom = box
                    # Map Crop-ROI-relative box → full-frame source pixels.
                    left += roi.x
                    right += roi.x
                    top += roi.y
                    bottom += roi.y
                    left_i = max(0, min(int(round(left)), width - 1))
                    top_i = max(0, min(int(round(top)), height - 1))
                    right_i = max(left_i + 1, min(int(round(right)), width - 1))
                    bottom_i = max(top_i + 1, min(int(round(bottom)), height - 1))

                    cx = (left + right) / 2.0
                    cy = (top + bottom) / 2.0
                    cx = max(0.0, min(cx, float(width - 1)))
                    cy = max(0.0, min(cy, float(height - 1)))

                    events_file.write(
                        json.dumps(
                            {
                                "type": "cursor",
                                "t": t,
                                "x": cx,
                                "y": cy,
                                "confidence": float(confidence),
                                "click_candidate": False,
                            }
                        )
                        + "\n"
                    )
                    event_count += 1

                    if detections_file is not None:
                        detections_file.write(
                            json.dumps(
                                {
                                    "frame_number": frame_number,
                                    "timestamp_seconds": t,
                                    "x": left_i,
                                    "y": top_i,
                                    "width": right_i - left_i,
                                    "height": bottom_i - top_i,
                                    "confidence": float(confidence),
                                    "label": "cursor",
                                }
                            )
                            + "\n"
                        )

                    if writer is not None:
                        cv2.rectangle(
                            frame,
                            (left_i, top_i),
                            (right_i, bottom_i),
                            (0, 255, 0),
                            2,
                        )
                        cv2.putText(
                            frame,
                            f"cursor {confidence:.2f}",
                            (left_i, max(20, top_i - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 255, 0),
                            2,
                            cv2.LINE_AA,
                        )
            if writer is not None:
                writer.write(frame)
            processed += 1
        crops.clear()
        frames.clear()
        frame_numbers.clear()

    try:
        with out_path.open("w", encoding="utf-8") as events_file:
            det_ctx = (
                det_path.open("w", encoding="utf-8") if det_path is not None else None
            )
            try:
                while start_frame + processed < end_frame:
                    ok, frame = video.read()
                    if not ok:
                        break
                    frame_number = start_frame + processed + len(frames)
                    cropped = frame[
                        roi.y : roi.y + roi.height,
                        roi.x : roi.x + roi.width,
                    ]
                    crops.append(cropped)
                    frames.append(frame)
                    frame_numbers.append(frame_number)
                    if len(crops) >= batch:
                        flush_batch(events_file, det_ctx)
                flush_batch(events_file, det_ctx)
            finally:
                if det_ctx is not None:
                    det_ctx.close()
    finally:
        video.release()
        if writer is not None:
            writer.release()

    print(f"Processed {processed} frames on {device}")
    print(f"Cursor events: {event_count}")
    print(f"Cursor events JSONL: {out_path}")
    if debug_path is not None:
        print(f"Annotated video: {debug_path}")
    if det_path is not None:
        print(f"Detections JSONL: {det_path}")
    return out_path
