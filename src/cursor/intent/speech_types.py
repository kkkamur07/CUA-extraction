"""Speech artifact dataclasses for dual ASR extraction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class SpeechSegment:
    """One timed transcript span (absolute times in the source video)."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class SpeechRange:
    """Time span covered by a speech artifact (source-video seconds)."""

    start_t: float
    end_t: float | None


@dataclass(frozen=True)
class SpeechArtifact:
    """Intermediate ASR artifact written under a Processing run directory."""

    text: str
    segments: list[SpeechSegment]
    range: SpeechRange
    provider: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "text": self.text,
            "segments": [asdict(segment) for segment in self.segments],
            "range": {"start_t": self.range.start_t, "end_t": self.range.end_t},
        }
        if self.provider:
            out["provider"] = self.provider
        return out


class AsrBackend(Protocol):
    def transcribe(self, audio_path: Path) -> list[dict[str, Any]] | list[SpeechSegment]:
        """Transcribe audio; segment times are relative to the audio file start."""
