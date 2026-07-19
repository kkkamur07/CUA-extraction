"""Processing run artifact contract and Workflow sample stub assembler.

Layout under ``runs/<id>/``:

- ``selection.json`` — Project selection (Crop ROI, Keyboard ROI, time range)
- ``trace/workflow_sample.json`` — assembled intermediate Workflow sample
- ``keystrokes/raw_keystrokes.json`` — unfiltered keyboard-overlay detections
- ``trace/keystrokes/keystrokes.json`` — filtered keyboard events
- ``trace/keystrokes/keystroke_job.json`` — async Keystroke job progress
- ``final_video.mp4`` — cropped, trimmed, white-masked final video
- ``final_video.json`` — final-video render manifest
- ``cursor/raw_cursor_events.jsonl`` — unfiltered cursor detector output
- ``trace/cursor/cursor_events.jsonl`` — filtered cursor events
- ``trace/cursor/mouse_events.jsonl`` — normalized M1/M2 mouse-button events
- ``trace/final_processing_summary.json`` — finalization trace
- ``trace/intent/speech_full.json`` — full-video ASR
- ``trace/intent/speech_trimmed.json`` — trimmed-range ASR
- ``trace/intent/action_intent_pairs.json`` — Action–Intent pairs
- ``trace/intent/intent_job.json`` — async Intent job progress
- ``trace/summary/summary.json`` — intermediate task summary
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    CornerMasks,
    CropROI,
    ProjectSelection,
    TrackSelection,
    WorkflowSample,
)

# Exact artifact names for a Processing run directory (relative to run root).
# Raw and final artifacts stay visible at the run root; intermediate traces live
# under trace/ so the published run is easy to inspect.
SELECTION_FILENAME = "selection.json"
RAW_KEYSTROKES_FILENAME = "keystrokes/raw_keystrokes.json"
KEYSTROKES_FILENAME = "trace/keystrokes/keystrokes.json"
KEYSTROKE_JOB_FILENAME = "trace/keystrokes/keystroke_job.json"
MOUSE_EVENTS_FILENAME = "trace/cursor/mouse_events.jsonl"
INTENT_JOB_FILENAME = "trace/intent/intent_job.json"
RAW_CURSOR_EVENTS_FILENAME = "cursor/raw_cursor_events.jsonl"
CURSOR_EVENTS_FILENAME = "trace/cursor/cursor_events.jsonl"
EVENT_PROCESSING_SUMMARY_FILENAME = "trace/events/processing_summary.json"
FINAL_PROCESSING_SUMMARY_FILENAME = "events/final_processing_summary.json"
FINAL_CURSOR_EVENTS_FILENAME = "cursor/final_cursor_events.jsonl"
FINAL_MOUSE_EVENTS_FILENAME = "cursor/final_mouse_events.jsonl"
FINAL_KEYSTROKES_FILENAME = "keystrokes/final_keystrokes.json"
FINAL_SPEECH_FULL_FILENAME = "intent/final_speech_full.json"
FINAL_SPEECH_TRIMMED_FILENAME = "intent/final_speech_trimmed.json"
FINAL_ACTION_INTENT_PAIRS_FILENAME = "intent/final_action_intent_pairs.json"
FINAL_SUMMARY_FILENAME = "summary/final_summary.json"
FINAL_WORKFLOW_SAMPLE_FILENAME = "final_workflow_sample.json"
FINAL_VIDEO_FILENAME = "final_video.mp4"
FINAL_VIDEO_MANIFEST_FILENAME = "final_video.json"
SPEECH_FULL_FILENAME = "trace/intent/speech_full.json"
SPEECH_TRIMMED_FILENAME = "trace/intent/speech_trimmed.json"
ACTION_INTENT_PAIRS_FILENAME = "trace/intent/action_intent_pairs.json"
WORKFLOW_SAMPLE_FILENAME = "trace/workflow_sample.json"
SUMMARY_FILENAME = "trace/summary/summary.json"


def _roi_from_dict(raw: dict[str, Any]) -> CropROI:
    return CropROI(
        x=int(raw["x"]),
        y=int(raw["y"]),
        width=int(raw["width"]),
        height=int(raw["height"]),
    )


def _track_from_dict(raw: dict[str, Any]) -> TrackSelection:
    return TrackSelection(
        roi=_roi_from_dict(raw["roi"]),
        start=float(raw["start"]),
        end=float(raw["end"]),
        preview_timestamp=float(raw["preview_timestamp"]),
    )


def _default_corner_masks(screen: CropROI, keyboard: CropROI) -> CornerMasks:
    """Choose useful defaults while keeping old selections loadable."""
    left = max(screen.x, keyboard.x)
    top = max(screen.y, keyboard.y)
    right = min(screen.x + screen.width, keyboard.x + keyboard.width)
    bottom = min(screen.y + screen.height, keyboard.y + keyboard.height)
    if left < right and top < bottom:
        bottom_left = CropROI(
            x=left - screen.x if left == screen.x else 0,
            y=top - screen.y,
            width=right - screen.x,
            height=screen.height - (top - screen.y),
        )
    else:
        width = min(360, screen.width)
        height = min(200, screen.height)
        bottom_left = CropROI(
            x=0,
            y=screen.height - height,
            width=width,
            height=height,
        )

    timer_width = min(300, screen.width)
    timer_top = min(screen.height, max(0, int(round(screen.height * 0.45))))
    return CornerMasks(
        bottom_left=bottom_left,
        bottom_right=CropROI(
            x=screen.width - timer_width,
            y=timer_top,
            width=timer_width,
            height=screen.height - timer_top,
        ),
    )


def _corner_masks_from_dict(
    raw: Any,
    screen: CropROI,
    keyboard: CropROI,
) -> CornerMasks:
    if isinstance(raw, dict):
        left = raw.get("bottom_left")
        right = raw.get("bottom_right")
        if isinstance(left, dict) and isinstance(right, dict):
            try:
                return CornerMasks(
                    bottom_left=_roi_from_dict(left),
                    bottom_right=_roi_from_dict(right),
                )
            except (KeyError, TypeError, ValueError):
                pass
    return _default_corner_masks(screen, keyboard)


def load_project_selection(run_dir: Path | str) -> ProjectSelection:
    """Load ``selection.json`` for a Processing run directory."""
    run_dir = Path(run_dir)
    path = run_dir / SELECTION_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Missing project selection: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid selection.json (expected object): {path}")

    run_id = str(raw.get("id") or run_dir.name)

    if "screen" in raw and isinstance(raw["screen"], dict):
        screen = _track_from_dict(raw["screen"])
    else:
        screen = TrackSelection(
            roi=_roi_from_dict(raw["roi"]),
            start=float(raw["start"]),
            end=float(raw["end"]),
            preview_timestamp=float(raw.get("preview_timestamp", raw["start"])),
        )

    if "keyboard" in raw and isinstance(raw["keyboard"], dict):
        keyboard = _track_from_dict(raw["keyboard"])
    else:
        frame_height = int(raw["frame_height"])
        keyboard = TrackSelection(
            roi=CropROI(
                x=0,
                y=0,
                width=int(raw["frame_width"]),
                height=min(240, frame_height),
            ),
            start=screen.start,
            end=screen.end,
            preview_timestamp=screen.preview_timestamp,
        )
    corner_masks = _corner_masks_from_dict(
        raw.get("corner_masks"),
        screen.roi,
        keyboard.roi,
    )

    return ProjectSelection(
        id=run_id,
        video=str(raw["video"]),
        fps=float(raw["fps"]),
        frame_width=int(raw["frame_width"]),
        frame_height=int(raw["frame_height"]),
        preview_timestamp=float(raw.get("preview_timestamp", screen.preview_timestamp)),
        roi=_roi_from_dict(raw["roi"]) if "roi" in raw else screen.roi,
        start=float(raw.get("start", screen.start)),
        end=float(raw.get("end", screen.end)),
        screen=screen,
        keyboard=keyboard,
        corner_masks=corner_masks,
    )


def write_stub_workflow_sample(run_dir: Path | str) -> Path:
    """Write an empty Workflow sample under ``runs/<id>/workflow_sample.json``.

    Loads the existing project selection so the sample ``id`` matches the run,
    then writes a valid stub with empty summary, pairs, and raw events.
    """
    run_dir = Path(run_dir)
    selection = load_project_selection(run_dir)
    sample = WorkflowSample(id=selection.id)
    out_path = run_dir / WORKFLOW_SAMPLE_FILENAME
    out_path.write_text(
        json.dumps(sample.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path
