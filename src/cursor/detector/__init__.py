"""Cursor annotation persistence and YOLO Cursor observation extraction."""

from .annotations import save_cursor_annotation
from .cursor_events import DEFAULT_MODEL_PATH, extract_cursor_events
from .processor import read_frame

__all__ = [
    "DEFAULT_MODEL_PATH",
    "extract_cursor_events",
    "read_frame",
    "save_cursor_annotation",
]
