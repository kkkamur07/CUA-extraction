"""Render a publishable cropped tutorial video from a Processing selection.

The renderer:

* keeps the saved screen ROI and selected time range;
* masks the part of the keyboard ROI visible in the screen crop;
* masks the elapsed-time panel in the lower-right corner;
* uses the white corner masks saved by the frontend; and
* writes a silent H.264/AVC MP4 for broad QuickTime compatibility.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from cursor.detector.cursor_events import resolve_repo_path
from cursor.workflow.models import CornerMasks, ProjectSelection
from cursor.workflow.workflow import load_project_selection


@dataclass(frozen=True)
class MaskRect:
    x: int
    y: int
    width: int
    height: int

    def clipped(self, width: int, height: int) -> "MaskRect":
        left = max(0, min(self.x, width))
        top = max(0, min(self.y, height))
        right = max(left, min(self.x + self.width, width))
        bottom = max(top, min(self.y + self.height, height))
        return MaskRect(left, top, right - left, bottom - top)


def _parse_rect(value: str) -> MaskRect:
    try:
        x, y, width, height = (int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Expected X,Y,WIDTH,HEIGHT, got {value!r}"
        ) from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError(f"Mask dimensions must be positive: {value!r}")
    return MaskRect(x, y, width, height)


def _ffmpeg_filter(
    selection: ProjectSelection,
    masks: list[MaskRect],
) -> str:
    screen = selection.screen.roi
    video_parts = [f"crop={screen.width}:{screen.height}:{screen.x}:{screen.y}"]
    video_parts.extend(
        f"drawbox=x={mask.x}:y={mask.y}:w={mask.width}:h={mask.height}:"
        "color=white@1:t=fill"
        for mask in masks
    )
    video_parts.extend(
        [
            f"trim=start={selection.screen.start:.6f}:end={selection.screen.end:.6f}",
            "setpts=PTS-STARTPTS",
        ]
    )
    return ",".join(video_parts)


def _selection_masks(corner_masks: CornerMasks) -> list[MaskRect]:
    return [
        MaskRect(**asdict(corner_masks.bottom_left)),
        MaskRect(**asdict(corner_masks.bottom_right)),
    ]


def render_final_video(
    run_dir: Path | str,
    *,
    output: Path | str | None = None,
    masks: list[MaskRect] | None = None,
) -> tuple[Path, Path]:
    """Render the final MP4 and a JSON manifest describing the render."""
    run_dir = Path(run_dir)
    selection = load_project_selection(run_dir)
    video_path = resolve_repo_path(Path(selection.video), run_dir)
    if not video_path.is_file():
        raise FileNotFoundError(f"Source video not found: {video_path}")

    screen = selection.screen.roi
    output_path = (
        Path(output)
        if output
        else run_dir / "final_video.mp4"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path = output_path.with_suffix(".json")

    render_masks = masks if masks is not None else _selection_masks(selection.corner_masks)
    render_masks = [mask.clipped(screen.width, screen.height) for mask in render_masks]
    render_masks = [mask for mask in render_masks if mask.width and mask.height]

    video_filter = _ffmpeg_filter(selection, render_masks)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to render the final video")

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        video_filter,
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-tag:v",
        "avc1",
        "-movflags",
        "+faststart",
        "-y",
        str(output_path),
    ]
    subprocess.run(command, check=True)

    manifest = {
        "source": str(video_path),
        "output": str(output_path),
        "selection": {
            "start": selection.screen.start,
            "end": selection.screen.end,
            "screen_roi": asdict(screen),
        },
        "masks": [asdict(mask) for mask in render_masks],
        "audio": False,
        "codec": "H.264/AVC (libx264)",
        "crf": 23,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path, manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path("runs/solidworks-tut/selection.json"),
        help="Processing run selection.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output MP4 (default: runs/<id>/final_video.mp4)",
    )
    parser.add_argument(
        "--mask",
        type=_parse_rect,
        action="append",
        default=None,
        metavar="X,Y,WIDTH,HEIGHT",
        help="Override default white masks in screen-crop coordinates",
    )
    args = parser.parse_args()

    output_path, manifest_path = render_final_video(
        args.selection.parent,
        output=args.output,
        masks=args.mask,
    )
    print(f"Final video: {output_path}")
    print(f"Render manifest: {manifest_path}")


if __name__ == "__main__":
    main()
