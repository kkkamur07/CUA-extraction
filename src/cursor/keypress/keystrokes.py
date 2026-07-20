"""Keystroke extraction for a Processing run (Keyboard ROI + time range).

Uses in-tree ``cursor.keypress`` CV analysis (brightness extract + press/release
detect) and optional key auto-detection. Writes ``keystrokes/keystrokes.json``
under the run directory. Async jobs also write ``keystrokes/keystroke_job.json``
for UI polling.

Granularity: every Source frame in the Keyboard track range at the video's
native FPS (stride=1).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import cv2

from . import analysis, cvdetect

LAYOUTS_DIR = Path(__file__).resolve().parent / "layouts"
from ..workflow.models import KeystrokeRawEvent, ProjectSelection
from ..workflow.workflow import (
    KEYSTROKE_JOB_FILENAME,
    KEYSTROKES_FILENAME,
    MOUSE_EVENTS_FILENAME,
    RAW_KEYSTROKES_FILENAME,
    load_project_selection,
)

DEFAULT_LAYOUT_NAME = "tootalltoby.json"
_DEFAULT_LAYOUT_NAME = DEFAULT_LAYOUT_NAME  # back-compat
DEFAULT_STRIDE = 1
POLL_INTERVAL_S = 0.25
MOUSE_BUTTON_MAPPING = {"M1": "left", "M2": "right"}


def _is_mouse_overlay_event(event: dict[str, Any]) -> bool:
    return str(event.get("key", "")).upper() in MOUSE_BUTTON_MAPPING


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def ensure_keyboard_detector_importable() -> Path:
    """Back-compat: returns the in-tree keypress package root."""
    return LAYOUTS_DIR.parent


def resolve_video_path(video: str, *, cwd: Path | None = None) -> Path:
    path = Path(video)
    if path.is_file():
        return path.resolve()
    base = cwd if cwd is not None else Path.cwd()
    candidates = [
        base / path,
        _repo_root() / path,
        base / "video" / path.name,
        _repo_root() / "video" / path.name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Video not found: {video}")


def load_layout_template(
    kd_root: Path | None = None,
    *,
    layout_name: str = DEFAULT_LAYOUT_NAME,
) -> list[dict[str, Any]]:
    if kd_root is None:
        layouts = LAYOUTS_DIR
    else:
        root = Path(kd_root)
        if (root / "layouts").is_dir():
            layouts = root / "layouts"
        elif root.name == "layouts":
            layouts = root
        elif (root / "app" / "layouts").is_dir():
            layouts = root / "app" / "layouts"
        else:
            layouts = LAYOUTS_DIR
    path = layouts / layout_name
    if not path.is_file():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    keys = doc.get("keys", [])
    return keys if isinstance(keys, list) else []


def _keyboard_rect(selection: ProjectSelection) -> tuple[int, int, int, int]:
    roi = selection.keyboard.roi
    return (int(roi.x), int(roi.y), int(roi.width), int(roi.height))


def read_video_fps(video_path: Path, *, fallback: float | None = None) -> float:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    finally:
        cap.release()
    if fps > 1e-6:
        return fps
    if fallback is not None and fallback > 1e-6:
        return float(fallback)
    raise RuntimeError(
        f"Could not read FPS from video {video_path}; "
        "set a positive fps in selection.json as fallback"
    )


def _frame_range(
    selection: ProjectSelection,
    *,
    n_frames: int,
    fps: float,
) -> tuple[int, int]:
    track = selection.keyboard
    start_f = max(0, int(round(track.start * fps)))
    end_f = min(n_frames - 1, int(round(track.end * fps)))
    if end_f <= start_f:
        raise ValueError(
            f"Keyboard time range must have end > start "
            f"(got start={track.start}, end={track.end}, fps={fps})"
        )
    return start_f, end_f


def read_keyboard_crop(
    video_path: Path,
    rect: tuple[int, int, int, int],
    t: float,
    fps: float,
) -> Any:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {video_path}")
    try:
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        frame_i = max(0, min(int(round(t * fps)), max(0, n - 1)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_i)
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError(f"could not read frame at t={t} (frame {frame_i})")
        x, y, w, h = rect
        crop = frame[y : y + h, x : x + w]
        if crop.size == 0:
            raise ValueError(f"Keyboard ROI is outside the frame: {rect}")
        return crop
    finally:
        cap.release()


def autodetect_keys(
    video_path: Path,
    selection: ProjectSelection,
    *,
    template: list[dict[str, Any]] | None = None,
    layout_name: str = DEFAULT_LAYOUT_NAME,
) -> list[dict[str, Any]]:
    if template is None:
        template = load_layout_template(layout_name=layout_name)

    rect = _keyboard_rect(selection)
    t = float(selection.keyboard.preview_timestamp)
    fps = read_video_fps(video_path, fallback=float(selection.fps))
    crop = read_keyboard_crop(video_path, rect, t, fps)
    keys, info = cvdetect.autodetect(crop, template)
    if not keys:
        raise RuntimeError(
            f"No keys auto-detected in Keyboard ROI {rect} "
            f"(info={info}); provide a layout or adjust the ROI"
        )
    return keys


def detector_event_to_raw(event: dict[str, Any]) -> dict[str, Any]:
    raw = KeystrokeRawEvent(
        key=str(event["key"]),
        press_t=float(event["press_t"]),
        release_t=float(event["release_t"]),
        clipped=bool(event.get("clipped", False)),
    )
    out: dict[str, Any] = {
        "type": raw.type,
        "key": raw.key,
        "press_t": raw.press_t,
        "release_t": raw.release_t,
        "clipped": raw.clipped,
    }
    if "press_frame" in event:
        out["press_frame"] = int(event["press_frame"])
    if "release_frame" in event:
        out["release_frame"] = int(event["release_frame"])
    if "duration_ms" in event:
        out["duration_ms"] = event["duration_ms"]
    return out


def extract_keystrokes_from_selection(
    selection: ProjectSelection,
    *,
    keys: list[dict[str, Any]] | None = None,
    video_path: Path | str | None = None,
    stride: int = DEFAULT_STRIDE,
    layout_name: str = DEFAULT_LAYOUT_NAME,
    detect_params: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run keypress extract+detect for a ProjectSelection."""
    path = resolve_video_path(str(video_path or selection.video))
    rect = _keyboard_rect(selection)

    stride_i = max(1, int(stride))
    if stride_i != 1:
        raise ValueError(
            f"Keystroke extraction requires stride=1 (every Source frame); "
            f"got stride={stride_i}. Subsampling is not allowed for Processing runs."
        )

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video: {path}")
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    video_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    cap.release()
    if n_frames <= 0:
        raise RuntimeError(f"video has no frames: {path}")
    if video_fps <= 1e-6:
        video_fps = read_video_fps(path, fallback=float(selection.fps))

    start_f, end_f = _frame_range(selection, n_frames=n_frames, fps=video_fps)

    if keys is None:
        keys = autodetect_keys(path, selection, layout_name=layout_name)

    key_boxes = [
        analysis.KeyBox(
            str(k["label"]),
            float(k["x"]),
            float(k["y"]),
            float(k["w"]),
            float(k["h"]),
        )
        for k in keys
    ]
    if not key_boxes:
        raise ValueError("no keys defined for Keystroke extraction")

    job = analysis.Job(
        video_path=str(path),
        fps=video_fps,
        rect=rect,
        keys=key_boxes,
        start_frame=start_f,
        end_frame=end_f,
        stride=1,
    )
    analysis.extract(job)
    if job.state != "done":
        raise RuntimeError(f"keystroke extract failed: {job.error or job.state}")

    params = dict(detect_params or {})
    events, stats = analysis.detect(job, **params)
    raw_events = [detector_event_to_raw(e) for e in events]
    meta = {
        "video": str(path),
        "fps": video_fps,
        "selection_fps": float(selection.fps),
        "keyboard_rect": list(rect),
        "range": {
            "start_t": float(selection.keyboard.start),
            "end_t": float(selection.keyboard.end),
            "start_frame": start_f,
            "end_frame": end_f,
            "stride": 1,
            "n_frames_analyzed": int(end_f - start_f + 1),
        },
        "n_keys": len(key_boxes),
        "params": job.last_params,
        "stats": stats,
        "layout": layout_name,
        "keypress_package": str(LAYOUTS_DIR.parent),
    }
    return raw_events, meta


