"""Core video analysis: per-key brightness extraction + press/release detection.

The pipeline is split in two stages so thresholds can be re-tuned instantly:

1. extract():  decode frames once, compute one scalar per key per frame
               (mean grayscale brightness of the key's inner ROI).
2. detect():   pure numpy on the cached metrics -> press/release events.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class KeyBox:
    label: str
    # normalized to the keyboard rect, 0..1
    x: float
    y: float
    w: float
    h: float


@dataclass
class Job:
    video_path: str
    fps: float
    rect: tuple[int, int, int, int]          # keyboard rect in video px (x, y, w, h)
    keys: list[KeyBox]
    start_frame: int
    end_frame: int                            # inclusive
    stride: int = 1

    state: str = "pending"                    # pending | running | done | error | cancelled
    error: str = ""
    progress: float = 0.0
    frame_indices: np.ndarray | None = None   # (n_samples,)
    metrics: np.ndarray | None = None         # (n_samples, n_keys) float32
    # results of the last detect() run
    last_events: list[dict] = field(default_factory=list)
    last_params: dict = field(default_factory=dict)
    last_stats: list[dict] = field(default_factory=list)
    _cancel: bool = False

    def cancel(self):
        self._cancel = True


def _roi_slices(rect, keys, shrink=0.22):
    """Pixel slices for each key's inner ROI, relative to the cropped keyboard rect."""
    _, _, rw, rh = rect
    slices = []
    for k in keys:
        x0 = k.x * rw
        y0 = k.y * rh
        w = k.w * rw
        h = k.h * rh
        # shrink towards the center to avoid key borders / neighbor bleed
        ix0 = int(round(x0 + w * shrink))
        ix1 = int(round(x0 + w * (1 - shrink)))
        iy0 = int(round(y0 + h * shrink))
        iy1 = int(round(y0 + h * (1 - shrink)))
        ix1 = max(ix1, ix0 + 1)
        iy1 = max(iy1, iy0 + 1)
        ix0 = max(0, min(ix0, rw - 1))
        iy0 = max(0, min(iy0, rh - 1))
        ix1 = max(1, min(ix1, rw))
        iy1 = max(1, min(iy1, rh))
        slices.append((slice(iy0, iy1), slice(ix0, ix1)))
    return slices


def extract(job: Job):
    """Decode the frame range and fill job.metrics. Runs in a worker thread."""
    try:
        job.state = "running"
        cap = cv2.VideoCapture(job.video_path)
        if not cap.isOpened():
            raise RuntimeError(f"cannot open video: {job.video_path}")

        x, y, w, h = job.rect
        slices = _roi_slices(job.rect, job.keys)
        frame_indices = list(range(job.start_frame, job.end_frame + 1, job.stride))
        n = len(frame_indices)
        metrics = np.zeros((n, len(job.keys)), dtype=np.float32)

        cap.set(cv2.CAP_PROP_POS_FRAMES, job.start_frame)
        cur = job.start_frame
        out_i = 0
        want = set(frame_indices)
        while out_i < n:
            if job._cancel:
                job.state = "cancelled"
                cap.release()
                return
            ok, frame = cap.read()
            if not ok:
                # video ended early; truncate
                frame_indices = frame_indices[:out_i]
                metrics = metrics[:out_i]
                break
            if cur in want:
                crop = frame[y:y + h, x:x + w]
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                for ki, (sy, sx) in enumerate(slices):
                    metrics[out_i, ki] = float(gray[sy, sx].mean())
                out_i += 1
                if out_i % 200 == 0:
                    job.progress = out_i / n
            cur += 1
        cap.release()
        job.frame_indices = np.asarray(frame_indices, dtype=np.int64)
        job.metrics = metrics
        job.progress = 1.0
        job.state = "done"
    except Exception as e:  # noqa: BLE001
        job.state = "error"
        job.error = str(e)


def start_extract(job: Job) -> threading.Thread:
    t = threading.Thread(target=extract, args=(job,), daemon=True)
    t.start()
    return t


