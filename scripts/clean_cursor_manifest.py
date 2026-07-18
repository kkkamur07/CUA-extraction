"""Clean the cursor annotation manifest against the actual training frames.

Fixes the two data problems that poison YOLO training:

1. Misaligned boxes — annotations drawn on a preview frame that differed from
   the frame used at training time. Each saved patch is template-matched
   against the real (OpenCV-decoded) frame; boxes are snapped to the best
   match, and rows whose patch cannot be located confidently are moved to a
   sidecar ``templates.review.jsonl`` for manual re-annotation.
2. Duplicate boxes — frames annotated twice with overlapping boxes for the
   same cursor. Only the best-aligned (newest on ties) box per cursor is kept.

The original manifest is backed up as ``templates.jsonl.bak-<timestamp>``.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np

SEARCH_MARGIN_PX = 48
# Patches saved through the browser canvas are double-JPEG-compressed, so
# absolute match scores run low even when placement is perfect. Placement is
# therefore judged primarily by the offset of the best match: an in-place match
# is trusted at any score, while relocating a box requires a confident match.
KEEP_OFFSET_PX = 3
SNAP_SCORE = 0.55
MAX_SNAP_PX = 40


def load_rows(manifest_path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def resolve_video_path(selection_path: Path) -> tuple[Path, dict[str, int]]:
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    video_path = Path(selection["video"])
    if not video_path.is_absolute():
        video_path = selection_path.parent.parent.parent / video_path
    return video_path, selection["roi"]


def read_roi_frame(
    video: cv2.VideoCapture,
    frame_number: int,
    roi: dict[str, int],
) -> np.ndarray | None:
    video.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ok, frame = video.read()
    if not ok:
        return None
    return frame[
        roi["y"] : roi["y"] + roi["height"],
        roi["x"] : roi["x"] + roi["width"],
    ]


def match_patch(
    roi_frame: np.ndarray,
    patch: np.ndarray,
    x: int,
    y: int,
    margin: int = SEARCH_MARGIN_PX,
) -> tuple[int, int, float] | None:
    """Best (dx, dy, score) for the patch near its annotated position."""
    patch_h, patch_w = patch.shape[:2]
    frame_h, frame_w = roi_frame.shape[:2]
    x0 = max(0, x - margin)
    y0 = max(0, y - margin)
    x1 = min(frame_w, x + patch_w + margin)
    y1 = min(frame_h, y + patch_h + margin)
    window = roi_frame[y0:y1, x0:x1]
    if window.shape[0] < patch_h or window.shape[1] < patch_w:
        return None
    result = cv2.matchTemplate(window, patch, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(result)
    return x0 + loc[0] - x, y0 + loc[1] - y, float(score)


def check_row(
    row: dict[str, Any],
    video: cv2.VideoCapture,
    roi: dict[str, int],
    repo_root: Path,
    frame_cache: dict[int, np.ndarray | None],
) -> tuple[int, int, float] | None:
    """Template-match a manifest row's patch against its training frame."""
    patch_path = Path(row["path"])
    if not patch_path.is_absolute():
        patch_path = repo_root / patch_path
    patch = cv2.imread(str(patch_path))
    if patch is None:
        return None
    frame_number = row["frame_number"]
    if frame_number not in frame_cache:
        frame_cache[frame_number] = read_roi_frame(video, frame_number, roi)
    roi_frame = frame_cache[frame_number]
    if roi_frame is None:
        return None
    return match_patch(roi_frame, patch, int(row["x"]), int(row["y"]))


def boxes_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ax0, ay0 = a["x"], a["y"]
    ax1, ay1 = ax0 + a["width"], ay0 + a["height"]
    bx0, by0 = b["x"], b["y"]
    bx1, by1 = bx0 + b["width"], by0 + b["height"]
    inter_w = max(0, min(ax1, bx1) - max(ax0, bx0))
    inter_h = max(0, min(ay1, by1) - max(ay0, by0))
    inter = inter_w * inter_h
    if inter == 0:
        return False
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union > 0.25


