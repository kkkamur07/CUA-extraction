"""Prepare the labeled video frames and train a one-class YOLO cursor detector."""

from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
import yaml
from ultralytics import YOLO


def canonical_label(label: str) -> str:
    """Collapse cursor variants into stable semantic labels."""
    if label == "cross_hair":
        return "crosshair_black"
    if label == "arrow_white_blue" or label.startswith("arrow_with_"):
        return "arrow_white"
    return label


def load_annotations(manifest_path: Path) -> dict[int, list[dict[str, Any]]]:
    """Load and deduplicate annotations, grouped by source frame."""
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[int, int, int, int, int]] = set()
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        annotation = json.loads(line)
        key = (
            annotation["frame_number"],
            annotation["x"],
            annotation["y"],
            annotation["width"],
            annotation["height"],
        )
        if key in seen:
            continue
        seen.add(key)
        annotation["label"] = canonical_label(annotation["label"])
        grouped[annotation["frame_number"]].append(annotation)
    return dict(grouped)


def _temporal_groups(
    frame_numbers: list[int],
    group_gap_frames: int,
) -> list[list[int]]:
    groups: list[list[int]] = []
    for frame_number in sorted(frame_numbers):
        if not groups or frame_number - groups[-1][-1] > group_gap_frames:
            groups.append([])
        groups[-1].append(frame_number)
    return groups


