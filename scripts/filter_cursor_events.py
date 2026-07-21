"""Reduce frame-level cursor detections to a compact cursor track.

The YOLO detector produces observations, not semantic mouse actions. This
script keeps the raw detections untouched and writes a derived track with:

* one detection per source frame,
* a confidence threshold,
* removal of duplicate boxes from the same source frame, and
* retention of points only when the cursor moves at least 4 pixels.

It can also normalize keyboard-overlay mouse controls. In this project the
overlay convention is M1 = right click and M2 = left click.

Example:

    python3 scripts/filter_cursor_events.py \
        --input artifacts/predictions/solidworks-tut/detections-cleaned-yolo11m.jsonl \
        --output runs/solidworks-tut/cursor/cursor_events.jsonl

When ``--keystrokes`` is supplied, normalized mouse-button events are written
to ``--mouse-output`` as a separate JSONL artifact.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Detection:
    timestamp: float
    x: float
    y: float
    confidence: float
    frame_number: int | None = None


MOUSE_BUTTONS = {
    "M1": "left",
    "M2": "right",
}


def _number(item: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = item.get(name)
        if value is not None:
            return float(value)
    return None


def _parse_detection(item: dict[str, Any], line_number: int) -> Detection:
    timestamp = _number(item, "timestamp_seconds", "t")
    confidence = _number(item, "confidence")
    if timestamp is None or confidence is None:
        raise ValueError(
            f"line {line_number}: expected timestamp_seconds/t and confidence"
        )

    x = _number(item, "x")
    y = _number(item, "y")
    if x is None or y is None:
        raise ValueError(f"line {line_number}: expected x and y")

    # Detection exports store the top-left corner and dimensions. Cursor raw
    # events store the center, so convert only when needed.
    if "timestamp_seconds" in item and "width" in item and "height" in item:
        x += float(item["width"]) / 2.0
        y += float(item["height"]) / 2.0

    frame_number = item.get("frame_number")
    return Detection(
        timestamp=timestamp,
        x=x,
        y=y,
        confidence=confidence,
        frame_number=int(frame_number) if frame_number is not None else None,
    )


def load_detections(path: Path, *, skip_invalid: bool = False) -> list[Detection]:
    """Load either detector JSONL or cursor-events JSONL."""
    detections: list[Detection] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                if not skip_invalid:
                    raise
                print(f"Skipping malformed JSON line {line_number} in {path}")
                continue
            if not isinstance(item, dict):
                raise ValueError(f"line {line_number}: expected a JSON object")
            detections.append(_parse_detection(item, line_number))
    return detections


def _frame_key(detection: Detection) -> tuple[str, int | float]:
    if detection.frame_number is not None:
        return ("frame", detection.frame_number)
    # Timestamps from video decoding can differ by floating-point noise.
    return ("time", round(detection.timestamp, 6))


def keep_best_per_frame(detections: Iterable[Detection]) -> list[Detection]:
    """Collapse multiple YOLO boxes for one frame to the best box."""
    best: dict[tuple[str, int | float], Detection] = {}
    for detection in detections:
        key = _frame_key(detection)
        previous = best.get(key)
        if previous is None or detection.confidence > previous.confidence:
            best[key] = detection
    return sorted(best.values(), key=lambda item: item.timestamp)


def filter_track(
    detections: Iterable[Detection],
    *,
    min_confidence: float = 0.4,
    min_move_px: float = 4.0,
) -> tuple[list[Detection], dict[str, int]]:
    """Filter detections into a compact, time-ordered cursor trajectory."""
    if min_move_px < 0:
        raise ValueError("min_move_px must be non-negative")

    source = list(detections)
    confidence_filtered = [
        item for item in source if item.confidence >= min_confidence
    ]
    frame_filtered = keep_best_per_frame(confidence_filtered)
    if not frame_filtered:
        return [], {
            "input": len(source),
            "after_confidence": len(confidence_filtered),
            "after_frame_dedup": 0,
            "output": 0,
        }

    # Spatial filtering is the only temporal reduction policy. A stationary
    # cursor therefore produces no repeated events.
    output = [frame_filtered[0]]
    for item in frame_filtered[1:-1]:
        previous = output[-1]
        distance = ((item.x - previous.x) ** 2 + (item.y - previous.y) ** 2) ** 0.5
        if distance >= min_move_px:
            output.append(item)
    if len(frame_filtered) > 1:
        output.append(frame_filtered[-1])

    return output, {
        "input": len(source),
        "after_confidence": len(confidence_filtered),
        "after_frame_dedup": len(frame_filtered),
        "output": len(output),
    }


def _cursor_event(detection: Detection) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "cursor",
        "t": round(detection.timestamp, 6),
        "x": round(detection.x, 3),
        "y": round(detection.y, 3),
        "confidence": round(detection.confidence, 6),
        "click_candidate": False,
    }
    if detection.frame_number is not None:
        event["source_frame"] = detection.frame_number
    return event


def write_jsonl(path: Path, events: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            count += 1
    return count


def normalize_mouse_buttons(path: Path) -> list[dict[str, Any]]:
    """Convert overlay M1/M2 keystroke detections to mouse-button events."""
    raw_path = path.with_name("raw_keystrokes.json")
    if raw_path.is_file():
        path = raw_path
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw.get("events", []) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError(f"{path}: expected an events list")

    events: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        source_key = str(item.get("key", "")).upper()
        button = MOUSE_BUTTONS.get(source_key)
        if button is None:
            continue
        event = {
            "type": "mouse_button",
            "button": button,
            "press_t": float(item["press_t"]),
            "release_t": float(item["release_t"]),
            "source_key": source_key,
            "clipped": bool(item.get("clipped", False)),
        }
        events.append(event)
    return sorted(events, key=lambda item: (item["press_t"], item["button"]))


def write_metadata(
    path: Path,
    *,
    input_path: Path,
    output_path: Path,
    counts: dict[str, int],
    min_confidence: float,
    min_move_px: float,
    mouse_output: Path | None = None,
    mouse_count: int | None = None,
) -> None:
    metadata: dict[str, Any] = {
        "input": str(input_path),
        "output": str(output_path),
        "filter": {
            "min_confidence": min_confidence,
            "min_move_px": min_move_px,
        },
        "counts": counts,
        "mouse_button_mapping": MOUSE_BUTTONS,
    }
    if mouse_output is not None:
        metadata["mouse_output"] = str(mouse_output)
        metadata["mouse_count"] = mouse_count
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(
            "artifacts/predictions/solidworks-tut/"
            "detections-cleaned-yolo11m.jsonl"
        ),
        help="Raw detector JSONL or cursor_events.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runs/solidworks-tut/trace/cursor/cursor_events.jsonl"),
        help="Filtered cursor JSONL output",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="Metadata output (default: sibling filter_summary.json)",
    )
    parser.add_argument("--min-confidence", type=float, default=0.4)
    parser.add_argument("--min-move-px", type=float, default=4.0)
    parser.add_argument(
        "--skip-invalid",
        action="store_true",
        help="Skip malformed JSONL lines instead of failing",
    )
    parser.add_argument(
        "--keystrokes",
        type=Path,
        default=None,
        help="Optional keystrokes.json containing M1/M2 detections",
    )
    parser.add_argument(
        "--mouse-output",
        type=Path,
        default=None,
        help="Mouse-button JSONL output (required with --keystrokes)",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(f"Input detections not found: {args.input}")
    if args.keystrokes is not None and args.mouse_output is None:
        args.mouse_output = args.output.parent / "mouse_events.jsonl"

    detections = load_detections(args.input, skip_invalid=args.skip_invalid)
    filtered, counts = filter_track(
        detections,
        min_confidence=args.min_confidence,
        min_move_px=args.min_move_px,
    )
    write_jsonl(args.output, (_cursor_event(item) for item in filtered))

    mouse_count: int | None = None
    if args.keystrokes is not None:
        if not args.keystrokes.is_file():
            raise FileNotFoundError(f"Keystrokes not found: {args.keystrokes}")
        mouse_events = normalize_mouse_buttons(args.keystrokes)
        mouse_count = write_jsonl(args.mouse_output, mouse_events)

    metadata_path = args.metadata or args.output.parent / "filter_summary.json"
    write_metadata(
        metadata_path,
        input_path=args.input,
        output_path=args.output,
        counts=counts,
        min_confidence=args.min_confidence,
        min_move_px=args.min_move_px,
        mouse_output=args.mouse_output,
        mouse_count=mouse_count,
    )
    print(
        f"Cursor events: {counts['input']} -> {counts['output']} "
        f"({args.output})"
    )
    if args.keystrokes is not None:
        print(f"Mouse-button events: {mouse_count} ({args.mouse_output})")
    print(f"Filter summary: {metadata_path}")


if __name__ == "__main__":
    main()