def write_keystrokes_artifact(
    run_dir: Path | str,
    events: list[dict[str, Any]],
    *,
    meta: dict[str, Any] | None = None,
) -> Path:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_payload: dict[str, Any] = {"events": events}
    if meta:
        raw_payload["meta"] = {
            k: v
            for k, v in meta.items()
            if k
            in (
                "video",
                "fps",
                "selection_fps",
                "keyboard_rect",
                "range",
                "n_keys",
                "params",
                "layout",
            )
        }
    raw_path = run_dir / RAW_KEYSTROKES_FILENAME
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps(raw_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    keyboard_events = [
        event for event in events if not _is_mouse_overlay_event(event)
    ]
    payload = {**raw_payload, "events": keyboard_events}
    out_path = run_dir / KEYSTROKES_FILENAME
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path


def write_mouse_events_artifact(
    run_dir: Path | str,
    events: list[dict[str, Any]],
) -> Path:
    """Write M1/M2 overlay detections as normalized mouse-button events."""
    run_dir = Path(run_dir)
    mouse_events: list[dict[str, Any]] = []
    for item in events:
        source_key = str(item.get("key", "")).upper()
        button = MOUSE_BUTTON_MAPPING.get(source_key)
        if button is None:
            continue
        mouse_events.append(
            {
                "type": "mouse_button",
                "button": button,
                "press_t": float(item["press_t"]),
                "release_t": float(item["release_t"]),
                "source_key": source_key,
                "clipped": bool(item.get("clipped", False)),
            }
        )
    mouse_events.sort(key=lambda item: (item["press_t"], item["button"]))
    out_path = run_dir / MOUSE_EVENTS_FILENAME
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in mouse_events),
        encoding="utf-8",
    )
    return out_path


