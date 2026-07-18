"""Keyboard ROI keystroke extraction (CV analysis + layouts)."""

from pathlib import Path

from . import analysis, cvdetect
from .keystrokes import (
    DEFAULT_LAYOUT_NAME,
    DEFAULT_STRIDE,
    extract_keystrokes,
    extract_keystrokes_from_selection,
    read_job_status,
    run_keystroke_job,
    write_job_status,
)

PACKAGE_ROOT = Path(__file__).resolve().parent
LAYOUTS_DIR = PACKAGE_ROOT / "layouts"

__all__ = [
    "DEFAULT_LAYOUT_NAME",
    "DEFAULT_STRIDE",
    "LAYOUTS_DIR",
    "PACKAGE_ROOT",
    "analysis",
    "cvdetect",
    "extract_keystrokes",
    "extract_keystrokes_from_selection",
    "read_job_status",
    "run_keystroke_job",
    "write_job_status",
]
