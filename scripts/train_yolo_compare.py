#!/usr/bin/env python3
"""Print (or optionally run) the side-by-side yolo11s / yolo11m train commands.

Does not train unless ``--run`` is passed. Shared split/seed via train_yolo.py.
Winner promotion to ``artifacts/models/cursor/weights/best.pt`` is manual (HITL).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TRAIN = REPO / "scripts" / "train_yolo.py"

SHARED = [
    "--selection",
    "data/solidworks-tut/selection.json",
    "--manifest",
    "data/solidworks-tut/templates/templates.jsonl",
    "--dataset-dir",
    "data/solidworks-tut/yolo-dataset",
    "--project",
    "artifacts/models",
    "--epochs",
    "100",
    "--patience",
    "25",
    "--imgsz",
    "1024",
    "--seed",
    "42",
    "--val-fraction",
    "0.2",
]

RUNS = [
    {
        "name": "cursor-yolo11s",
        "weights": "yolo11s.pt",
        "batch": "32",
    },
    {
        "name": "cursor-yolo11m",
        "weights": "yolo11m.pt",
        "batch": "16",
    },
]


def cmds() -> list[list[str]]:
    out: list[list[str]] = []
    for run in RUNS:
        out.append(
            [
                sys.executable,
                str(TRAIN),
                *SHARED,
                "--name",
                run["name"],
                "--weights",
                run["weights"],
                "--batch",
                run["batch"],
            ]
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        help="Actually start both training runs (GPU recommended). Default: print only.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Only prepare the stratified dataset once (print + optional run).",
    )
    args = parser.parse_args()

    if args.prepare_only:
        prepare = [
            sys.executable,
            str(TRAIN),
            *SHARED,
            "--prepare-only",
        ]
        print(" ".join(prepare))
        if args.run:
            raise SystemExit(subprocess.call(prepare, cwd=REPO))
        return

    for cmd in cmds():
        print(" ".join(cmd))
        if args.run:
            code = subprocess.call(cmd, cwd=REPO)
            if code != 0:
                raise SystemExit(code)

    print(
        "\nAfter both finish, compare val mAP50 / mAP50-95 under "
        "artifacts/models/cursor-yolo11s|m/ and copy the winner to "
        "artifacts/models/cursor/weights/best.pt"
    )


if __name__ == "__main__":
    main()
