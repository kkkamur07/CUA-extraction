"""Async intent job with ``intent/intent_job.json`` progress for UI polling."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..keypress.keystrokes import resolve_video_path
from ..workflow.workflow import INTENT_JOB_FILENAME, load_project_selection
from . import audio_intent
from .intent import (
    apply_asr_overrides,
    video_duration_s,
    write_intent_artifacts,
)

POLL_INTERVAL_S = 0.35

_STATE_MSG = {
    "pending": "Starting…",
    "extracting": "Extracting audio…",
    "transcribing": "Transcribing speech…",
    "summarizing": "Generating Action–Intent pairs + summary…",
    "done": "Done",
    "error": "Failed",
}


def job_status_path(run_dir: Path | str) -> Path:
    return Path(run_dir) / INTENT_JOB_FILENAME


def write_job_status(run_dir: Path | str, payload: dict[str, Any]) -> Path:
    run_dir = Path(run_dir)
    path = job_status_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {**payload, "updated_at": time.time()}
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read_job_status(run_dir: Path | str) -> dict[str, Any] | None:
    path = job_status_path(run_dir)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return raw if isinstance(raw, dict) else None


def _message_for(job: audio_intent.AudioJob) -> str:
    base = _STATE_MSG.get(job.state, job.state)
    pct = max(0.0, min(1.0, float(job.progress or 0.0)))
    if job.state in {"extracting", "transcribing", "summarizing"}:
        return f"{base} {pct * 100:.0f}%"
    return base


def run_intent_job(
    run_dir: Path | str,
    *,
    chunk_s: int = 600,
    language: str | None = None,
    asr_provider: str | None = None,
    asr_model: str | None = None,
) -> dict[str, Any]:
    """Blocking entry: run audio_intent with progress file, then write artifacts."""
    run_dir = Path(run_dir)
    apply_asr_overrides(asr_provider, asr_model)
    write_job_status(
        run_dir,
        {
            "state": "starting",
            "progress": 0.0,
            "error": None,
            "message": "Loading selection…",
            "n_segments": 0,
            "n_intents": 0,
        },
    )

    try:
        selection = load_project_selection(run_dir)
        video_path = resolve_video_path(selection.video)
        duration = video_duration_s(video_path)
        start_t = float(selection.screen.start)
        end_t = float(selection.screen.end)
        job = audio_intent.AudioJob(
            video_path=str(video_path),
            duration=duration,
            chunk_s=int(chunk_s),
            language=language,
            start_t=start_t,
            end_t=end_t,
        )

        write_job_status(
            run_dir,
            {
                "state": "running",
                "progress": 0.0,
                "error": None,
                "message": f"Starting ASR ({start_t:.1f}s–{end_t:.1f}s)…",
                "n_segments": 0,
                "n_intents": 0,
                "duration_s": duration,
                "start_t": start_t,
                "end_t": end_t,
            },
        )

        thread = audio_intent.start(job)
        while thread.is_alive():
            write_job_status(
                run_dir,
                {
                    "state": job.state if job.state != "pending" else "running",
                    "progress": float(job.progress or 0.0),
                    "error": None,
                    "message": _message_for(job),
                    "n_segments": len(job.transcript or []),
                    "n_intents": len(job.intents or []),
                    "duration_s": duration,
                },
            )
            time.sleep(POLL_INTERVAL_S)
        thread.join()

        if job.state != "done":
            err = job.error or f"audio_intent failed ({job.state})"
            write_job_status(
                run_dir,
                {
                    "state": "error",
                    "progress": float(job.progress or 0.0),
                    "error": err,
                    "message": err,
                    "n_segments": len(job.transcript or []),
                    "n_intents": len(job.intents or []),
                },
            )
            return {
                "state": "error",
                "error": err,
                "progress": float(job.progress or 0.0),
            }

        paths = write_intent_artifacts(
            run_dir,
            job,
            start_t=start_t,
            end_t=end_t,
        )
        result = {
            "state": "done",
            "progress": 1.0,
            "error": None,
            "message": "Intent extraction finished",
            "n_segments": len(job.transcript or []),
            "n_intents": len(job.intents or []),
            "paths": {k: str(v) for k, v in paths.items()},
        }
        write_job_status(run_dir, result)
        return result
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        write_job_status(
            run_dir,
            {
                "state": "error",
                "progress": 0.0,
                "error": err,
                "message": err,
                "n_segments": 0,
                "n_intents": 0,
            },
        )
        return {"state": "error", "error": err, "progress": 0.0}