def _label_counts_for_frames(
    frames: list[int],
    annotations: dict[int, list[dict[str, Any]]],
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for frame_number in frames:
        for annotation in annotations[frame_number]:
            counts[annotation["label"]] += 1
    return dict(counts)


def _val_targets_per_label(
    total_labels: dict[str, int],
    val_fraction: float,
) -> dict[str, int]:
    """Proportional val targets; keep singletons in train; leave ≥1 in train when possible."""
    targets: dict[str, int] = {}
    for label, count in total_labels.items():
        if count <= 1:
            targets[label] = 0
            continue
        desired = round(count * val_fraction)
        desired = max(1, desired)
        desired = min(desired, count - 1)
        targets[label] = desired
    return targets


def split_frames(
    frame_numbers: list[int],
    annotations: dict[int, list[dict[str, Any]]],
    val_fraction: float,
    seed: int,
    group_gap_frames: int,
) -> tuple[set[int], dict[str, Any]]:
    """Temporal groups + label-proportional assignment (no adjacent-frame leakage)."""
    groups = _temporal_groups(frame_numbers, group_gap_frames)
    total_labels = _label_counts_for_frames(frame_numbers, annotations)
    targets = _val_targets_per_label(total_labels, val_fraction)
    frame_budget = max(1, round(len(frame_numbers) * val_fraction))

    rng = random.Random(seed)
    order = list(range(len(groups)))
    rng.shuffle(order)

    val_frames: set[int] = set()
    val_labels: dict[str, int] = defaultdict(int)
    chosen: list[int] = []

    def deficit() -> dict[str, int]:
        return {
            label: max(0, target - val_labels.get(label, 0))
            for label, target in targets.items()
        }

    def group_score(group_index: int) -> tuple[float, int]:
        group = groups[group_index]
        counts = _label_counts_for_frames(group, annotations)
        # Prefer groups that fill the largest remaining label deficits.
        gain = sum(
            min(counts.get(label, 0), need) for label, need in deficit().items() if need > 0
        )
        # Soft penalty for overshooting targets so common labels don't dominate.
        overshoot = sum(
            max(0, val_labels.get(label, 0) + counts.get(label, 0) - target)
            for label, target in targets.items()
        )
        return (gain - 0.25 * overshoot, -len(group))

    # Pass 1: cover rare / under-filled labels first.
    while True:
        needs = deficit()
        if not any(needs.values()):
            break
        if len(val_frames) >= frame_budget and any(
            val_labels.get(label, 0) > 0 for label, need in needs.items() if need > 0
        ):
            # Budget hit; still try one more group only if some label has zero val examples.
            if all(val_labels.get(label, 0) > 0 or target == 0 for label, target in targets.items()):
                break

        candidates = [index for index in order if index not in chosen]
        if not candidates:
            break
        # Only consider groups that help at least one deficit label.
        helpful = [
            index
            for index in candidates
            if any(
                _label_counts_for_frames(groups[index], annotations).get(label, 0) > 0
                and need > 0
                for label, need in needs.items()
            )
        ]
        if not helpful:
            break
        if len(val_frames) >= frame_budget * 1.35:
            break

        best = max(helpful, key=group_score)
        chosen.append(best)
        for frame_number in groups[best]:
            val_frames.add(frame_number)
        for label, count in _label_counts_for_frames(groups[best], annotations).items():
            val_labels[label] += count

    # Pass 2: fill remaining frame budget with least-damaging groups.
    while len(val_frames) < frame_budget:
        candidates = [index for index in order if index not in chosen]
        if not candidates:
            break
        best = max(candidates, key=group_score)
        # Stop if adding the smallest remaining group would wildly overshoot budget.
        if len(val_frames) + len(groups[best]) > frame_budget * 1.5 and len(val_frames) >= max(
            1, frame_budget // 2
        ):
            # Try a smaller leftover group instead.
            smaller = [index for index in candidates if len(groups[index]) <= frame_budget - len(val_frames)]
            if not smaller:
                break
            best = min(smaller, key=lambda index: len(groups[index]))
        chosen.append(best)
        for frame_number in groups[best]:
            val_frames.add(frame_number)
        for label, count in _label_counts_for_frames(groups[best], annotations).items():
            val_labels[label] += count

    train_labels = {
        label: total_labels[label] - val_labels.get(label, 0) for label in total_labels
    }
    split_info = {
        "method": "temporal_groups_label_proportional",
        "group_gap_frames": group_gap_frames,
        "validation_fraction": val_fraction,
        "frame_budget": frame_budget,
        "val_frames": len(val_frames),
        "train_frames": len(frame_numbers) - len(val_frames),
        "label_targets_val": targets,
        "label_counts_val": dict(val_labels),
        "label_counts_train": train_labels,
        "total_labels": total_labels,
    }
    return set(val_frames), split_info


def yolo_box(annotation: dict[str, Any], width: int, height: int) -> str:
    """Convert an ROI-relative pixel box into a normalized YOLO label."""
    x = max(0, min(int(annotation["x"]), width - 1))
    y = max(0, min(int(annotation["y"]), height - 1))
    right = max(x + 1, min(x + int(annotation["width"]), width))
    bottom = max(y + 1, min(y + int(annotation["height"]), height))
    box_width = right - x
    box_height = bottom - y
    center_x = (x + box_width / 2) / width
    center_y = (y + box_height / 2) / height
    return f"0 {center_x:.6f} {center_y:.6f} {box_width / width:.6f} {box_height / height:.6f}"


def prepare_dataset(
    selection_path: Path,
    manifest_path: Path,
    dataset_dir: Path,
    val_fraction: float,
    seed: int,
    group_gap_frames: int,
) -> tuple[Path, dict[str, int], dict[str, Any]]:
    """Export ROI frames and one-class YOLO labels from the video."""
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    video_path = Path(selection["video"])
    if not video_path.is_absolute():
        video_path = selection_path.parent.parent.parent / video_path
    roi = selection["roi"]
    annotations = load_annotations(manifest_path)
    frame_numbers = sorted(annotations)
    if len(frame_numbers) < 2:
        raise ValueError("At least two annotated frames are required.")

    val_frames, split_info = split_frames(
        frame_numbers,
        annotations,
        val_fraction,
        seed,
        group_gap_frames,
    )

    for split in ("train", "val"):
        for kind in ("images", "labels"):
            split_dir = dataset_dir / kind / split
            if split_dir.exists():
                shutil.rmtree(split_dir)
            split_dir.mkdir(parents=True, exist_ok=True)

    video = cv2.VideoCapture(str(video_path))
    if not video.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    counts = {"train_frames": 0, "val_frames": 0, "boxes": 0}
    try:
        for frame_number in frame_numbers:
            video.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ok, frame = video.read()
            if not ok:
                raise ValueError(f"Could not read source frame {frame_number}")
            cropped = frame[
                roi["y"] : roi["y"] + roi["height"],
                roi["x"] : roi["x"] + roi["width"],
            ]
            if cropped.size == 0:
                raise ValueError(f"ROI is empty for source frame {frame_number}")
            height, width = cropped.shape[:2]
            split = "val" if frame_number in val_frames else "train"
            stem = f"frame_{frame_number:08d}"
            if not cv2.imwrite(str(dataset_dir / "images" / split / f"{stem}.jpg"), cropped):
                raise ValueError(f"Could not write dataset image for frame {frame_number}")
            labels = [
                yolo_box(annotation, width, height)
                for annotation in annotations[frame_number]
            ]
            (dataset_dir / "labels" / split / f"{stem}.txt").write_text(
                "\n".join(labels) + "\n",
                encoding="utf-8",
            )
            counts[f"{split}_frames"] += 1
            counts["boxes"] += len(labels)
    finally:
        video.release()

    data = {
        "path": str(dataset_dir.resolve()),
        "train": "images/train",
        "val": "images/val",
        "names": {0: "cursor"},
    }
    data_path = dataset_dir / "data.yaml"
    data_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return data_path, counts, split_info


def select_best_map50_weights(run_dir: Path) -> dict[str, Any]:
    """Replace best.pt with the epoch that maximized mAP50 (not Ultralytics fitness)."""
    import csv

    results_path = run_dir / "results.csv"
    weights_dir = run_dir / "weights"
    if not results_path.is_file():
        raise FileNotFoundError(f"Missing training results: {results_path}")

    rows = list(csv.DictReader(results_path.open(encoding="utf-8")))
    if not rows:
        raise ValueError(f"Empty training results: {results_path}")

    map_key = next(key for key in rows[0] if "mAP50" in key and "95" not in key)
    best_row = max(rows, key=lambda row: float(row[map_key] or 0.0))
    best_epoch = int(float(best_row["epoch"]))
    best_map50 = float(best_row[map_key])

    # Ultralytics save_period checkpoints are epoch{N}.pt (1-indexed epoch number).
    candidates = [
        weights_dir / f"epoch{best_epoch}.pt",
        weights_dir / f"epoch{best_epoch - 1}.pt",
    ]
    chosen = next((path for path in candidates if path.is_file()), None)
    fitness_best = weights_dir / "best.pt"
    last = weights_dir / "last.pt"

    selection = {
        "criterion": "mAP50",
        "epoch": best_epoch,
        "map50": best_map50,
        "precision": float(best_row.get("metrics/precision(B)", 0) or 0),
        "recall": float(best_row.get("metrics/recall(B)", 0) or 0),
        "map50_95": float(
            next(
                (best_row[key] for key in best_row if "mAP50-95" in key),
                0,
            )
            or 0
        ),
        "source": None,
    }

    if chosen is not None:
        archive = weights_dir / "best_ultralytics_fitness.pt"
        if fitness_best.is_file():
            shutil.copy2(fitness_best, archive)
        shutil.copy2(chosen, fitness_best)
        selection["source"] = str(chosen.relative_to(run_dir))
        selection["archived_fitness_best"] = str(archive.relative_to(run_dir))
    elif fitness_best.is_file():
        selection["source"] = "weights/best.pt (epoch checkpoint missing; kept Ultralytics best)"
        selection["warning"] = (
            "save_period checkpoint for the best mAP50 epoch was not found; "
            "left Ultralytics fitness best.pt in place"
        )
    elif last.is_file():
        shutil.copy2(last, fitness_best)
        selection["source"] = "weights/last.pt"
        selection["warning"] = "Fell back to last.pt"
    else:
        raise FileNotFoundError(f"No weights found under {weights_dir}")

    return selection


def select_device(override: str | None = None) -> str | int:
    """Prefer CUDA, then MPS, then CPU. ``override`` forces a device string/index."""
    if override:
        text = override.strip()
        if text.isdigit():
            return int(text)
        return text
    import torch

    if torch.cuda.is_available():
        return 0
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path("data/solidworks-tut/selection.json"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/solidworks-tut/templates/templates.jsonl"),
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("data/solidworks-tut/yolo-dataset"),
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=Path("artifacts/models"),
        help="Directory for trained model runs (weights land under <project>/<name>/).",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="cursor",
        help="Ultralytics run name under --project (use a new name to keep older checkpoints).",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=Path("artifacts/models/yolo11n.pt"),
        help="Starting weights (.pt). Pass a prior best.pt to fine-tune.",
    )
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument(
        "--patience",
        type=int,
        default=25,
        help="Early-stopping patience (0 = train all epochs, then pick best mAP50).",
    )
    parser.add_argument("--imgsz", type=int, default=1024)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument(
        "--group-gap-frames",
        type=int,
        default=90,
        help="Keep annotations within this many source frames in one split group.",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--device",
        default=None,
        help="Force device (e.g. 0, cuda:0, mps, cpu). Default: cuda → mps → cpu.",
    )
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    data_path, counts, split_info = prepare_dataset(
        args.selection,
        args.manifest,
        args.dataset_dir,
        args.val_fraction,
        args.seed,
        args.group_gap_frames,
    )
    print(f"Prepared {counts['boxes']} boxes: {counts['train_frames']} train frames, "
          f"{counts['val_frames']} validation frames")
    print("Split label counts (train):", json.dumps(split_info["label_counts_train"]))
    print("Split label counts (val):  ", json.dumps(split_info["label_counts_val"]))
    print("Split label targets (val): ", json.dumps(split_info["label_targets_val"]))
    if args.prepare_only:
        print(f"Dataset config: {data_path}")
        return

    device = select_device(args.device)
    weights = str(args.weights)
    print(f"Training on {device} from {weights}")
    model = YOLO(weights)
    project_dir = args.project.resolve()
    run_dir = project_dir / args.name
    if run_dir.exists():
        archive = project_dir / f"{args.name}-archive-{run_dir.stat().st_mtime_ns}"
        print(f"Keeping earlier run at {archive}")
        shutil.move(str(run_dir), str(archive))
    model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        workers=0,
        project=str(project_dir),
        name=args.name,
        exist_ok=True,
        patience=args.patience,
        save_period=1,
        seed=args.seed,
        plots=True,
        hsv_h=0.0,
        hsv_s=0.2,
        hsv_v=0.2,
        degrees=0.0,
        translate=0.05,
        scale=0.15,
        shear=0.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.0,
        mosaic=0.3,
        mixup=0.0,
        copy_paste=0.0,
        erasing=0.1,
        close_mosaic=10,
    )

    selection = select_best_map50_weights(run_dir)
    print(
        f"Selected best.pt by mAP50: epoch {selection['epoch']} "
        f"(mAP50={selection['map50']:.4f}, P={selection['precision']:.4f}, "
        f"R={selection['recall']:.4f}) from {selection['source']}"
    )

    metrics = model.val(
        data=str(data_path),
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        workers=0,
        plots=True,
    )
    # Re-load selected weights so reported metrics match best.pt.
    best_path = run_dir / "weights" / "best.pt"
    selected_metrics = {
        "map50": float(selection["map50"]),
        "map50_95": float(selection["map50_95"]),
        "precision": float(selection["precision"]),
        "recall": float(selection["recall"]),
        "selection_epoch": selection["epoch"],
        "selection_source": selection["source"],
        "final_val_map50": float(metrics.box.map50),
        "final_val_map50_95": float(metrics.box.map),
        "final_val_precision": float(metrics.box.mp),
        "final_val_recall": float(metrics.box.mr),
    }
    if best_path.is_file():
        model = YOLO(str(best_path))
        metrics = model.val(
            data=str(data_path),
            imgsz=args.imgsz,
            batch=args.batch,
            device=device,
            workers=0,
            plots=True,
        )
        selected_metrics.update(
            {
                "map50": float(metrics.box.map50),
                "map50_95": float(metrics.box.map),
                "precision": float(metrics.box.mp),
                "recall": float(metrics.box.mr),
            }
        )

    summary = {
        "device": device,
        "weights": weights,
        "data": str(data_path),
        "counts": counts,
        "split": split_info,
        "augmentation": {
            "hsv_s": 0.2,
            "hsv_v": 0.2,
            "translate": 0.05,
            "scale": 0.15,
            "mosaic": 0.3,
            "erasing": 0.1,
            "flips": False,
        },
        "checkpoint_selection": selection,
        "metrics": {
            "map50": selected_metrics["map50"],
            "map50_95": selected_metrics["map50_95"],
            "precision": selected_metrics["precision"],
            "recall": selected_metrics["recall"],
        },
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary["metrics"], indent=2))
    print(f"Summary: {summary_path}")
    print(f"Best weights: {best_path}")


if __name__ == "__main__":
    main()