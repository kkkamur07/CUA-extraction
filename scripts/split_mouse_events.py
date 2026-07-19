"""Split M1/M2 overlay controls from keyboard events.

M1 and M2 are mouse buttons in the on-screen keyboard overlay, not keyboard
keys. This script preserves the source artifact, rewrites the final keyboard
artifact without those controls, and writes normalized mouse-button events.

Example:

    python3 scripts/split_mouse_events.py runs/solidworks-tut
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MOUSE_BUTTON_MAPPING = {
    "M1": "right",
    "M2": "left",
}


def _read_payload(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        events = raw.get("events")
        if not isinstance(events, list):
            raise ValueError(f"{path}: expected an events list")
        return raw
    if isinstance(raw, list):
        return {"events": raw}
    raise ValueError(f"{path}: expected a JSON object or list")


def split_events(events: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    keyboard_events: list[dict[str, Any]] = []
    mouse_events: list[dict[str, Any]] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        source_key = str(item.get("key", "")).upper()
        button = MOUSE_BUTTON_MAPPING.get(source_key)
        if button is None:
            keyboard_events.append(item)
            continue
        mouse_events.append(
            {
                "type": "mouse_button",
                "button": button,
                "press_t": float(item["press_t"]),
                "release_t": float(item["release_t"]),
                "source_key": source_key,
                "clipped": bool(item.get("clipped", False)),
            }
        )
    mouse_events.sort(key=lambda item: (item["press_t"], item["button"]))
    return keyboard_events, mouse_events


def write_artifacts(
    *,
    source_path: Path,
    raw_output: Path,
    keyboard_output: Path,
    mouse_output: Path,
    summary_output: Path,
) -> dict[str, int]:
    payload = _read_payload(source_path)
    events = payload["events"]
    keyboard_events, mouse_events = split_events(events)

    raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    keyboard_payload = {**payload, "events": keyboard_events}
    keyboard_output.parent.mkdir(parents=True, exist_ok=True)
    keyboard_output.write_text(
        json.dumps(keyboard_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    mouse_output.parent.mkdir(parents=True, exist_ok=True)
    mouse_output.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in mouse_events),
        encoding="utf-8",
    )

    counts = {
        "input": len(events),
        "keyboard": len(keyboard_events),
        "mouse": len(mouse_events),
    }
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(
        json.dumps(
            {
                "source": str(source_path),
                "raw_output": str(raw_output),
                "keyboard_output": str(keyboard_output),
                "mouse_output": str(mouse_output),
                "mouse_button_mapping": MOUSE_BUTTON_MAPPING,
                "counts": counts,
            },
            indent=2,
        )
        + "\n",
    )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Processing run directory")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--raw-output", type=Path, default=None)
    parser.add_argument("--keyboard-output", type=Path, default=None)
    parser.add_argument("--mouse-output", type=Path, default=None)
    parser.add_argument("--summary-output", type=Path, default=None)
    args = parser.parse_args()

    run_dir = args.run_dir
    final_keyboard = run_dir / "trace" / "keystrokes" / "keystrokes.json"
    raw_keyboard = run_dir / "keystrokes" / "raw_keystrokes.json"
    source_path = args.input or (raw_keyboard if raw_keyboard.is_file() else final_keyboard)
    raw_output = args.raw_output or raw_keyboard
    keyboard_output = args.keyboard_output or final_keyboard
    mouse_output = args.mouse_output or run_dir / "trace" / "cursor" / "mouse_events.jsonl"
    summary_output = (
        args.summary_output
        or run_dir / "trace" / "cursor" / "mouse_filter_summary.json"
    )

    if not source_path.is_file():
        raise FileNotFoundError(f"Keyboard artifact not found: {source_path}")
    counts = write_artifacts(
        source_path=source_path,
        raw_output=raw_output,
        keyboard_output=keyboard_output,
        mouse_output=mouse_output,
        summary_output=summary_output,
    )
    print(
        f"Keyboard events: {counts['input']} -> {counts['keyboard']}; "
        f"mouse events: {counts['mouse']}"
    )
    print(f"Keyboard output: {keyboard_output}")
    print(f"Mouse output: {mouse_output}")


if __name__ == "__main__":
    main()
