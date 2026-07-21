"""OpenCUA/AgentNet-style action reduction (arXiv:2508.09123, Section 2.2).

Turns the extracted low-level event streams (per-frame cursor track, mouse
button intervals, per-key keystroke intervals) into a compact sequence of
pyautogui-space agent actions, following the AgentNet rules:

* Mouse move events are treated as *preconditions* for clicks or drags — only
  their start and end positions are retained. Cursor motion not attached to a
  click/drag (noise, idle wandering) produces no action.
* Common multistep gestures are combined: repeated clicks in place become
  ``doubleClick``/``tripleClick``; press–move–release beyond a threshold
  becomes ``moveTo`` + ``dragTo``.
* Consecutive printable key presses are merged into ``write(text)`` strings
  (shift/capslock aware); modifier combinations (e.g. CTRL+C) are abstracted
  into ``hotkey(...)``; other keys become ``press(key)``, with immediate
  repeats consolidated via a count.
* State–action matching: each action carries the timestamp of the observation
  frame *immediately before* it. For mouse actions we backtrack to the start
  of the cursor's pre-movement phase, per the paper.
* A ``terminate`` action is appended at the end of the trajectory.

Coordinates are emitted both as screen-crop pixels and normalized [0, 1]
(4 decimals), matching AgentNet's serialized examples.

This module consumes only already-extracted artifacts — it never touches the
video.
"""

from __future__ import annotations

import bisect
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import keymap

SCHEMA_VERSION = "opencua-reduction/1"


@dataclass(frozen=True)
class ReduceParams:
    drag_min_px: float = 12.0            # press→release displacement that makes a drag
    multi_click_gap_s: float = 0.4       # max release→press gap inside double/triple click
    multi_click_radius_px: float = 12.0  # max spatial spread inside double/triple click
    write_max_gap_s: float = 2.0         # max gap between chars merged into one write()
    press_repeat_gap_s: float = 1.0      # max gap when consolidating repeated press()
    modifier_tolerance_s: float = 0.05   # slack when testing "modifier held during event"
    cursor_max_gap_s: float = 1.0        # max distance to a cursor sample for a position
    stationary_eps_px: float = 3.0       # movement below this is "stationary" (keyframes)
    keyframe_backtrack_max_s: float = 5.0
    keyboard_keyframe_lead_s: float = 0.2
    terminate_status: str | None = "success"   # None disables the terminate action
    # Drag-path preservation (extension over the paper, see docs): when the
    # actual drag trajectory deviates from the straight start->end line by
    # more than drag_path_deviation_px, the simplified true path is attached
    # as an auxiliary "path" field (args stay strictly AgentNet-shaped).
    include_drag_paths: bool = True
    drag_path_deviation_px: float = 6.0   # min curvature to bother storing a path
    drag_path_epsilon_px: float = 3.0     # Douglas-Peucker simplification tolerance
    drag_path_max_points: int = 64
    # Overlay key -> physical button. Overrides the `button` field via
    # `source_key` because previously extracted artifacts carry an inverted
    # mapping (M1 is the LEFT mouse button on the TooTallToby overlay, and it
    # accounts for ~97% of presses in the samples — the dominant button in any
    # GUI workflow is the left one). Set to None to trust the input as-is.
    button_map: dict[str, str] | None = field(
        default_factory=lambda: {"M1": "left", "M2": "right"})

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


