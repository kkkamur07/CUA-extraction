"""Processing run contract, sample types, and pipeline orchestration."""

from __future__ import annotations

from typing import Any

from .models import (
    ActionIntentPair,
    CropROI,
    CursorRawEvent,
    KeystrokeRawEvent,
    ProjectSelection,
    RawEvent,
    TrackSelection,
    WorkflowSample,
)
from .workflow import (
    ACTION_INTENT_PAIRS_FILENAME,
    CURSOR_EVENTS_FILENAME,
    INTENT_JOB_FILENAME,
    KEYSTROKE_JOB_FILENAME,
    KEYSTROKES_FILENAME,
    SELECTION_FILENAME,
    SPEECH_FULL_FILENAME,
    SPEECH_TRIMMED_FILENAME,
    SUMMARY_FILENAME,
    WORKFLOW_SAMPLE_FILENAME,
    load_project_selection,
    write_stub_workflow_sample,
)

__all__ = [
    "ACTION_INTENT_PAIRS_FILENAME",
    "ALL_STEPS",
    "CURSOR_EVENTS_FILENAME",
    "CropROI",
    "INTENT_JOB_FILENAME",
    "KEYSTROKE_JOB_FILENAME",
    "KEYSTROKES_FILENAME",
    "ActionIntentPair",
    "CursorRawEvent",
    "KeystrokeRawEvent",
    "PipelineError",
    "PipelineResult",
    "ProjectSelection",
    "RawEvent",
    "SELECTION_FILENAME",
    "SPEECH_FULL_FILENAME",
    "SPEECH_TRIMMED_FILENAME",
    "STEP_ASSEMBLE",
    "STEP_CURSOR",
    "STEP_INTENT",
    "STEP_KEYSTROKES",
    "SUMMARY_FILENAME",
    "StepResult",
    "TrackSelection",
    "WORKFLOW_SAMPLE_FILENAME",
    "WorkflowSample",
    "assemble_workflow_sample",
    "load_action_intent_pairs",
    "load_cursor_raw_events",
    "load_keystroke_raw_events",
    "load_project_selection",
    "load_summary_text",
    "run_pipeline",
    "write_stub_workflow_sample",
]

_PIPELINE_EXPORTS = {
    "ALL_STEPS",
    "STEP_ASSEMBLE",
    "STEP_CURSOR",
    "STEP_INTENT",
    "STEP_KEYSTROKES",
    "PipelineError",
    "PipelineResult",
    "StepResult",
    "assemble_workflow_sample",
    "load_action_intent_pairs",
    "load_cursor_raw_events",
    "load_keystroke_raw_events",
    "load_summary_text",
    "run_pipeline",
}


def __getattr__(name: str) -> Any:
    if name in _PIPELINE_EXPORTS:
        from . import pipeline

        return getattr(pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