def detect(job: Job, *, direction="up", min_delta=25.0, k_mad=8.0,
           release_frac=0.5, min_duration_ms=40.0, merge_gap_ms=30.0):
    """Turn cached metrics into press/release events.

    baseline   = per-key median over time (keys are unpressed most of the time)
    press when  signal crosses baseline + max(min_delta, k_mad * MAD)
    release when it falls back below baseline + release_frac * press_delta
    """
    if job.metrics is None:
        raise RuntimeError("metrics not extracted yet")

    m = job.metrics                      # (n, k)
    frames = job.frame_indices
    fps = job.fps
    baseline = np.median(m, axis=0)      # (k,)
    mad = np.median(np.abs(m - baseline), axis=0) * 1.4826

    press_delta = np.maximum(min_delta, k_mad * mad)          # (k,)
    release_delta = np.maximum(min_delta * release_frac, press_delta * release_frac)

    if direction == "up":
        sig = m - baseline
    elif direction == "down":
        sig = baseline - m
    else:  # both
        sig = np.abs(m - baseline)

    frame_dt = job.stride / fps
    # an interval of L samples spans L*frame_dt of wall time; require at least min_duration
    min_len = max(1, int(np.ceil((min_duration_ms / 1000.0) / frame_dt)))
    merge_gap = int(round((merge_gap_ms / 1000.0) / frame_dt))

    events = []
    stats = []
    n = m.shape[0]
    for ki, key in enumerate(job.keys):
        s = sig[:, ki]
        pd, rd = float(press_delta[ki]), float(release_delta[ki])
        intervals = []
        pressed = False
        start_i = 0
        for i in range(n):
            if not pressed:
                if s[i] >= pd:
                    pressed = True
                    start_i = i
            else:
                if s[i] < rd:
                    intervals.append([start_i, i - 1])
                    pressed = False
        clipped_last = False
        if pressed:
            intervals.append([start_i, n - 1])
            clipped_last = True

        # merge intervals separated by a tiny gap (flicker/compression noise)
        merged = []
        for iv in intervals:
            if merged and iv[0] - merged[-1][1] <= merge_gap:
                merged[-1][1] = iv[1]
            else:
                merged.append(iv)
        # drop too-short blips
        merged = [iv for iv in merged if iv[1] - iv[0] + 1 >= min_len]

        for j, (a, b) in enumerate(merged):
            fa, fb = int(frames[a]), int(frames[b])
            ev = {
                "key": key.label,
                "press_t": round(fa / fps, 4),
                "release_t": round(fb / fps, 4),
                "press_frame": fa,
                "release_frame": fb,
                "duration_ms": round((fb - fa) / fps * 1000.0, 1),
                "clipped": bool(clipped_last and j == len(merged) - 1),
            }
            events.append(ev)

        stats.append({
            "key": key.label,
            "baseline": round(float(baseline[ki]), 1),
            "mad": round(float(mad[ki]), 2),
            "press_delta": round(pd, 1),
            "release_delta": round(rd, 1),
            "peak": round(float(s.max()), 1),
            "events": len(merged),
        })

    events.sort(key=lambda e: (e["press_t"], e["key"]))
    params = dict(direction=direction, min_delta=min_delta, k_mad=k_mad,
                  release_frac=release_frac, min_duration_ms=min_duration_ms,
                  merge_gap_ms=merge_gap_ms)
    job.last_events = events
    job.last_params = params
    job.last_stats = stats
    return events, stats


def key_trace(job: Job, label: str):
    """Time series for one key, for the review plot."""
    if job.metrics is None:
        raise RuntimeError("metrics not extracted yet")
    labels = [k.label for k in job.keys]
    ki = labels.index(label)
    m = job.metrics[:, ki]
    baseline = float(np.median(m))
    intervals = [[e["press_frame"], e["release_frame"]]
                 for e in job.last_events if e["key"] == label]
    return {
        "label": label,
        "frames": job.frame_indices.tolist(),
        "t": [round(f / job.fps, 4) for f in job.frame_indices],
        "v": [round(float(v), 2) for v in m],
        "baseline": round(baseline, 2),
        "intervals": intervals,
    }


def states_at(job: Job, t: float):
    """Which keys are pressed at time t, according to the last detection run."""
    if job.frame_indices is None:
        raise RuntimeError("metrics not extracted yet")
    f = int(round(t * job.fps))
    i = int(np.clip(np.searchsorted(job.frame_indices, f), 0, len(job.frame_indices) - 1))
    sample_f = int(job.frame_indices[i])
    pressed = {e["key"] for e in job.last_events
               if e["press_frame"] <= sample_f <= e["release_frame"]}
    out = []
    for ki, k in enumerate(job.keys):
        out.append({
            "key": k.label,
            "value": round(float(job.metrics[i, ki]), 1),
            "pressed": k.label in pressed,
        })
    return {"frame": sample_f, "t": round(sample_f / job.fps, 4), "keys": out}