# --------------------------------------------------------------- cursor track
class CursorTrack:
    """Time-indexed cursor positions with interpolation and backtracking."""

    def __init__(self, samples: list[dict[str, Any]]):
        samples = sorted(samples, key=lambda s: s["t"])
        self.ts = [float(s["t"]) for s in samples]
        self.xs = [float(s["x"]) for s in samples]
        self.ys = [float(s["y"]) for s in samples]

    def __len__(self) -> int:
        return len(self.ts)

    def pos_at(self, t: float, max_gap_s: float) -> tuple[float, float] | None:
        """Cursor position at time t: interpolated when bracketed, else the
        nearest sample within max_gap_s."""
        if not self.ts:
            return None
        i = bisect.bisect_left(self.ts, t)
        if 0 < i < len(self.ts):
            t0, t1 = self.ts[i - 1], self.ts[i]
            if t1 - t0 <= 2 * max_gap_s and t0 <= t <= t1:
                f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                return (self.xs[i - 1] + f * (self.xs[i] - self.xs[i - 1]),
                        self.ys[i - 1] + f * (self.ys[i] - self.ys[i - 1]))
        j = min(max(i, 0), len(self.ts) - 1)
        if i > 0 and (i >= len(self.ts) or abs(self.ts[i - 1] - t) <= abs(self.ts[j] - t)):
            j = i - 1
        if abs(self.ts[j] - t) <= max_gap_s:
            return (self.xs[j], self.ys[j])
        return None

    def samples_between(self, t0: float, t1: float) -> list[tuple[float, float, float]]:
        """(t, x, y) samples with t0 <= t <= t1."""
        i = bisect.bisect_left(self.ts, t0)
        j = bisect.bisect_right(self.ts, t1)
        return [(self.ts[k], self.xs[k], self.ys[k]) for k in range(i, j)]

    def pre_movement_start(self, t: float, params: ReduceParams) -> float:
        """Backtrack from t to the start of the contiguous movement phase that
        leads into it (AgentNet state–action matching for mouse actions)."""
        if not self.ts:
            return max(0.0, t - params.keyboard_keyframe_lead_s)
        i = min(bisect.bisect_right(self.ts, t), len(self.ts)) - 1
        limit = t - params.keyframe_backtrack_max_s
        while i > 0:
            if self.ts[i - 1] < limit:
                break
            step = math.hypot(self.xs[i] - self.xs[i - 1], self.ys[i] - self.ys[i - 1])
            if step <= params.stationary_eps_px:
                break
            i -= 1
        return max(0.0, self.ts[max(i, 0)])


