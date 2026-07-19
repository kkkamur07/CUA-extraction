"""Write final run artifacts normalized to the final-clip timeline.

The final video is trimmed to the selection range and cropped to the screen
ROI, so its timeline starts at 0 and its pixels start at the ROI origin. This
script converts the intermediate trace artifacts into the published final
files on that same timeline:

* all timestamps are shifted by the selection start (clip time 0);
* events outside the selection range are dropped, partial ones clamped;
* cursor x/y are shifted from full-frame pixels into screen-crop pixels; and
* keystroke frame numbers are rebased onto the clip's frames.

Example:

    python3 scripts/normalize_final_events.py runs/solidworks-tut
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from cursor.workflow.workflow import load_project_selection


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                items.append(json.loads(line))
    return items


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items),
        encoding="utf-8",
    )


def _shift(value: float, offset: float) -> float:
    return round(float(value) - offset, 6)


def normalize_cursor_events(
    events: list[dict[str, Any]],
    *,
    start: float,
    duration: float,
    roi_x: float,
    roi_y: float,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for event in events:
        t = _shift(event["t"], start)
        if t < 0 or t > duration:
            continue
        item = {**event, "t": t}
        item["x"] = round(float(event["x"]) - roi_x, 3)
        item["y"] = round(float(event["y"]) - roi_y, 3)
        output.append(item)
    return output


def normalize_span_events(
    events: list[dict[str, Any]],
    *,
    start: float,
    duration: float,
) -> list[dict[str, Any]]:
    """Shift press_t/release_t spans; drop outside, clamp partial overlaps."""
    output: list[dict[str, Any]] = []
    for event in events:
        press = _shift(event["press_t"], start)
        release = _shift(event["release_t"], start)
        if release < 0 or press > duration:
            continue
        item = {**event}
        if press < 0 or release > duration:
            item["clipped"] = True
        item["press_t"] = max(0.0, press)
        item["release_t"] = min(duration, release)
        output.append(item)
    return output


def _rebase_frames(
    events: list[dict[str, Any]],
    start_frame: int,
) -> list[dict[str, Any]]:
    output = []
    for event in events:
        item = {**event}
        for key in ("press_frame", "release_frame"):
            if key in item:
                item[key] = max(0, int(item[key]) - start_frame)
        output.append(item)
    return output


def normalize_keystrokes(
    payload: dict[str, Any],
    *,
    start: float,
    duration: float,
) -> dict[str, Any]:
    events = normalize_span_events(payload["events"], start=start, duration=duration)
    meta = dict(payload.get("meta") or {})
    source_range = dict(meta.get("range") or {})
    fps = float(meta.get("fps") or 0.0)
    start_frame = source_range.get("start_frame")
    if start_frame is None:
        start_frame = round(start * fps) if fps else 0
    events = _rebase_frames(events, int(start_frame))
    if source_range:
        meta["source_range"] = source_range
    meta["range"] = {"start_t": 0.0, "end_t": round(duration, 6)}
    return {**payload, "events": events, "meta": meta}


def normalize_speech(
    payload: dict[str, Any],
    *,
    start: float,
    duration: float,
) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    for segment in payload.get("segments") or []:
        seg_start = _shift(segment["start"], start)
        seg_end = _shift(segment["end"], start)
        if seg_end < 0 or seg_start > duration:
            continue
        segments.append(
            {
                **segment,
                "start": max(0.0, seg_start),
                "end": min(duration, seg_end),
            }
        )
    output = {**payload, "segments": segments}
    if payload.get("range") is not None:
        output["source_range"] = payload["range"]
    output["range"] = {"start_t": 0.0, "end_t": round(duration, 6)}
    return output


def normalize_intent_pairs(
    payload: Any,
    *,
    start: float,
    duration: float,
) -> Any:
    if isinstance(payload, dict):
        key = "action_intent_pairs" if "action_intent_pairs" in payload else "pairs"
        pairs = payload.get(key) or []
    else:
        key = None
        pairs = payload

    normalized: list[dict[str, Any]] = []
    for pair in pairs:
        pair_start = _shift(pair["start_t"], start)
        pair_end = _shift(pair["end_t"], start)
        if pair_end < 0 or pair_start > duration:
            continue
        normalized.append(
            {
                **pair,
                "start_t": max(0.0, pair_start),
                "end_t": min(duration, pair_end),
            }
        )

    if key is None:
        return normalized
    return {**payload, key: normalized}


def normalize_final_events(
    run_dir: Path | str,
    output_dir: Path | str | None = None,
) -> dict[str, int]:
    run_dir = Path(run_dir)
    output_dir = Path(output_dir) if output_dir is not None else run_dir
    selection = load_project_selection(run_dir)
    start = float(selection.screen.start)
    duration = round(float(selection.screen.end) - start, 6)
    roi = selection.screen.roi

    cursor_events = normalize_cursor_events(
        _read_jsonl(run_dir / "trace" / "cursor" / "cursor_events.jsonl"),
        start=start,
        duration=duration,
        roi_x=float(roi.x),
        roi_y=float(roi.y),
    )
    _write_jsonl(output_dir / "cursor" / "final_cursor_events.jsonl", cursor_events)

    mouse_events = normalize_span_events(
        _read_jsonl(run_dir / "trace" / "cursor" / "mouse_events.jsonl"),
        start=start,
        duration=duration,
    )
    _write_jsonl(output_dir / "cursor" / "final_mouse_events.jsonl", mouse_events)

    keystrokes = normalize_keystrokes(
        _read_json(run_dir / "trace" / "keystrokes" / "keystrokes.json"),
        start=start,
        duration=duration,
    )
    _write_json(output_dir / "keystrokes" / "final_keystrokes.json", keystrokes)

    for source_name, final_name in (
        ("speech_full.json", "final_speech_full.json"),
        ("speech_trimmed.json", "final_speech_trimmed.json"),
    ):
        speech = normalize_speech(
            _read_json(run_dir / "trace" / "intent" / source_name),
            start=start,
            duration=duration,
        )
        _write_json(output_dir / "intent" / final_name, speech)

    pairs = normalize_intent_pairs(
        _read_json(run_dir / "trace" / "intent" / "action_intent_pairs.json"),
        start=start,
        duration=duration,
    )
    _write_json(output_dir / "intent" / "final_action_intent_pairs.json", pairs)

    summary_final = output_dir / "summary" / "final_summary.json"
    summary_final.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(run_dir / "trace" / "summary" / "summary.json", summary_final)

    counts = {
        "cursor": len(cursor_events),
        "mouse": len(mouse_events),
        "keyboard": len(keystrokes["events"]),
        "intent_pairs": len(
            pairs["action_intent_pairs"] if isinstance(pairs, dict) else pairs
        ),
    }
    _write_json(
        run_dir / "trace" / "normalization_summary.json",
        {
            "time_offset_s": start,
            "clip_duration_s": duration,
            "roi_offset": {"x": roi.x, "y": roi.y},
            "counts": counts,
        },
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Processing run directory")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Published final-data directory (default: run_dir)",
    )
    args = parser.parse_args()

    counts = normalize_final_events(args.run_dir, args.output_dir)
    print(
        "Normalized final artifacts: "
        + ", ".join(f"{name}={count}" for name, count in counts.items())
    )


if __name__ == "__main__":
    main()
