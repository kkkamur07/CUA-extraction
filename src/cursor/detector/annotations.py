"""Persistence for manually drawn cursor annotations."""

from __future__ import annotations

import json
import re
from pathlib import Path

import cv2

from ..workflow.models import CropROI
from .processor import read_frame


def save_cursor_annotation(
    video_path: str,
    roi: CropROI,
    fps: float,
    frame_number: int,
    box: dict[str, int],
    label: str,
    output_dir: Path,
    ambiguous: bool = False,
) -> Path:
    """Save a cursor patch and its annotation record."""
    video = cv2.VideoCapture(video_path)
    frame = read_frame(video, frame_number)
    video.release()

    if frame is None:
        raise ValueError(f"Could not read frame {frame_number}")

    cropped = frame[roi.y : roi.y + roi.height, roi.x : roi.x + roi.width]
    left = max(0, box["x"])
    top = max(0, box["y"])
    right = min(cropped.shape[1], left + box["width"])
    bottom = min(cropped.shape[0], top + box["height"])
    patch = cropped[top:bottom, left:right]
    
    if patch.size == 0:
        raise ValueError("The selected bounding box is empty")

    safe_label = re.sub(r"[^a-z0-9_-]+", "_", label.lower()).strip("_")
    timestamp = frame_number / fps
    template_dir = output_dir / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path = template_dir / (
        f"cursor-{safe_label}-frame-{frame_number:08d}-t-{timestamp:.3f}.png"
    )
    cv2.imwrite(str(template_path), patch)

    record = {
        "label": label.strip(),
        "frame_number": frame_number,
        "timestamp_seconds": timestamp,
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
        "center_x": left + (right - left) // 2,
        "center_y": top + (bottom - top) // 2,
        "ambiguous": ambiguous,
        "path": str(template_path),
    }
    manifest_path = template_dir / "templates.jsonl"
    with manifest_path.open("a", encoding="utf-8") as manifest:
        manifest.write(json.dumps(record) + "\n")
    return template_path
