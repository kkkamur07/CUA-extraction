"""Provider registry — OpenAI API for ASR + LLM."""

from __future__ import annotations

from . import config
from .base import IntentModel, Transcriber, TranscriptSegment  # noqa: F401
from .openai_compat import OpenAICompatChat, OpenAICompatTranscriber

TRANSCRIBERS: dict[str, type[Transcriber]] = {
    "openai": OpenAICompatTranscriber,
}

INTENT_MODELS: dict[str, type[IntentModel]] = {
    "openai": OpenAICompatChat,
}


def get_transcriber() -> Transcriber:
    # Always use OpenAI Whisper API (legacy local backends remapped).
    import os

    os.environ["ASR_PROVIDER"] = "openai"
    model = (config.get("ASR_MODEL") or "whisper-1").strip()
    if model in {"base", "tiny", "small", "medium", "large", "large-v2", "large-v3", "higgs"}:
        model = "whisper-1"
    os.environ["ASR_MODEL"] = model
    return OpenAICompatTranscriber()


def get_intent_model() -> IntentModel:
    name = (config.get("LLM_PROVIDER") or "openai").strip().lower()
    if name != "openai":
        raise ValueError("LLM_PROVIDER must be 'openai' (OpenAI API only)")
    return OpenAICompatChat()