def clean(
    manifest_path: Path,
    selection_path: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    repo_root = selection_path.parent.parent.parent
    video_path, roi = resolve_video_path(selection_path)
    video = cv2.VideoCapture(str(video_path))
    if not video.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    rows = load_rows(manifest_path)
    frame_cache: dict[int, np.ndarray | None] = {}
    snapped: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    scored: list[tuple[dict[str, Any], float, int]] = []  # (row, score, order)

    try:
        for order, row in enumerate(rows):
            result = check_row(row, video, roi, repo_root, frame_cache)
            if result is None:
                row["review_reason"] = "patch or frame unreadable"
                review.append(row)
                continue
            dx, dy, score = result
            offset = max(abs(dx), abs(dy))
            if offset > KEEP_OFFSET_PX:
                if score < SNAP_SCORE or offset > MAX_SNAP_PX:
                    row["review_reason"] = (
                        f"patch not found at annotation "
                        f"(best match dx={dx} dy={dy} score={score:.2f})"
                    )
                    review.append(row)
                    continue
                new_x = row["x"] + dx
                new_y = row["y"] + dy
                if (
                    0 <= new_x
                    and 0 <= new_y
                    and new_x + row["width"] <= roi["width"]
                    and new_y + row["height"] <= roi["height"]
                ):
                    row["x"] = new_x
                    row["y"] = new_y
                    row["center_x"] = new_x + row["width"] // 2
                    row["center_y"] = new_y + row["height"] // 2
                    snapped.append(
                        {"frame_number": row["frame_number"], "dx": dx, "dy": dy}
                    )
                else:
                    row["review_reason"] = "snapped box would leave the ROI"
                    review.append(row)
                    continue
            scored.append((row, score, order))
    finally:
        video.release()

    # One box per cursor: within each frame, drop overlapping boxes, keeping
    # the clearly better template match, or the newest annotation when close.
    kept: list[tuple[dict[str, Any], float, int]] = []
    deduped: list[dict[str, Any]] = []
    by_frame: dict[int, list[tuple[dict[str, Any], float, int]]] = {}
    for entry in scored:
        by_frame.setdefault(entry[0]["frame_number"], []).append(entry)
    for frame_number in sorted(by_frame):
        entries = sorted(
            by_frame[frame_number], key=lambda e: (-round(e[1], 1), -e[2])
        )
        chosen: list[tuple[dict[str, Any], float, int]] = []
        for entry in entries:
            if any(boxes_overlap(entry[0], other[0]) for other in chosen):
                deduped.append(entry[0])
            else:
                chosen.append(entry)
        kept.extend(chosen)
    kept.sort(key=lambda e: e[2])

    report = {
        "input_rows": len(rows),
        "kept_rows": len(kept),
        "snapped": len(snapped),
        "snapped_detail": snapped,
        "moved_to_review": len(review),
        "review_frames": sorted({row["frame_number"] for row in review}),
        "removed_duplicates": len(deduped),
        "duplicate_frames": sorted({row["frame_number"] for row in deduped}),
    }

    if not dry_run:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = manifest_path.with_name(f"{manifest_path.name}.bak-{stamp}")
        shutil.copy2(manifest_path, backup)
        manifest_path.write_text(
            "".join(json.dumps(entry[0]) + "\n" for entry in kept),
            encoding="utf-8",
        )
        review_path = manifest_path.with_name("templates.review.jsonl")
        if review:
            with review_path.open("a", encoding="utf-8") as handle:
                for row in review:
                    handle.write(json.dumps(row) + "\n")
        report["backup"] = str(backup)
        if review:
            report["review_file"] = str(review_path)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/solidworks-tut/templates/templates.jsonl"),
    )
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path("data/solidworks-tut/selection.json"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without touching the manifest.",
    )
    args = parser.parse_args()

    report = clean(args.manifest, args.selection, dry_run=args.dry_run)
    print(json.dumps(report, indent=2))
    if report["moved_to_review"]:
        print(
            f"\n{report['moved_to_review']} row(s) need manual re-annotation "
            f"(frames: {report['review_frames']}). Re-label them in the "
            "workbench — the preview is now frame-accurate."
        )


if __name__ == "__main__":
    main()
