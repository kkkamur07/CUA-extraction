"""Run the trained cursor detector over a video and render its predictions.

When ``--selection`` points at a Processing run's ``selection.json``, also writes
``cursor_events.jsonl`` (Raw event stream) into that run directory.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from cursor.detector.cursor_events import (
    DEFAULT_MODEL_PATH,
    extract_cursor_events,
    resolve_repo_path,
)
from cursor.workflow.workflow import load_project_selection


def encode_hevc(
    input_video: Path,
    source_video: Path,
    output_video: Path,
    *,
    crf: int,
    preset: str,
) -> None:
    """Encode an annotated intermediate as QuickTime-friendly HEVC MP4."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("HEVC output requires ffmpeg on PATH")

    output_video.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-i",
        str(input_video),
        "-i",
        str(source_video),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-c:v",
        "libx265",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-tag:v",
        "hvc1",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        str(output_video),
    ]
    subprocess.run(command, check=True)


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
    parser.add_argument(
        "--hevc",
        action="store_true",
        help="Encode the annotated video as QuickTime-friendly HEVC/H.265 MP4",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=28,
        help="HEVC quality setting; lower is higher quality and larger output",
    )
    parser.add_argument(
        "--preset",
        default="medium",
        choices=("fast", "medium", "slow", "slower"),
        help="x265 speed/compression preset used with --hevc",
    )
    args = parser.parse_args()

    selection_path = args.selection.resolve()
    if not selection_path.is_file():
        raise FileNotFoundError(f"Missing selection: {selection_path}")
    run_dir = selection_path.parent
    output_path = args.output.resolve()
    temporary_video: Path | None = None

    if args.hevc:
        run_dir.mkdir(parents=True, exist_ok=True)
        selection = load_project_selection(run_dir)
        source_video = resolve_repo_path(Path(selection.video), run_dir)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{output_path.stem}-",
            suffix=".mp4",
            dir=output_path.parent,
        )
        os.close(fd)
        temporary_video = Path(temporary_name)
        temporary_video.unlink()
        debug_video_path = temporary_video
    else:
        debug_video_path = output_path

    try:
        extract_cursor_events(
            run_dir,
            model_path=args.model,
            imgsz=args.imgsz,
            batch=args.batch,
            conf=args.conf,
            max_frames=args.max_frames,
            full_video=args.full_video,
            debug_video_path=debug_video_path,
            detections_path=args.detections.resolve(),
        )
        if args.hevc:
            encode_hevc(
                debug_video_path,
                source_video,
                output_path,
                crf=args.crf,
                preset=args.preset,
            )
            print(f"HEVC video: {output_path}")
    finally:
        if temporary_video is not None:
            temporary_video.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
