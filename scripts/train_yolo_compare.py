#!/usr/bin/env python3
"""Print (or optionally run) the side-by-side yolo11s / yolo11m train commands.

Does not train unless ``--run`` is passed. Shared split/seed via train_yolo.py.
Winner promotion to ``artifacts/models/cursor/weights/best.pt`` is manual (HITL).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
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
    "0",
    "--imgsz",
    "1024",
    "--seed",
    "42",
    "--val-fraction",
    "0.2",
]

RUNS = [
    {
        "suffix": "yolo11s",
        "weights": "yolo11s.pt",
        "batch": "16",
        "extra": [],
    },
    {
        "suffix": "yolo11m",
        "weights": "yolo11m.pt",
        # Medium is less stable on ~120 images @1024; keep LR/mosaic conservative.
        "batch": "4",
        "extra": ["--mosaic", "0", "--lr0", "0.0005", "--optimizer", "AdamW"],
    },
]


def cmds(stamp: str | None = None) -> list[tuple[str, list[str]]]:
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    out: list[tuple[str, list[str]]] = []
    for run in RUNS:
        name = f"{stamp}-{run['suffix']}"
        out.append(
            (
                name,
                [
                    sys.executable,
                    str(TRAIN),
                    *SHARED,
                    "--name",
                    name,
                    "--weights",
                    run["weights"],
                    "--batch",
                    run["batch"],
                    *run.get("extra", []),
                ],
            )
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
    parser.add_argument(
        "--device",
        default=None,
        help="Forwarded to train_yolo.py (e.g. 0).",
    )
    args = parser.parse_args()

    device_args = ["--device", args.device] if args.device is not None else []

    if args.prepare_only:
        prepare = [
            sys.executable,
            str(TRAIN),
            *SHARED,
            *device_args,
            "--prepare-only",
        ]
        print(" ".join(prepare))
        if args.run:
            raise SystemExit(subprocess.call(prepare, cwd=REPO))
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for name, cmd in cmds(stamp):
        full = [*cmd, *device_args]
        print(" ".join(full))
        if args.run:
            code = subprocess.call(full, cwd=REPO)
            if code != 0:
                raise SystemExit(code)
            print(f"Finished run: artifacts/models/{name}")

    print(
        "\nAfter both finish, compare val mAP50 / mAP50-95 under "
        f"artifacts/models/{stamp}-yolo11s|m/ and copy the winner to "
        "artifacts/models/cursor/weights/best.pt"
    )


if __name__ == "__main__":
    main()
