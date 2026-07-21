"""Tests for the OpenCUA action reduction (src/cursor/reduce).

Run:  PYTHONPATH=src python tests/test_reduce_opencua.py
(or via pytest; only the standard library is required)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cursor.reduce import ReduceParams, reduce_events  # noqa: E402

SCREEN = {"screen_w": 1000.0, "screen_h": 800.0}
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    if not cond:
        FAILURES.append(f"{name}: {detail}")


def cursor_path(points: list[tuple[float, float, float]]):
    """[(t, x, y)] -> cursor samples."""
    return [{"t": t, "x": x, "y": y, "confidence": 0.9} for t, x, y in points]


def key(k: str, t0: float, t1: float):
    return {"type": "keystroke", "key": k, "press_t": t0, "release_t": t1}


def btn(button: str, t0: float, t1: float):
    return {"type": "mouse_button", "button": button, "press_t": t0, "release_t": t1}


P = ReduceParams(terminate_status=None)   # terminate tested separately


def actions_of(cursor, mouse, keys, params=P):
    return reduce_events(cursor, mouse, keys, fps=30.0, params=params, **SCREEN)


# 1. single click at cursor position; noisy moves around it are dropped
def test_click_and_noise():
    cur = cursor_path([(0.0, 100, 100), (0.5, 300, 220), (1.0, 500, 400),
                       (1.5, 505, 402), (1.6, 506, 402),
                       (2.0, 900, 700), (2.5, 120, 80)])
    acts = actions_of(cur, [btn("left", 1.45, 1.55)], [])
    check("click count", len(acts) == 1, f"{[a['action'] for a in acts]}")
    a = acts[0]
    check("click name", a["action"] == "click", a["action"])
    check("click xy", abs(a["pixels"]["x"] - 503.5) < 3 and abs(a["pixels"]["y"] - 401) < 3,
          str(a["pixels"]))
    check("click norm", a["args"]["x"] == round(a["pixels"]["x"] / 1000, 4), str(a["args"]))
    check("click t", a["t_start"] == 1.45 and a["t_end"] == 1.55, f"{a['t_start']}-{a['t_end']}")
    # keyframe backtracks to before the approach movement started
    check("click keyframe", a["observation"]["keyframe_t"] <= 0.5,
          str(a["observation"]))


# 2. double and triple click merging; far-apart clicks stay separate
def test_multi_click():
    cur = cursor_path([(0.0, 200, 200), (5.0, 200, 200)])
    mouse = [btn("left", 1.0, 1.05), btn("left", 1.2, 1.25),                  # double
             btn("left", 2.5, 2.55), btn("left", 2.7, 2.75), btn("left", 2.9, 2.95),  # triple
             btn("left", 4.5, 4.55)]                                          # single
    acts = actions_of(cur, mouse, [])
    names = [a["action"] for a in acts]
    check("multi-click", names == ["doubleClick", "tripleClick", "click"], str(names))


# 3. drag = moveTo precondition + dragTo, mid-path discarded
def test_drag():
    cur = cursor_path([(0.0, 100, 100), (1.0, 100, 100), (1.5, 250, 300),
                       (2.0, 400, 500), (2.5, 400, 500)])
    acts = actions_of(cur, [btn("left", 1.0, 2.0)], [])
    check("drag count", len(acts) == 1, str([a["action"] for a in acts]))
    a = acts[0]
    check("drag name", a["action"] == "dragTo", a["action"])
    check("drag from", abs(a["pixels"]["from"]["x"] - 100) < 3, str(a["pixels"]))
    check("drag to", abs(a["pixels"]["to"]["x"] - 400) < 3, str(a["pixels"]))
    check("drag code", "moveTo" in a["pyautogui_code"] and "dragTo" in a["pyautogui_code"],
          a["pyautogui_code"])


# 4. right button click name
def test_right_click():
    cur = cursor_path([(0.9, 50, 60)])
    acts = actions_of(cur, [btn("right", 1.0, 1.1)], [])
    check("rightClick", acts[0]["action"] == "rightClick", acts[0]["action"])


# 5. consecutive printable keys merge into write(); shift capitalizes
def test_write_merge_shift():
    keys = [
        key("LSHIFT", 0.9, 1.15),
        key("H", 1.0, 1.1),
        key("E", 1.3, 1.4),
        key("Y", 1.6, 1.7),
        key("1", 1.9, 2.0),
    ]
    acts = actions_of([], [], keys)
    check("write count", len(acts) == 1, str([a["action"] for a in acts]))
    a = acts[0]
    check("write text", a["args"]["text"] == "Hey1", str(a["args"]))
    check("write t", a["t_start"] == 1.0 and a["t_end"] == 2.0, f"{a['t_start']}-{a['t_end']}")


# 6. write splits on time gap
def test_write_gap_split():
    keys = [key("A", 1.0, 1.1), key("B", 1.5, 1.6), key("C", 5.0, 5.1)]
    acts = actions_of([], [], keys)
    texts = [a["args"]["text"] for a in acts if a["action"] == "write"]
    check("write split", texts == ["ab", "c"], str(texts))


# 7. modifier combos become hotkey; canonical modifier order
def test_hotkey():
    keys = [key("LCTRL", 0.9, 1.3), key("LSHIFT", 0.95, 1.3), key("S", 1.0, 1.1)]
    acts = actions_of([], [], keys)
    check("hotkey count", len(acts) == 1, str([a["action"] for a in acts]))
    a = acts[0]
    check("hotkey keys", a["args"]["keys"] == ["ctrl", "shift", "s"], str(a["args"]))
    check("hotkey code", a["pyautogui_code"] == "pyautogui.hotkey('ctrl', 'shift', 's')",
          a["pyautogui_code"])


# 8. shift + arrow is a hotkey (selection), not write/press
def test_shift_arrow():
    keys = [key("LSHIFT", 0.9, 1.3), key("RIGHT", 1.0, 1.1)]
    acts = actions_of([], [], keys)
    check("shift-arrow", acts[0]["action"] == "hotkey"
          and acts[0]["args"]["keys"] == ["shift", "right"], str(acts[0]["args"]))


# 9. special keys become press(); immediate repeats consolidate with count
def test_press_repeat():
    keys = [key("ENTER", 1.0, 1.1),
            key("DOWN", 2.0, 2.05), key("DOWN", 2.3, 2.35), key("DOWN", 2.6, 2.65),
            key("ESC", 9.0, 9.1)]
    acts = actions_of([], [], keys)
    names = [(a["action"], a["args"].get("key"), a["args"].get("presses")) for a in acts]
    check("press seq", names == [("press", "enter", 1), ("press", "down", 3),
                                 ("press", "esc", 1)], str(names))
    check("press code", acts[1]["pyautogui_code"] == "pyautogui.press('down', presses=3)",
          acts[1]["pyautogui_code"])


# 10. lone modifier tap becomes press('shift')
def test_lone_modifier():
    acts = actions_of([], [], [key("LSHIFT", 1.0, 1.2)])
    check("lone shift", [(a["action"], a["args"].get("key")) for a in acts]
          == [("press", "shift", )[:2]], str(acts))


# 11. modifier held over a click is recorded and wrapped in keyDown/keyUp
def test_modified_click():
    cur = cursor_path([(0.9, 300, 300)])
    acts = actions_of(cur, [btn("left", 1.0, 1.1)], [key("LCTRL", 0.8, 1.4)])
    a = acts[0]
    check("mod click mods", a["modifiers"] == ["ctrl"], str(a))
    check("mod click code", a["pyautogui_code"].startswith("pyautogui.keyDown('ctrl');"),
          a["pyautogui_code"])
    check("mod consumed", len(acts) == 1, str([x["action"] for x in acts]))


# 12. write buffer flushes when a click intervenes (ordering preserved)
def test_interleave_order():
    cur = cursor_path([(1.9, 700, 100)])
    acts = actions_of(cur, [btn("left", 2.0, 2.1)],
                      [key("A", 1.0, 1.1), key("B", 3.0, 3.1)])
    names = [a["action"] for a in acts]
    check("interleave", names == ["write", "click", "write"], str(names))


# 13. terminate action appended with status
def test_terminate():
    acts = reduce_events([], [], [key("A", 1.0, 1.1)], fps=30.0,
                         params=ReduceParams(terminate_status="success"), **SCREEN)
    check("terminate", acts[-1]["action"] == "terminate"
          and acts[-1]["args"]["status"] == "success", str(acts[-1]))


# 14. numpad digits are written as characters
def test_numpad_write():
    keys = [key("NUM1", 1.0, 1.1), key("NUM.", 1.3, 1.4), key("NUM5", 1.6, 1.7)]
    acts = actions_of([], [], keys)
    check("numpad write", acts[0]["args"]["text"] == "1.5", str(acts[0]["args"]))


# 15b. curved drag (circle-like) keeps its simplified true path
def test_drag_path_curved():
    import math as m
    pts = [(1.0 + i * 0.1, 400 + 150 * m.cos(m.pi * i / 10), 400 + 150 * m.sin(m.pi * i / 10))
           for i in range(11)]  # half-circle from (550,400) to (250,400)
    acts = actions_of(cursor_path(pts), [btn("left", 1.0, 2.0)], [])
    a = acts[0]
    check("curved is drag", a["action"] == "dragTo", a["action"])
    check("curved has path", "path" in a and len(a["path"]) >= 4,
          str(len(a.get("path", []))))
    if "path" in a:
        ys = [p["y"] for p in a["path"]]
        check("path bulges", max(ys) > a["args"]["from"]["y"] + 0.1, str(ys))


# 15c. straight drag stores no path (endpoints suffice)
def test_drag_path_straight():
    pts = [(1.0 + i * 0.1, 100 + 30 * i, 100 + 20 * i) for i in range(11)]
    acts = actions_of(cursor_path(pts), [btn("left", 1.0, 2.0)], [])
    check("straight no path", "path" not in acts[0], str(acts[0].get("path"))[:60])


# 15. capslock capitalizes letters until toggled off
def test_capslock():
    keys = [key("CAPSLOCK", 0.5, 0.6), key("A", 1.0, 1.1),
            key("CAPSLOCK", 2.0, 2.1), key("B", 3.0, 3.1)]
    acts = actions_of([], [], keys)
    texts = [a["args"]["text"] for a in acts if a["action"] == "write"]
    check("capslock", texts == ["A", "b"], str(texts))


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)} tests, {len(FAILURES)} failures")
    for f in FAILURES:
        print("  FAIL", f)
    sys.exit(1 if FAILURES else 0)