# -------------------------------------------------------- path simplification
def _perp_dist(p: tuple[float, float], a: tuple[float, float],
               b: tuple[float, float]) -> float:
    """Distance from point p to the segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    f = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    return math.hypot(p[0] - (a[0] + f * dx), p[1] - (a[1] + f * dy))


def _rdp(points: list[tuple[float, float, float]], eps: float):
    """Ramer–Douglas–Peucker over (t, x, y) points (keyed on x, y)."""
    if len(points) < 3:
        return list(points)
    a, b = points[0], points[-1]
    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        d = _perp_dist(points[i][1:], a[1:], b[1:])
        if d > dmax:
            dmax, idx = d, i
    if dmax <= eps:
        return [a, b]
    left = _rdp(points[:idx + 1], eps)
    right = _rdp(points[idx:], eps)
    return left[:-1] + right


# ------------------------------------------------------------- stream elements
@dataclass
class _KeyEvent:
    t: float
    end_t: float
    label: str
    modifiers: list[str]
    capslock: bool
    source_index: int


@dataclass
class _MouseEvent:
    t: float
    end_t: float
    button: str
    press_pos: tuple[float, float] | None
    release_pos: tuple[float, float] | None
    modifiers: list[str]
    source_index: int


@dataclass
class _Reducer:
    track: CursorTrack
    screen_w: float
    screen_h: float
    fps: float
    params: ReduceParams
    actions: list[dict[str, Any]] = field(default_factory=list)

    # ---- pending write() buffer
    _write_chars: list[str] = field(default_factory=list)
    _write_t0: float = 0.0
    _write_t1: float = 0.0
    _write_sources: list[int] = field(default_factory=list)

    # ---- pending click cluster (for double/triple click)
    _clicks: list[_MouseEvent] = field(default_factory=list)

    # ---- pending repeated press()
    _press: dict[str, Any] | None = None

    # ------------------------------------------------------------- helpers
    def _clamp(self, pos: tuple[float, float]) -> tuple[float, float]:
        # detections can land marginally outside the screen crop
        return (min(max(pos[0], 0.0), self.screen_w),
                min(max(pos[1], 0.0), self.screen_h))

    def _norm(self, pos: tuple[float, float]) -> dict[str, float]:
        x, y = self._clamp(pos)
        return {"x": round(x / self.screen_w, 4), "y": round(y / self.screen_h, 4)}

    def _pixels(self, pos: tuple[float, float]) -> dict[str, float]:
        x, y = self._clamp(pos)
        return {"x": round(x, 1), "y": round(y, 1)}

    def _emit(self, action: dict[str, Any]) -> None:
        action["idx"] = len(self.actions)
        self.actions.append(action)

    def _observation(self, t_start: float, mouse: bool) -> dict[str, float]:
        if mouse:
            kt = self.track.pre_movement_start(t_start, self.params)
        else:
            kt = max(0.0, t_start - self.params.keyboard_keyframe_lead_s)
        return {"keyframe_t": round(kt, 3), "keyframe_frame": int(round(kt * self.fps))}

    @staticmethod
    def _mod_sorted(mods: list[str]) -> list[str]:
        return sorted(set(mods), key=lambda m: keymap.MODIFIER_ORDER.get(m, 9))

    @staticmethod
    def _wrap_modifiers(code: str, mods: list[str]) -> str:
        """Non-hotkey action performed while modifiers are held (e.g. CTRL+drag
        in CAD): wrap the pyautogui code in keyDown/keyUp. Extension over the
        paper's Table 1, recorded in args.modifiers as well."""
        if not mods:
            return code
        down = " ".join(f"pyautogui.keyDown({m!r});" for m in mods)
        up = " ".join(f"pyautogui.keyUp({m!r});" for m in mods)
        return f"{down} {code} {up}".strip().rstrip(";")

    # ------------------------------------------------------------- flushing
    def flush_all(self) -> None:
        self.flush_write()
        self.flush_clicks()
        self.flush_press()

    def flush_write(self) -> None:
        if not self._write_chars:
            return
        text = "".join(self._write_chars)
        self._emit({
            "t_start": round(self._write_t0, 3),
            "t_end": round(self._write_t1, 3),
            "action": "write",
            "args": {"text": text},
            "pyautogui_code": f"pyautogui.write({text!r})",
            "observation": self._observation(self._write_t0, mouse=False),
            "evidence": {"keystroke_indices": list(self._write_sources)},
        })
        self._write_chars.clear()
        self._write_sources.clear()

    def flush_press(self) -> None:
        if self._press is None:
            return
        p = self._press
        n = p["count"]
        code = (f"pyautogui.press({p['key']!r})" if n == 1
                else f"pyautogui.press({p['key']!r}, presses={n})")
        self._emit({
            "t_start": round(p["t0"], 3),
            "t_end": round(p["t1"], 3),
            "action": "press",
            "args": {"key": p["key"], "presses": n},
            "pyautogui_code": code,
            "observation": self._observation(p["t0"], mouse=False),
            "evidence": {"keystroke_indices": p["sources"]},
        })
        self._press = None

    def flush_clicks(self) -> None:
        if not self._clicks:
            return
        group = self._clicks
        self._clicks = []
        count = len(group)
        first = group[0]
        pos = first.press_pos
        name_by_count = {1: "click", 2: "doubleClick", 3: "tripleClick"}
        name = name_by_count.get(count, "tripleClick")
        if first.button == "right" and count == 1:
            name = "rightClick"
        elif first.button == "middle" and count == 1:
            name = "middleClick"

        args: dict[str, Any] = {}
        if pos is not None:
            args.update(self._norm(pos))
        if first.button != "left" and name in ("click", "doubleClick", "tripleClick"):
            args["button"] = first.button

        fn = {"click": "click", "rightClick": "rightClick", "middleClick": "middleClick",
              "doubleClick": "doubleClick", "tripleClick": "tripleClick"}[name]
        arg_str = ", ".join(
            [f"x={args['x']}, y={args['y']}" if pos is not None else ""]
            + ([f"button={first.button!r}"] if "button" in args else [])
        ).strip(", ")
        code = self._wrap_modifiers(f"pyautogui.{fn}({arg_str})", first.modifiers)

        self._emit({
            "t_start": round(first.t, 3),
            "t_end": round(group[-1].end_t, 3),
            "action": name,
            "args": args,
            "pixels": self._pixels(pos) if pos is not None else None,
            "modifiers": first.modifiers,
            "pyautogui_code": code,
            "observation": self._observation(first.t, mouse=True),
            "evidence": {"mouse_button_indices": [g.source_index for g in group]},
        })

    # ------------------------------------------------------------- ingestion
    def on_key(self, ev: _KeyEvent) -> None:
        label = ev.label
        non_shift_mods = [m for m in ev.modifiers if m != "shift"]
        shifted = "shift" in ev.modifiers

        # hotkey: any non-shift modifier, or shift on a non-printable key
        if non_shift_mods or (shifted and not keymap.is_printable(label)):
            self.flush_all()
            keys = self._mod_sorted(ev.modifiers) + [keymap.hotkey_key_name(label)]
            self._emit({
                "t_start": round(ev.t, 3),
                "t_end": round(ev.end_t, 3),
                "action": "hotkey",
                "args": {"keys": keys},
                "pyautogui_code": "pyautogui.hotkey(" + ", ".join(repr(k) for k in keys) + ")",
                "observation": self._observation(ev.t, mouse=False),
                "evidence": {"keystroke_indices": [ev.source_index]},
            })
            return

        if keymap.is_printable(label):
            self.flush_clicks()
            self.flush_press()
            if self._write_chars and ev.t - self._write_t1 > self.params.write_max_gap_s:
                self.flush_write()
            if not self._write_chars:
                self._write_t0 = ev.t
            self._write_chars.append(
                keymap.char_for(label, shifted=shifted, capslock=ev.capslock))
            self._write_t1 = ev.end_t
            self._write_sources.append(ev.source_index)
            return

        # special key -> press (with repeat consolidation)
        key_name = keymap.SPECIAL.get(label, label.lower())
        self.flush_write()
        self.flush_clicks()
        if (self._press is not None
                and self._press["key"] == key_name
                and ev.t - self._press["t1"] <= self.params.press_repeat_gap_s):
            self._press["count"] += 1
            self._press["t1"] = ev.end_t
            self._press["sources"].append(ev.source_index)
            return
        self.flush_press()
        self._press = {"key": key_name, "count": 1, "t0": ev.t, "t1": ev.end_t,
                       "sources": [ev.source_index]}

    def on_mouse(self, ev: _MouseEvent) -> None:
        self.flush_write()
        self.flush_press()

        drag_dist = 0.0
        if ev.press_pos is not None and ev.release_pos is not None:
            drag_dist = math.hypot(ev.release_pos[0] - ev.press_pos[0],
                                   ev.release_pos[1] - ev.press_pos[1])
        if drag_dist >= self.params.drag_min_px:
            self.flush_clicks()
            self._emit_drag(ev)
            return

        # click clustering for double/triple click
        if self._clicks:
            prev = self._clicks[-1]
            # spatial check only when both positions are known — YOLO cursor
            # tracks have gaps, and a missing sample must not break merging
            near = True
            if prev.press_pos is not None and ev.press_pos is not None:
                near = (math.hypot(ev.press_pos[0] - prev.press_pos[0],
                                   ev.press_pos[1] - prev.press_pos[1])
                        <= self.params.multi_click_radius_px)
            same = (prev.button == ev.button
                    and ev.t - prev.end_t <= self.params.multi_click_gap_s
                    and near
                    and prev.modifiers == ev.modifiers
                    and len(self._clicks) < 3)
            if not same:
                self.flush_clicks()
        self._clicks.append(ev)

    def _drag_path(self, ev: _MouseEvent) -> list[dict[str, float]] | None:
        """Simplified true trajectory of a drag, when it is not just a line.

        Extension over the AgentNet format for drawing-heavy domains (CAD
        sketching, freehand annotation): a curved drag — a circle, an orbit
        gesture, a marker stroke — is not reproducible from its endpoints.
        The path is auxiliary; args/pyautogui_code stay strictly linear."""
        p = self.params
        if not p.include_drag_paths or ev.press_pos is None or ev.release_pos is None:
            return None
        pts = self.track.samples_between(ev.t, ev.end_t)
        if len(pts) < 3:
            return None
        a, b = ev.press_pos, ev.release_pos
        max_dev = max(_perp_dist(pt[1:], a, b) for pt in pts[1:-1])
        if max_dev < p.drag_path_deviation_px:
            return None                      # essentially straight — endpoints suffice
        simp = _rdp(pts, p.drag_path_epsilon_px)
        if len(simp) > p.drag_path_max_points:
            step = (len(simp) - 1) / (p.drag_path_max_points - 1)
            simp = [simp[round(i * step)] for i in range(p.drag_path_max_points)]
        return [{"t": round(t, 3), **self._norm((x, y))} for t, x, y in simp]

    def _emit_drag(self, ev: _MouseEvent) -> None:
        p0, p1 = ev.press_pos, ev.release_pos
        n0, n1 = self._norm(p0), self._norm(p1)
        code = (f"pyautogui.moveTo(x={n0['x']}, y={n0['y']}); "
                f"pyautogui.dragTo(x={n1['x']}, y={n1['y']}, button={ev.button!r})")
        code = self._wrap_modifiers(code, ev.modifiers)
        action = {
            "t_start": round(ev.t, 3),
            "t_end": round(ev.end_t, 3),
            "action": "dragTo",
            "args": {"from": n0, "to": n1, "button": ev.button},
            "pixels": {"from": self._pixels(p0), "to": self._pixels(p1)},
            "modifiers": ev.modifiers,
            "pyautogui_code": code,
            "observation": self._observation(ev.t, mouse=True),
            "evidence": {"mouse_button_indices": [ev.source_index]},
        }
        path = self._drag_path(ev)
        if path:
            action["path"] = path
        self._emit(action)


