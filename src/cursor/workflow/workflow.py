"""Processing run artifact contract and Workflow sample stub assembler.

Layout under ``runs/<id>/``:

- ``selection.json`` — Project selection (Crop ROI, Keyboard ROI, time range)
- ``workflow_sample.json`` — published Workflow sample
- ``keystrokes/keystrokes.json`` — Keystroke Raw events
- ``keystrokes/keystroke_job.json`` — async Keystroke job progress (UI polling)
- ``cursor/cursor_events.jsonl`` — one Cursor observation JSON object per line
- ``intent/speech_full.json`` — full-video ASR (feeds Workflow summary)
- ``intent/speech_trimmed.json`` — trimmed-range ASR (feeds Action–Intent pairs)
- ``intent/action_intent_pairs.json`` — list of Action–Intent pairs
- ``intent/intent_job.json`` — async Intent job progress (UI polling)
- ``summary/summary.json`` — optional task summary; prefer field on Workflow sample
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    CropROI,
    ProjectSelection,
    TrackSelection,
    WorkflowSample,
)

# Exact intermediate names for a Processing run directory (relative to run root).
SELECTION_FILENAME = "selection.json"
KEYSTROKES_FILENAME = "keystrokes/keystrokes.json"
KEYSTROKE_JOB_FILENAME = "keystrokes/keystroke_job.json"
INTENT_JOB_FILENAME = "intent/intent_job.json"
CURSOR_EVENTS_FILENAME = "cursor/cursor_events.jsonl"
SPEECH_FULL_FILENAME = "intent/speech_full.json"
SPEECH_TRIMMED_FILENAME = "intent/speech_trimmed.json"
ACTION_INTENT_PAIRS_FILENAME = "intent/action_intent_pairs.json"
WORKFLOW_SAMPLE_FILENAME = "workflow_sample.json"
SUMMARY_FILENAME = "summary/summary.json"


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
