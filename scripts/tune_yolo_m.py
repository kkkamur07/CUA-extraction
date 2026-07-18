#!/usr/bin/env python3
"""Stable Ultralytics hyperparameter tune for cursor YOLO11m.

Fitness collapse has no configurable interval — Ultralytics recovers when
validation fitness drops to 0 (up to 3 reloads of last.pt). We reduce collapse
risk by constraining LR / augs instead.
"""

from __future__ import annotations

from ultralytics import YOLO

# Safer search space for a tiny one-class cursor dataset.
SPACE = {
    "lr0": (1e-5, 1e-3),  # AdamW-friendly; default tune goes up to 1e-2 (unstable here)
    "lrf": (0.01, 0.2),
    "momentum": (0.85, 0.95),
    "weight_decay": (0.0, 0.001),
    "warmup_epochs": (1.0, 3.0),
    "warmup_momentum": (0.5, 0.9),
    "box": (5.0, 10.0),
    "cls": (0.3, 1.0),
    "dfl": (1.0, 2.0),
    # Mild color jitter only — no geometric flips (cursors are asymmetric).
    "hsv_h": (0.0, 0.02),
    "hsv_s": (0.0, 0.3),
    "hsv_v": (0.0, 0.3),
    "degrees": (0.0, 0.0),
    "translate": (0.0, 0.05),
    "scale": (0.0, 0.15),
    "shear": (0.0, 0.0),
    "perspective": (0.0, 0.0),
    "flipud": (0.0, 0.0),
    "fliplr": (0.0, 0.0),
    "bgr": (0.0, 0.0),
    "mosaic": (0.0, 0.0),
    "mixup": (0.0, 0.0),
    "cutmix": (0.0, 0.0),
    "copy_paste": (0.0, 0.0),
    "close_mosaic": (0.0, 0.0),
}


def main() -> None:
    model = YOLO("yolo11m.pt")
    model.tune(
        data="data/solidworks-tut/yolo-dataset/data.yaml",
        space=SPACE,
        epochs=10,
        iterations=15,
        patience=3,  # early-stop each trial if no val improvement for 3 epochs
        imgsz=1024,
        batch=4,
        device=0,
        amp=False,
        mosaic=0.0,
        fliplr=0.0,
        flipud=0.0,
        optimizer="AdamW",
        workers=0,
        project="artifacts/models",
        name="lr-tune-yolo11m-stable-i15",
        exist_ok=True,
    )


if __name__ == "__main__":
    main()