# ------------------------------------------------------------------ reduction
def _modifier_intervals(keystrokes: list[dict[str, Any]]):
    mods, capslock_taps = [], []
    for i, ev in enumerate(keystrokes):
        label = ev["key"]
        if keymap.is_modifier(label):
            mods.append({"name": keymap.MODIFIERS[label], "press_t": ev["press_t"],
                         "release_t": ev["release_t"], "index": i, "used": False})
        elif label == "CAPSLOCK":
            capslock_taps.append(ev["press_t"])
    return mods, sorted(capslock_taps)


def _active_mods(mods, t: float, tol: float) -> list[str]:
    out = []
    for m in mods:
        if m["press_t"] - tol <= t <= m["release_t"] + tol:
            out.append(m["name"])
            m["used"] = True
    return out


def _capslock_on(taps: list[float], t: float) -> bool:
    return bisect.bisect_right(taps, t) % 2 == 1


def reduce_events(
    cursor_samples: list[dict[str, Any]],
    mouse_events: list[dict[str, Any]],
    keystrokes: list[dict[str, Any]],
    *,
    screen_w: float,
    screen_h: float,
    fps: float = 30.0,
    params: ReduceParams | None = None,
) -> list[dict[str, Any]]:
    """Reduce raw event streams into OpenCUA/AgentNet-style actions."""
    params = params or ReduceParams()
    track = CursorTrack(cursor_samples)
    red = _Reducer(track=track, screen_w=screen_w, screen_h=screen_h,
                   fps=fps, params=params)

    mods, caps_taps = _modifier_intervals(keystrokes)

    stream: list[tuple[float, int, Any]] = []   # (t, tiebreak, element)
    for i, ev in enumerate(keystrokes):
        label = ev["key"]
        if keymap.is_modifier(label):
            continue
        stream.append((float(ev["press_t"]), 1, _KeyEvent(
            t=float(ev["press_t"]), end_t=float(ev["release_t"]), label=label,
            modifiers=_active_mods(mods, float(ev["press_t"]), params.modifier_tolerance_s),
            capslock=_capslock_on(caps_taps, float(ev["press_t"])),
            source_index=i,
        )))
    for i, ev in enumerate(mouse_events):
        press_t, release_t = float(ev["press_t"]), float(ev["release_t"])
        button = ev.get("button", "left")
        if params.button_map and ev.get("source_key") in params.button_map:
            button = params.button_map[ev["source_key"]]
        stream.append((press_t, 0, _MouseEvent(
            t=press_t, end_t=release_t, button=button,
            press_pos=track.pos_at(press_t, params.cursor_max_gap_s),
            release_pos=track.pos_at(release_t, params.cursor_max_gap_s),
            modifiers=_active_mods(mods, press_t, params.modifier_tolerance_s),
            source_index=i,
        )))

    # lone modifier taps (never combined with any key/mouse event) become press()
    for m in mods:
        if not m["used"]:
            stream.append((float(m["press_t"]), 2, _KeyEvent(
                t=float(m["press_t"]), end_t=float(m["release_t"]),
                label=f"_MOD_{m['name'].upper()}",
                modifiers=[], capslock=False, source_index=m["index"],
            )))

    stream.sort(key=lambda item: (item[0], item[1]))

    for _, _, el in stream:
        if isinstance(el, _MouseEvent):
            red.on_mouse(el)
        elif el.label.startswith("_MOD_"):
            red.flush_write()
            red.flush_clicks()
            key_name = el.label.removeprefix("_MOD_").lower()
            if (red._press is not None and red._press["key"] == key_name
                    and el.t - red._press["t1"] <= params.press_repeat_gap_s):
                red._press["count"] += 1
                red._press["t1"] = el.end_t
                red._press["sources"].append(el.source_index)
            else:
                red.flush_press()
                red._press = {"key": key_name, "count": 1, "t0": el.t,
                              "t1": el.end_t, "sources": [el.source_index]}
        else:
            red.on_key(el)

    red.flush_all()

    if params.terminate_status:
        last_t = red.actions[-1]["t_end"] if red.actions else 0.0
        red._emit({
            "t_start": last_t, "t_end": last_t,
            "action": "terminate",
            "args": {"status": params.terminate_status},
            "pyautogui_code": f"computer.terminate(status={params.terminate_status!r})",
            "observation": {"keyframe_t": last_t,
                            "keyframe_frame": int(round(last_t * fps))},
            "evidence": {},
        })
    return red.actions


