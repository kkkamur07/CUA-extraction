"""Audit cursor annotations for duplicates, conflicts, and temporal redundancy."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from train_yolo import canonical_label


def read_rows(manifest_path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def geometry_key(row: dict[str, Any]) -> tuple[int, int, int, int, int]:
    return (
        row["frame_number"],
        row["x"],
        row["y"],
        row["width"],
        row["height"],
    )


def temporal_groups(frame_numbers: list[int], gap: int) -> list[list[int]]:
    groups: list[list[int]] = []
    for frame_number in sorted(frame_numbers):
        if not groups or frame_number - groups[-1][-1] > gap:
            groups.append([])
        groups[-1].append(frame_number)
    return groups


def audit(manifest_path: Path, selection_path: Path) -> dict[str, Any]:
    rows = read_rows(manifest_path)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    roi = selection["roi"]

    exact_records = Counter(
        (
            row["frame_number"],
            row["label"],
            row["x"],
            row["y"],
            row["width"],
            row["height"],
        )
        for row in rows
    )
    by_geometry: dict[tuple[int, int, int, int, int], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for row in rows:
        by_geometry[geometry_key(row)].append(row)

    patch_hashes: Counter[str] = Counter()
    missing_paths: list[str] = []
    invalid_boxes: list[dict[str, Any]] = []
    for row in rows:
        path = Path(row["path"])
        if not path.exists():
            missing_paths.append(str(path))
        else:
            patch_hashes[hashlib.sha1(path.read_bytes()).hexdigest()] += 1
        if (
            row["x"] < 0
            or row["y"] < 0
            or row["width"] <= 0
            or row["height"] <= 0
            or row["x"] + row["width"] > roi["width"]
            or row["y"] + row["height"] > roi["height"]
        ):
            invalid_boxes.append(row)

    frames = sorted({row["frame_number"] for row in rows})
    groups = temporal_groups(frames, gap=90)
    canonical_conflicts = {
        str(key): sorted({canonical_label(row["label"]) for row in group})
        for key, group in by_geometry.items()
        if len({canonical_label(row["label"]) for row in group}) > 1
    }
    raw_conflicts = sum(
        1 for group in by_geometry.values() if len({row["label"] for row in group}) > 1
    )
    report = {
        "records": len(rows),
        "unique_frames": len(frames),
        "raw_labels": dict(Counter(row["label"] for row in rows)),
        "canonical_labels": dict(
            Counter(canonical_label(row["label"]) for row in rows)
        ),
        "exact_duplicate_records": sum(
            count - 1 for count in exact_records.values() if count > 1
        ),
        "unique_geometry_boxes": len(by_geometry),
        "raw_same_box_label_conflicts": raw_conflicts,
        "same_box_label_conflicts": len(canonical_conflicts),
        "canonical_conflicts": canonical_conflicts,
        "identical_patch_duplicates": sum(
            count - 1 for count in patch_hashes.values() if count > 1
        ),
        "missing_patch_paths": missing_paths,
        "invalid_boxes": invalid_boxes,
        "ambiguous_records": sum(bool(row.get("ambiguous")) for row in rows),
        "temporal_groups_within_90_frames": len(groups),
        "largest_temporal_group": max((len(group) for group in groups), default=0),
        "canonicalization": {
            "arrow_with_*": "arrow_white",
            "arrow_white_blue": "arrow_white",
            "cross_hair": "crosshair_black",
        },
        "recommendations": [
            "Keep one label per frame/geometry box after canonicalization.",
            "Split validation by temporal groups to avoid adjacent-frame leakage.",
            "Add more pencil and crosshair examples before training separate classes.",
        ],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
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
        "--output",
        type=Path,
        default=Path("data/solidworks-tut/yolo-data-quality.json"),
    )
    args = parser.parse_args()

    report = audit(args.manifest, args.selection)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