def extract_keystrokes(
    run_dir: Path | str,
    *,
    keys: list[dict[str, Any]] | None = None,
    stride: int = DEFAULT_STRIDE,
    layout_name: str = DEFAULT_LAYOUT_NAME,
    detect_params: dict[str, Any] | None = None,
) -> Path:
    run_dir = Path(run_dir)
    selection = load_project_selection(run_dir)
    events, meta = extract_keystrokes_from_selection(
        selection,
        keys=keys,
        stride=stride,
        layout_name=layout_name,
        detect_params=detect_params,
    )
    out_path = write_keystrokes_artifact(run_dir, events, meta=meta)
    write_mouse_events_artifact(run_dir, events)
    return out_path


# --- Async job (UI polling via keystroke_job.json) ---


def job_status_path(run_dir: Path | str) -> Path:
    return Path(run_dir) / KEYSTROKE_JOB_FILENAME


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


def run_keystroke_job(
    run_dir: Path | str,
    *,
    layout_name: str = DEFAULT_LAYOUT_NAME,
    detect_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Blocking entry: extract with progress file, detect, write keystrokes.json."""
    run_dir = Path(run_dir)
    write_job_status(
        run_dir,
        {
            "state": "starting",
            "progress": 0.0,
            "error": None,
            "n_samples": 0,
            "n_events": 0,
            "message": "Loading selection…",
        },
    )

    try:
        selection = load_project_selection(run_dir)
        path = resolve_video_path(selection.video)
        rect = _keyboard_rect(selection)

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError(f"cannot open video: {path}")
        n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        video_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        cap.release()
        if n_frames <= 0:
            raise RuntimeError(f"video has no frames: {path}")
        if video_fps <= 1e-6:
            video_fps = read_video_fps(path, fallback=float(selection.fps))

        start_f, end_f = _frame_range(selection, n_frames=n_frames, fps=video_fps)

        write_job_status(
            run_dir,
            {
                "state": "starting",
                "progress": 0.0,
                "error": None,
                "n_samples": 0,
                "n_events": 0,
                "message": "Auto-detecting keys…",
                "fps": video_fps,
                "range": {
                    "start_t": float(selection.keyboard.start),
                    "end_t": float(selection.keyboard.end),
                    "start_frame": start_f,
                    "end_frame": end_f,
                },
            },
        )

        keys = autodetect_keys(path, selection, layout_name=layout_name)
        key_boxes = [
            analysis.KeyBox(
                str(k["label"]),
                float(k["x"]),
                float(k["y"]),
                float(k["w"]),
                float(k["h"]),
            )
            for k in keys
        ]
        if not key_boxes:
            raise ValueError("no keys defined for Keystroke extraction")

        frames_to_process = end_f - start_f + 1
        job = analysis.Job(
            video_path=str(path),
            fps=video_fps,
            rect=rect,
            keys=key_boxes,
            start_frame=start_f,
            end_frame=end_f,
            stride=DEFAULT_STRIDE,
        )

        write_job_status(
            run_dir,
            {
                "state": "running",
                "progress": 0.0,
                "error": None,
                "n_samples": 0,
                "n_events": 0,
                "message": f"Extracting metrics ({frames_to_process} frames)…",
                "fps": video_fps,
                "n_keys": len(key_boxes),
                "frames_to_process": frames_to_process,
                "range": {
                    "start_t": float(selection.keyboard.start),
                    "end_t": float(selection.keyboard.end),
                    "start_frame": start_f,
                    "end_frame": end_f,
                },
            },
        )

        thread = analysis.start_extract(job)
        while thread.is_alive():
            write_job_status(
                run_dir,
                {
                    "state": "running",
                    "progress": float(job.progress),
                    "error": None,
                    "n_samples": 0,
                    "n_events": 0,
                    "message": f"Extracting metrics… {job.progress * 100:.1f}%",
                    "fps": video_fps,
                    "n_keys": len(key_boxes),
                    "frames_to_process": frames_to_process,
                    "range": {
                        "start_t": float(selection.keyboard.start),
                        "end_t": float(selection.keyboard.end),
                        "start_frame": start_f,
                        "end_frame": end_f,
                    },
                },
            )
            thread.join(timeout=POLL_INTERVAL_S)

        if job.state != "done":
            err = job.error or job.state
            write_job_status(
                run_dir,
                {
                    "state": "error",
                    "progress": float(job.progress),
                    "error": err,
                    "n_samples": 0,
                    "n_events": 0,
                    "message": f"Extract failed: {err}",
                },
            )
            raise RuntimeError(f"keystroke extract failed: {err}")

        n_samples = 0 if job.metrics is None else int(job.metrics.shape[0])
        write_job_status(
            run_dir,
            {
                "state": "detecting",
                "progress": 1.0,
                "error": None,
                "n_samples": n_samples,
                "n_events": 0,
                "message": "Detecting key presses…",
                "fps": video_fps,
                "n_keys": len(key_boxes),
                "frames_to_process": frames_to_process,
                "range": {
                    "start_t": float(selection.keyboard.start),
                    "end_t": float(selection.keyboard.end),
                    "start_frame": start_f,
                    "end_frame": end_f,
                },
            },
        )

        params = dict(detect_params or {})
        events, stats = analysis.detect(job, **params)
        raw_events = [detector_event_to_raw(e) for e in events]
        meta = {
            "video": str(path),
            "fps": video_fps,
            "selection_fps": float(selection.fps),
            "keyboard_rect": list(rect),
            "range": {
                "start_t": float(selection.keyboard.start),
                "end_t": float(selection.keyboard.end),
                "start_frame": start_f,
                "end_frame": end_f,
                "stride": 1,
                "n_frames_analyzed": int(end_f - start_f + 1),
            },
            "n_keys": len(key_boxes),
            "params": job.last_params,
            "stats": stats,
            "layout": layout_name,
            "keypress_package": str(LAYOUTS_DIR.parent),
        }
        out_path = write_keystrokes_artifact(run_dir, raw_events, meta=meta)
        mouse_path = write_mouse_events_artifact(run_dir, raw_events)
        keyboard_event_count = sum(
            not _is_mouse_overlay_event(event) for event in raw_events
        )

        result = {
            "state": "done",
            "progress": 1.0,
            "error": None,
            "n_samples": n_samples,
            "n_events": keyboard_event_count,
            "mouse_events": len(raw_events) - keyboard_event_count,
            "message": f"Done — {keyboard_event_count} keyboard events",
            "fps": video_fps,
            "n_keys": len(key_boxes),
            "frames_to_process": frames_to_process,
            "path": str(out_path),
            "mouse_path": str(mouse_path),
            "range": meta["range"],
            "stats": stats,
        }
        write_job_status(run_dir, result)
        return result
    except Exception as exc:  # noqa: BLE001
        write_job_status(
            run_dir,
            {
                "state": "error",
                "progress": 0.0,
                "error": str(exc),
                "n_samples": 0,
                "n_events": 0,
                "message": str(exc),
            },
        )
        raise