# ------------------------------------------------------------------- file I/O
def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_project(project_dir: str | Path) -> dict[str, Any]:
    """Load extracted events from a published data/<id> dir (final_*) or a
    processing run dir (trace/*)."""
    d = Path(project_dir)
    if (d / "cursor" / "final_cursor_events.jsonl").exists():
        cursor_path = d / "cursor" / "final_cursor_events.jsonl"
        mouse_path = d / "cursor" / "final_mouse_events.jsonl"
        keys_path = d / "keystrokes" / "final_keystrokes.json"
    elif (d / "trace" / "cursor" / "cursor_events.jsonl").exists():
        cursor_path = d / "trace" / "cursor" / "cursor_events.jsonl"
        mouse_path = d / "trace" / "cursor" / "mouse_events.jsonl"
        keys_path = d / "trace" / "keystrokes" / "keystrokes.json"
    else:
        raise FileNotFoundError(
            f"no extracted events found under {d} (expected final_* or trace/* artifacts)")

    keystroke_doc = json.loads(keys_path.read_text())
    selection = json.loads((d / "selection.json").read_text())
    screen_roi = selection.get("screen", {}).get("roi") or selection.get("roi")
    return {
        "id": selection.get("id", d.name),
        "cursor": _read_jsonl(cursor_path),
        "mouse": _read_jsonl(mouse_path) if mouse_path.exists() else [],
        "keystrokes": keystroke_doc.get("events", []),
        "keystroke_meta": keystroke_doc.get("meta", {}),
        "screen_w": float(screen_roi["width"]),
        "screen_h": float(screen_roi["height"]),
        "fps": float(selection.get("fps") or keystroke_doc.get("meta", {}).get("fps") or 30.0),
        "sources": {"cursor": str(cursor_path), "mouse": str(mouse_path),
                    "keystrokes": str(keys_path)},
    }


