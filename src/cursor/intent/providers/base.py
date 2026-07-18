"""Provider interfaces. Implement these two classes to add a new provider."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TranscriptSegment:
    start_t: float
    end_t: float
    text: str

    def as_dict(self):
        return {"start_t": round(self.start_t, 3), "end_t": round(self.end_t, 3),
                "text": self.text}


class Transcriber(ABC):
    """Speech-to-text with segment-level timestamps."""

    name: str = "abstract"
    model: str = ""

    @abstractmethod
    def transcribe(self, wav_path: str, language: str | None = None) -> list[TranscriptSegment]:
        """Transcribe one audio file; timestamps are relative to that file."""

    def check(self) -> dict:
        """Cheap health check. Returns {'ok': bool, 'detail': str}."""
        return {"ok": True, "detail": "no check implemented"}

    def info(self) -> dict:
        return {"provider": self.name, "model": self.model}


class IntentModel(ABC):
    """LLM that answers with a JSON object."""

    name: str = "abstract"
    model: str = ""

    @abstractmethod
    def complete_json(self, system: str, user: str) -> dict:
        """Run one completion; must return the parsed JSON object."""

    def check(self) -> dict:
        return {"ok": True, "detail": "no check implemented"}

    def info(self) -> dict:
        return {"provider": self.name, "model": self.model}
