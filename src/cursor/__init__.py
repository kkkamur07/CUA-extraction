"""Cursor observation extraction package."""

from __future__ import annotations

from typing import Any

__all__ = [
    "CropROI",
    "WorkflowSample",
    "assemble_workflow_sample",
    "extract_cursor_events",
    "extract_intent",
    "extract_keystrokes",
    "load_project_selection",
    "run_pipeline",
    "write_stub_workflow_sample",
]


def __getattr__(name: str) -> Any:
    # Lazy imports so intent/keystroke CLIs work without loading torch/YOLO.
    if name == "extract_cursor_events":
        from .detector import extract_cursor_events

        return extract_cursor_events
    if name == "extract_intent":
        from .intent import extract_intent

        return extract_intent
    if name == "extract_keystrokes":
        from .keypress import extract_keystrokes

        return extract_keystrokes
    if name in {
        "CropROI",
        "WorkflowSample",
        "assemble_workflow_sample",
        "load_project_selection",
        "run_pipeline",
        "write_stub_workflow_sample",
    }:
        from . import workflow as wf

        return getattr(wf, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
