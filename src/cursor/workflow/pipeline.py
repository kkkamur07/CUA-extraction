"""Processing run orchestrator: extract modalities and assemble Workflow sample.

Given a run directory with ``selection.json``, runs (or optionally skips)
Keystroke extraction, Cursor YOLO, and OpenAI Intent extraction, then writes
``workflow_sample.json``.

Cursor observations and Keystrokes appear only in ``raw_events``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..detector.cursor_events import extract_cursor_events
from ..intent.intent import extract_intent
from ..keypress.keystrokes import extract_keystrokes
from .models import (
    ActionIntentPair,
    CursorRawEvent,
    KeystrokeRawEvent,
    WorkflowSample,
)
from .workflow import (
    ACTION_INTENT_PAIRS_FILENAME,
    CURSOR_EVENTS_FILENAME,
    KEYSTROKES_FILENAME,
    SPEECH_FULL_FILENAME,
    SPEECH_TRIMMED_FILENAME,
    SUMMARY_FILENAME,
    WORKFLOW_SAMPLE_FILENAME,
    load_project_selection,
)

# Step names used in status / error reporting (stable API surface).
STEP_KEYSTROKES = "keystrokes"
STEP_CURSOR = "cursor"
STEP_INTENT = "intent"
STEP_ASSEMBLE = "assemble"

ALL_STEPS = (
    STEP_KEYSTROKES,
    STEP_CURSOR,
    STEP_INTENT,
    STEP_ASSEMBLE,
)


@dataclass
class StepResult:
    """Outcome of one modality (or assemble) step in a Processing run."""

    name: str
    status: str  # ok | skipped | error
    path: str | None = None
    paths: list[str] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"name": self.name, "status": self.status}
        if self.path is not None:
            out["path"] = self.path
        if self.paths is not None:
            out["paths"] = self.paths
        if self.error is not None:
            out["error"] = self.error
        return out


@dataclass
class PipelineResult:
    """Aggregated Processing run status for CLI / HTTP callers."""

    run_id: str
    run_dir: str
    ok: bool
    steps: list[StepResult] = field(default_factory=list)
    sample_path: str | None = None
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "run_id": self.run_id,
            "run_dir": self.run_dir,
            "sample_path": self.sample_path,
            "errors": self.errors,
            "steps": [step.to_dict() for step in self.steps],
        }


class PipelineError(RuntimeError):
    """Raised when one or more required Processing run steps failed."""

    def __init__(self, result: PipelineResult) -> None:
        self.result = result
        failed = ", ".join(sorted(result.errors)) or "unknown"
        super().__init__(
            f"Processing run failed for {result.run_id}: "
            f"modality failure(s): {failed}"
        )


def load_keystroke_raw_events(run_dir: Path) -> list[KeystrokeRawEvent]:
    """Load Keystroke Raw events from ``keystrokes/keystrokes.json`` (events list)."""
    path = run_dir / KEYSTROKES_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Missing Keystroke artifact: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        items = raw.get("events", [])
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError(f"Invalid {KEYSTROKES_FILENAME}: expected object or list")
    if not isinstance(items, list):
        raise ValueError(f"Invalid {KEYSTROKES_FILENAME}: events must be a list")

    events: list[KeystrokeRawEvent] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Keystroke at index {i} must be an object")
        events.append(
            KeystrokeRawEvent(
                key=str(item["key"]),
                press_t=float(item["press_t"]),
                release_t=float(item["release_t"]),
                clipped=bool(item.get("clipped", False)),
            )
        )
    return events


def load_cursor_raw_events(run_dir: Path) -> list[CursorRawEvent]:
    """Load Cursor observation Raw events from ``cursor/cursor_events.jsonl``."""
    path = run_dir / CURSOR_EVENTS_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Missing Cursor observation artifact: {path}")
    events: list[CursorRawEvent] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON on line {line_no} of {CURSOR_EVENTS_FILENAME}: {exc}"
            ) from exc
        if not isinstance(item, dict):
            raise ValueError(f"Cursor event on line {line_no} must be an object")
        events.append(
            CursorRawEvent(
                t=float(item["t"]),
                x=float(item["x"]),
                y=float(item["y"]),
                confidence=float(item["confidence"]),
                click_candidate=bool(item.get("click_candidate", False)),
            )
        )
    return events


def load_summary_text(run_dir: Path) -> str:
    """Load Workflow summary text from ``summary/summary.json``."""
    path = run_dir / SUMMARY_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Missing Workflow summary artifact: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid {SUMMARY_FILENAME}: expected object")
    text = str(raw.get("summary") or "").strip()
    if not text:
        raise ValueError(f"{path} has empty summary text")
    return text


def load_action_intent_pairs(run_dir: Path) -> list[ActionIntentPair]:
    """Load Action–Intent pairs from ``intent/action_intent_pairs.json``."""
    path = run_dir / ACTION_INTENT_PAIRS_FILENAME
    if not path.is_file():
        raise FileNotFoundError(f"Missing Action–Intent pairs artifact: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        items = raw.get("pairs") or raw.get("action_intent_pairs") or []
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError(
            f"Invalid {ACTION_INTENT_PAIRS_FILENAME}: expected list or object"
        )
    if not isinstance(items, list):
        raise ValueError(f"Invalid {ACTION_INTENT_PAIRS_FILENAME}: pairs must be a list")

    pairs: list[ActionIntentPair] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Pair at index {i} must be an object")
        pairs.append(
            ActionIntentPair(
                action=str(item["action"]),
                intent=str(item["intent"]),
                start_t=float(item["start_t"]),
                end_t=float(item["end_t"]),
                quote=str(item.get("quote") or ""),
            )
        )
    return pairs


def assemble_workflow_sample(run_dir: Path | str) -> Path:
    """Assemble ``workflow_sample.json`` from intermediate artifacts.

    - ``summary`` from ``summary.json``
    - ``action_intent_pairs`` from ``action_intent_pairs.json``
    - ``raw_events`` from cursor + keystroke artifacts only (typed)

    Overwrites any existing sample for this run id.
    """
    run_dir = Path(run_dir)
    selection = load_project_selection(run_dir)
    summary = load_summary_text(run_dir)
    pairs = load_action_intent_pairs(run_dir)
    cursor_events = load_cursor_raw_events(run_dir)
    keystroke_events = load_keystroke_raw_events(run_dir)

    # Interleave by time: cursor by t, keystroke by press_t.
    raw_events: list[CursorRawEvent | KeystrokeRawEvent] = []
    raw_events.extend(cursor_events)
    raw_events.extend(keystroke_events)

    def _sort_key(event: CursorRawEvent | KeystrokeRawEvent) -> float:
        if isinstance(event, CursorRawEvent):
            return event.t
        return event.press_t

    raw_events.sort(key=_sort_key)

    sample = WorkflowSample(
        id=selection.id,
        summary=summary,
        action_intent_pairs=pairs,
        raw_events=raw_events,
    )
    out_path = run_dir / WORKFLOW_SAMPLE_FILENAME
    # Persist via to_dict so Raw event ``type`` fields stay explicit.
    payload = sample.to_dict()
    # Ensure typed raw events use asdict (includes type discriminator).
    payload["raw_events"] = [asdict(event) for event in raw_events]
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path


def _artifact_exists(run_dir: Path, *names: str) -> bool:
    return all((run_dir / name).is_file() for name in names)


def _run_step(
    name: str,
    run: Callable[[], Path | tuple[Path, ...] | list[Path | str]],
) -> StepResult:
    """Execute one modality step; capture failures without aborting the run."""
    try:
        result = run()
    except Exception as exc:  # noqa: BLE001 — surface modality failures to caller
        return StepResult(name=name, status="error", error=str(exc))

    if isinstance(result, (tuple, list)):
        paths = [str(p) for p in result]
        return StepResult(
            name=name,
            status="ok",
            path=paths[0] if paths else None,
            paths=paths or None,
        )
    return StepResult(name=name, status="ok", path=str(result))


def run_pipeline(
    run_dir: Path | str,
    *,
    skip_existing: bool = False,
    raise_on_error: bool = True,
) -> PipelineResult:
    """Run all Processing run modalities and assemble the Workflow sample.

    By default every step re-runs (overwriting intermediates). Pass
    ``skip_existing=True`` to reuse artifacts that already exist.

    Partial failures are collected under ``errors`` keyed by modality name.
    When ``raise_on_error`` is True (CLI default), a ``PipelineError`` is raised
    if any step failed — callers still receive the full ``PipelineResult`` on
    the exception. Never reports overall success with an empty stub sample after
    a required step crash.
    """
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Processing run directory not found: {run_dir}")

    selection = load_project_selection(run_dir)
    steps: list[StepResult] = []
    errors: dict[str, str] = {}

    def record(step: StepResult) -> None:
        steps.append(step)
        if step.status == "error" and step.error:
            errors[step.name] = step.error

    # --- Keystrokes ---
    if skip_existing and _artifact_exists(run_dir, KEYSTROKES_FILENAME):
        record(
            StepResult(
                name=STEP_KEYSTROKES,
                status="skipped",
                path=str(run_dir / KEYSTROKES_FILENAME),
            )
        )
    else:
        record(_run_step(STEP_KEYSTROKES, lambda: extract_keystrokes(run_dir)))

    # --- Cursor ---
    if skip_existing and _artifact_exists(run_dir, CURSOR_EVENTS_FILENAME):
        record(
            StepResult(
                name=STEP_CURSOR,
                status="skipped",
                path=str(run_dir / CURSOR_EVENTS_FILENAME),
            )
        )
    else:
        record(_run_step(STEP_CURSOR, lambda: extract_cursor_events(run_dir)))

    # --- Intent (OpenAI ASR + summary + pairs) ---
    if skip_existing and _artifact_exists(
        run_dir,
        SPEECH_FULL_FILENAME,
        SPEECH_TRIMMED_FILENAME,
        SUMMARY_FILENAME,
        ACTION_INTENT_PAIRS_FILENAME,
    ):
        record(
            StepResult(
                name=STEP_INTENT,
                status="skipped",
                paths=[
                    str(run_dir / SPEECH_FULL_FILENAME),
                    str(run_dir / SPEECH_TRIMMED_FILENAME),
                    str(run_dir / SUMMARY_FILENAME),
                    str(run_dir / ACTION_INTENT_PAIRS_FILENAME),
                ],
            )
        )
    else:
        record(
            _run_step(
                STEP_INTENT,
                lambda: list(extract_intent(run_dir).values()),
            )
        )

    # --- Assemble only when every modality succeeded (no silent stub success) ---
    required = [
        SUMMARY_FILENAME,
        ACTION_INTENT_PAIRS_FILENAME,
        CURSOR_EVENTS_FILENAME,
        KEYSTROKES_FILENAME,
    ]
    missing = [name for name in required if not (run_dir / name).is_file()]
    sample_path: str | None = None
    if errors or missing:
        detail_parts: list[str] = []
        if errors:
            detail_parts.append(
                "modality failure(s): "
                + "; ".join(f"{k}: {v}" for k, v in sorted(errors.items()))
            )
        if missing:
            detail_parts.append("missing artifacts: " + ", ".join(missing))
        record(
            StepResult(
                name=STEP_ASSEMBLE,
                status="error",
                error="; ".join(detail_parts),
            )
        )
    else:
        assemble_result = _run_step(
            STEP_ASSEMBLE, lambda: assemble_workflow_sample(run_dir)
        )
        record(assemble_result)
        if assemble_result.status == "ok" and assemble_result.path:
            sample_path = assemble_result.path

    ok = not errors and sample_path is not None
    result = PipelineResult(
        run_id=selection.id,
        run_dir=str(run_dir),
        ok=ok,
        steps=steps,
        sample_path=sample_path,
        errors=errors,
    )
    if raise_on_error and not ok:
        raise PipelineError(result)
    return result
