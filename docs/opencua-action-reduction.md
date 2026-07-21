# OpenCUA/AgentNet action reduction

Branch `opencua-action-reduction`. Converts the extracted low-level event
streams into the compact pyautogui-space action format proposed by **OpenCUA:
Open Foundations for Computer-Use Agents** (arXiv:2508.09123, NeurIPS 2025) —
Section 2.2 "Constructing compact state-action trajectories" and Table 1's
action space. Pure post-processing: it consumes only the already-extracted
artifacts and never reads the video.

## What the paper specifies (and how each rule is implemented)

| AgentNet rule (§2.2 / Table 1 / App. C.3.1) | Implementation (`src/cursor/reduce/opencua.py`) |
|---|---|
| "Mouse move events are treated as preconditions for clicks or drags, and only their start and end positions are retained" | Cursor track samples are never emitted as actions. A click takes its coordinate from the cursor position at button-press; a drag emits `moveTo(start); dragTo(end)`. All other motion (noise, idle wandering) is discarded. |
| "Scrolls are merged into single-directional actions with accumulated wheel counts" | **Not derivable**: the keyboard overlay carries no scroll-wheel signal, so the extraction has no scroll events. Documented limitation. |
| "Consecutive key presses are merged into text input strings" | Printable keys accumulate into `write(text)` (shift- and capslock-aware, US layout; numpad chars included). The buffer flushes on a >2 s gap, on any special key/hotkey, or when a mouse action intervenes. |
| "Modifier combinations (e.g., CTRL+C) are abstracted into hotkey actions" | A non-modifier key whose press falls inside a held ctrl/alt/win interval → `hotkey(mods..., key)` in canonical order (`ctrl, alt, shift, win`). Shift+printable stays text; shift+special (e.g. shift+arrow selection) is a hotkey. |
| "We also combine common multistep gestures such as drags or double-clicks" | A button-hold is a `dragTo` iff the cursor **moved during the hold** (max excursion from the press position ≥ `drag_min_px`, 12 px) — endpoint displacement alone would misclassify orbit gestures that end where they started as clicks. Same-button clicks within 0.4 s and 12 px merge into `doubleClick`/`tripleClick` (spatial check skipped when the YOLO track has a gap — time-only fallback). |
| Action space: `click/rightClick/middleClick/doubleClick/tripleClick/moveTo/dragTo/write/press/hotkey/terminate` (Table 1) | Emitted names match; `press` consolidates immediate repeats via `presses=N` (the paper's "consolidate repetitive keypresses with count"). A `terminate(status=...)` action is appended (configurable/disable-able). |
| State–action matching: "for mouse clicks, we backtrack to the beginning of the mouse's pre-movement phase" (§2.2 (2)) | Each action carries `observation.keyframe_t/keyframe_frame`: for mouse actions, walk the cursor track backwards from the press until motion falls below `stationary_eps_px` (max 5 s); for keyboard actions, 0.2 s before the first press. Without frame-diffing the video this approximates "last visually distinct frame". |
| Normalized coordinates (AgentNetBench examples use `x=0.988, y=0.081`) | `args.x/y` are normalized to the screen crop, 4 decimals, clamped to [0, 1]; raw crop pixels are kept in `pixels`. |

### Extension beyond the paper

Modifier-held mouse actions (CTRL+drag, SHIFT+click — constant in CAD) have no
representation in Table 1. They are kept as `click`/`dragTo` with a
`modifiers` list, and the `pyautogui_code` wraps the call in
`keyDown(...)`/`keyUp(...)`. Consumers wanting strict Table-1 actions can drop
the wrapper.

## Output format

`data/<id>/actions/final_actions_opencua.json`:

```json
{
  "schema": "opencua-reduction/1",
  "id": "tut-1",
  "screen": {"width": 1155.0, "height": 941.0},
  "fps": 30.0,
  "params": {"drag_min_px": 12.0, "...": "..."},
  "stats": {"n_raw_events": 7368, "n_actions": 503, "reduction_ratio": 14.6,
             "action_histogram": {"dragTo": 288, "click": 57, "...": 0}},
  "actions": [
    {"idx": 2, "t_start": 3.633, "t_end": 4.2,
     "action": "dragTo",
     "args": {"from": {"x": 0.3694, "y": 0.2382}, "to": {"x": 0.3281, "y": 0.0461},
              "button": "left"},
     "pixels": {"from": {"x": 426.6, "y": 224.2}, "to": {"x": 379.0, "y": 43.4}},
     "modifiers": [],
     "pyautogui_code": "pyautogui.moveTo(x=0.3694, y=0.2382); pyautogui.dragTo(x=0.3281, y=0.0461, button='left')",
     "observation": {"keyframe_t": 3.4, "keyframe_frame": 102},
     "evidence": {"mouse_button_indices": [2]}}
  ]
}
```

Timestamps are clip-timeline seconds (same reference as all `final_*`
artifacts); `evidence` indexes back into the source event files so every
action is auditable.

## Usage

```bash
# per project (data/<id> published dir, or a processing run dir):
python -m cursor reduce-actions data/solidworks-tut
python -m cursor reduce-actions data/solidworks-tut --json          # full doc to stdout
python -m cursor reduce-actions runs/my-run --terminate-status none # no terminate action
```

The workbench's "Generate final" flow (`process-events` route) now runs the
reduction automatically after final-event normalization and registers
`final_actions_opencua` in `metadata.json`.

Tests (stdlib only): `PYTHONPATH=src python tests/test_reduce_opencua.py` —
15 cases covering every rule above.

### Visual verification

```bash
python -m cursor view-actions data/<id>        # http://127.0.0.1:8899
```

Serves a local viewer (stdlib HTTP server with byte-range support) that plays
`final_video.mp4` with the reduced actions rendered on top of the frame:
click ripples / double- and triple-click badges, dashed drag arrows with a
progress dot, a keycast banner for `write`/`hotkey`/`press` (plus held
modifiers), a color-coded action timeline, and a clickable auto-following
action list. Coordinates are drawn in final-video space, so any systematic
offset in the extraction would be immediately visible.

## All changes on this branch

1. **New package `src/cursor/reduce/`** — `opencua.py` (reduction engine,
   documented above), `keymap.py` (overlay labels → pyautogui key space).
2. **New CLI command `reduce-actions`** (`src/cursor/cli/cli.py`,
   `cli_handlers.py`) + wrapper `scripts/reduce_actions_opencua.py`.
3. **Workbench integration** — `process-events` route runs the reduction after
   normalization; artifact registered in the processing summary + metadata.
4. **Bug fix: inverted M1/M2 mouse-button mapping.** `MOUSE_BUTTONS`/
   `MOUSE_BUTTON_MAPPING` said `M1→right, M2→left`. On the TooTallToby overlay
   M1 is the **left** button, and in all six data samples M1 accounts for
   ~97 % of presses — the dominant button in any GUI workflow is the left one.
   Fixed to `M1→left, M2→right` in `scripts/split_mouse_events.py`,
   `scripts/filter_cursor_events.py`, `src/cursor/keypress/keystrokes.py`.
   Because *already-extracted* artifacts carry the inverted labels, the
   reducer additionally remaps via `source_key` by default
   (`--no-remap-buttons` restores trust-the-input behaviour). Data extracted
   after this fix is correct at the source and the remap becomes a no-op.
5. **Updated sample data** — `final_actions_opencua.json` generated for all
   six samples (5.3k–7.8k raw events → 280–532 actions, 14.6–20.3:1).
6. **Tests** — `tests/test_reduce_opencua.py`.

## Known limitations

- **No scroll actions**: the overlay records no wheel signal.
- **No `moveTo`-only hover actions**: deliberate hovers (e.g. hover menus)
  cannot be distinguished from noise without UI-state signals; per the
  requirement, motion counts only when tied to a click, drag, or key press.
- **Coordinates depend on YOLO cursor coverage**: actions during detection
  gaps (> `cursor_max_gap_s` from any sample) are emitted without coordinates
  rather than with guessed ones.
- **Keyframe timestamps approximate** "last visually distinct frame" using
  cursor kinematics only (no video frame-diff, by design).
- **US keyboard layout** assumed for shifted characters; numpad assumed in
  NumLock mode (the overlay draws digits).
