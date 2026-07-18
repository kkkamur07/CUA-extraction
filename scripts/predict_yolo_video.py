"""Run the trained cursor detector over a video and render its predictions.

When ``--selection`` points at a Processing run's ``selection.json``, also writes
``cursor_events.jsonl`` (Raw event stream) into that run directory.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cursor.detector.cursor_events import DEFAULT_MODEL_PATH, extract_cursor_events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL_PATH,
    )
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path("runs/solidworks-tut/selection.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/predictions/solidworks-tut/cursor-detected.mp4"),
    )
    parser.add_argument(
        "--detections",
        type=Path,
        default=Path("artifacts/predictions/solidworks-tut/detections.jsonl"),
    )
    parser.add_argument("--imgsz", type=int, default=1024)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--full-video", action="store_true")
    args = parser.parse_args()

    selection_path = args.selection.resolve()
    if not selection_path.is_file():
        raise FileNotFoundError(f"Missing selection: {selection_path}")
    run_dir = selection_path.parent

    extract_cursor_events(
        run_dir,
        model_path=args.model,
        imgsz=args.imgsz,
        batch=args.batch,
        conf=args.conf,
        max_frames=args.max_frames,
        full_video=args.full_video,
        debug_video_path=args.output.resolve(),
        detections_path=args.detections.resolve(),
    )


if __name__ == "__main__":
    main()