def reduce_project(
    project_dir: str | Path,
    output_path: str | Path | None = None,
    params: ReduceParams | None = None,
) -> dict[str, Any]:
    """Run the reduction for one project and write the actions JSON."""
    params = params or ReduceParams()
    inputs = load_project(project_dir)
    actions = reduce_events(
        inputs["cursor"], inputs["mouse"], inputs["keystrokes"],
        screen_w=inputs["screen_w"], screen_h=inputs["screen_h"],
        fps=inputs["fps"], params=params,
    )
    n_raw = len(inputs["cursor"]) + len(inputs["mouse"]) + len(inputs["keystrokes"])
    from collections import Counter
    doc = {
        "schema": SCHEMA_VERSION,
        "id": inputs["id"],
        "screen": {"width": inputs["screen_w"], "height": inputs["screen_h"]},
        "fps": inputs["fps"],
        "params": params.as_dict(),
        "sources": inputs["sources"],
        "stats": {
            "n_raw_events": n_raw,
            "n_raw_cursor": len(inputs["cursor"]),
            "n_raw_mouse_buttons": len(inputs["mouse"]),
            "n_raw_keystrokes": len(inputs["keystrokes"]),
            "n_actions": len(actions),
            "reduction_ratio": round(n_raw / max(1, len(actions)), 1),
            "action_histogram": dict(Counter(a["action"] for a in actions)),
        },
        "actions": actions,
    }
    if output_path is None:
        output_path = Path(project_dir) / "actions" / "final_actions_opencua.json"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(doc, indent=2))
    doc["output_path"] = str(output_path)
    return doc
