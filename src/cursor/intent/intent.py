"""Intent extraction via in-tree ``cursor.intent.audio_intent`` pipeline.

Writes ``intent/speech_full.json``, ``intent/speech_trimmed.json``,
``summary/summary.json``, and ``intent/action_intent_pairs.json``.
ASR + LLM use the OpenAI API.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import cv2

from ..keypress.keystrokes import resolve_video_path
from ..workflow.workflow import (
    ACTION_INTENT_PAIRS_FILENAME,
    SPEECH_FULL_FILENAME,
    SPEECH_TRIMMED_FILENAME,
    SUMMARY_FILENAME,
    load_project_selection,
)
from . import audio_intent
from .speech_types import SpeechArtifact, SpeechRange, SpeechSegment

DEFAULT_ASR_PROVIDER = "openai"
DEFAULT_ASR_MODEL = "whisper-1"


def _sync_asr_env() -> None:
    os.environ["ASR_PROVIDER"] = DEFAULT_ASR_PROVIDER
    model = (
        os.environ.get("ASR_MODEL")
        or os.environ.get("CURSOR_ASR_MODEL")
        or DEFAULT_ASR_MODEL
    ).strip()
    if model in {
        "base", "tiny", "small", "medium", "large", "large-v2", "large-v3",
        "higgs", "bosonai/higgs-audio-v3-stt",
    }:
        model = DEFAULT_ASR_MODEL
    os.environ["ASR_MODEL"] = model
    os.environ["CURSOR_ASR_BACKEND"] = DEFAULT_ASR_PROVIDER
    os.environ["CURSOR_ASR_MODEL"] = model


def apply_asr_overrides(
    asr_provider: str | None = None,
    asr_model: str | None = None,
) -> None:
    # Provider is always OpenAI; allow model override (e.g. whisper-1).
    if asr_model:
        os.environ["ASR_MODEL"] = asr_model
        os.environ["CURSOR_ASR_MODEL"] = asr_model
    _sync_asr_env()



def video_duration_s(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    try:
        n = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    finally:
        cap.release()
    if n > 0 and fps > 1e-6:
        return n / fps
    raise RuntimeError(f"could not read duration from {video_path}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def segments_from_job(transcript: list[Any]) -> list[SpeechSegment]:
    out: list[SpeechSegment] = []
    for s in transcript:
        if hasattr(s, "start_t"):
            text = str(getattr(s, "text", "")).strip()
            if not text:
                continue
            out.append(
                SpeechSegment(
                    start=float(s.start_t),
                    end=float(s.end_t),
                    text=text,
                )
            )
            continue
        if isinstance(s, dict):
            text = str(s.get("text", "")).strip()
            if not text:
                continue
            start = float(s.get("start_t", s.get("start", 0.0)))
            end = float(s.get("end_t", s.get("end", start)))
            out.append(SpeechSegment(start=start, end=end, text=text))
    return out


def _filter_range(
    segments: list[SpeechSegment], start_t: float, end_t: float
) -> list[SpeechSegment]:
    return [s for s in segments if not (s.end < start_t or s.start > end_t)]


def write_intent_artifacts(
    run_dir: Path,
    job: audio_intent.AudioJob,
    *,
    start_t: float,
    end_t: float,
) -> dict[str, Path]:
    """Map a finished AudioJob into run-dir speech/summary/pairs files."""
    if job.state != "done" or not job.doc:
        raise RuntimeError(job.error or f"audio_intent failed ({job.state})")

    provider = (job.doc.get("providers") or {}).get("asr")
    segments = segments_from_job(job.transcript)
    trimmed_segs = _filter_range(segments, start_t, end_t)

    full = SpeechArtifact(
        text=" ".join(s.text for s in segments),
        segments=segments,
        range=SpeechRange(start_t=start_t, end_t=end_t),
        provider=provider if isinstance(provider, dict) else None,
    )
    trimmed = SpeechArtifact(
        text=" ".join(s.text for s in trimmed_segs),
        segments=trimmed_segs,
        range=SpeechRange(start_t=start_t, end_t=end_t),
        provider=provider if isinstance(provider, dict) else None,
    )

    speech_full = run_dir / SPEECH_FULL_FILENAME
    speech_trimmed = run_dir / SPEECH_TRIMMED_FILENAME
    summary_path = run_dir / SUMMARY_FILENAME
    pairs_path = run_dir / ACTION_INTENT_PAIRS_FILENAME

    _write_json(speech_full, full.to_dict())
    _write_json(speech_trimmed, trimmed.to_dict())
    _write_json(
        summary_path,
        {
            "summary": job.task_summary,
            "provider": (job.doc.get("providers") or {}).get("llm"),
        },
    )
    pairs = [
        {
            "start_t": float(iv["start_t"]),
            "end_t": float(iv["end_t"]),
            "action": str(iv.get("action", "")),
            "intent": str(iv.get("intent", "")),
            "quote": str(iv.get("quote", "")),
        }
        for iv in (job.intents or [])
        if not (float(iv["end_t"]) < start_t or float(iv["start_t"]) > end_t)
    ]
    _write_json(
        pairs_path,
        {
            "action_intent_pairs": pairs,
            "source": "cursor.intent.audio_intent",
            "asr": provider,
        },
    )
    return {
        "speech_full": speech_full,
        "speech_trimmed": speech_trimmed,
        "summary": summary_path,
        "action_intent_pairs": pairs_path,
    }


def extract_intent(
    run_dir: Path | str,
    *,
    chunk_s: int = 600,
    language: str | None = None,
    asr_provider: str | None = None,
    asr_model: str | None = None,
) -> dict[str, Path]:
    """Blocking ASR + summary + pairs. Prefer ``run_intent_job`` for UI progress."""
    apply_asr_overrides(asr_provider, asr_model)
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Processing run directory not found: {run_dir}")

    selection = load_project_selection(run_dir)
    video_path = resolve_video_path(selection.video)
    start_t = float(selection.screen.start)
    end_t = float(selection.screen.end)
    job = audio_intent.AudioJob(
        video_path=str(video_path),
        duration=video_duration_s(video_path),
        chunk_s=int(chunk_s),
        language=language,
        start_t=start_t,
        end_t=end_t,
    )
    audio_intent.run(job)
    return write_intent_artifacts(
        run_dir,
        job,
        start_t=start_t,
        end_t=end_t,
    )
