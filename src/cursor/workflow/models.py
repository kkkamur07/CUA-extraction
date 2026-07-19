"""Data structures used by cursor extraction and Workflow samples."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class CropROI:
    """Rectangular application area selected from a Source frame."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class TrackSelection:
    """ROI and useful time range for one track on a Source frame."""

    roi: CropROI
    start: float
    end: float
    preview_timestamp: float


@dataclass(frozen=True)
class CornerMasks:
    """White rectangles in screen-crop coordinates for final-video redaction."""

    bottom_left: CropROI
    bottom_right: CropROI


@dataclass(frozen=True)
class ProjectSelection:
    """Shared configuration for one Processing run (written as selection.json)."""

    id: str
    video: str
    fps: float
    frame_width: int
    frame_height: int
    preview_timestamp: float
    roi: CropROI
    start: float
    end: float
    screen: TrackSelection
    keyboard: TrackSelection
    corner_masks: CornerMasks


@dataclass(frozen=True)
class ActionIntentPair:
    """One labeled tutorial step binding an Action and Intent to a time range.

    Optional ``quote`` is verbatim transcript evidence (keyboard_detector
    audio-intent convention).
    """

    action: str
    intent: str
    start_t: float
    end_t: float
    quote: str = ""


@dataclass(frozen=True)
class CursorRawEvent:
    """Cursor observation published as a Raw event.

    ``x`` / ``y`` are full-frame source pixels (Crop ROI offset applied).
    """

    t: float
    x: float
    y: float
    confidence: float
    click_candidate: bool = False
    type: Literal["cursor"] = "cursor"


@dataclass(frozen=True)
class KeystrokeRawEvent:
    """Keystroke published as a Raw event (physical press–release)."""

    key: str
    press_t: float
    release_t: float
    clipped: bool = False
    type: Literal["keystroke"] = "keystroke"


RawEvent = CursorRawEvent | KeystrokeRawEvent


@dataclass
class WorkflowSample:
    """Published unit for one Processing run."""

    id: str
    summary: str = ""
    action_intent_pairs: list[ActionIntentPair] = field(default_factory=list)
    raw_events: list[RawEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "summary": self.summary,
            "action_intent_pairs": [asdict(pair) for pair in self.action_intent_pairs],
            "raw_events": [asdict(event) for event in self.raw_events],
        }
