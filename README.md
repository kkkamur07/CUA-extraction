# CUA extraction

This project extracts aligned multimodal tutorial evidence from screen-recorded
videos: **Cursor observations**, **Keystrokes**, and narrated **Action–Intent pairs**,
published as one **Workflow sample** per **Processing run**.

## Quick start

```bash
git clone https://github.com/kkkamur07/CUA-extraction.git
cd CUA-extraction
git lfs install && git lfs pull
python3 -m venv .venv && source .venv/bin/activate && pip install -e .
cp .env.example .env   # set OPENAI_API_KEY
cd frontend && npm install && npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

1. Put tutorial MP4s in `video/` (local only; not committed).
2. In the workbench: set **screen** + **keyboard** crops/ranges, save selection.
3. Run **cursor**, **keyboard**, and **intent** extraction from their tabs.
4. Click **Generate final events + video** to publish under `data/<id>/`.

Cursor detection uses weights at `artifacts/models/cursor/weights/best.pt`
(pulled via Git LFS above). If LFS is unavailable, train your own detector
(see below) or place a `best.pt` at that path.

## Run the labeling UI

Put tutorial MP4s in `video/` (5–6 is fine). Then start the Next.js workbench:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). For each video:

1. **Crop ROI** — seek, drag the application screen region, set start/end, save.
2. **Keyboard ROI** — same flow for the on-screen keyboard region/range.
3. **Cursor labels** — draw tight boxes on the screen crop (←/→ to step frames).

Selections for processing runs are written under `runs/<video-id>/selection.json`.
Cursor training labels land under `data/<video-id>/templates/`.
The screen track is also flattened to top-level `roi` / `start` / `end` so YOLO
scripts keep working:

```bash
.venv/bin/python scripts/train_yolo.py --selection data/<video-id>/selection.json
.venv/bin/python scripts/predict_yolo_video.py --selection runs/<video-id>/selection.json
```

## Processing run and published-data contract

Intermediate processing artifacts live under `runs/<id>`. The final published
dataset is written under `data/<id>`:

| Path | Role |
|------|------|
| `selection.json` | Project selection: Crop ROI, Keyboard ROI, time range, fps, video path |
| `selection.json.corner_masks` | Final-video white overlays in screen-crop coordinates |
| `keystrokes/raw_keystrokes.json` | Unfiltered keyboard-overlay detections |
| `trace/keystrokes/keystrokes.json` | Filtered keyboard events (trace) |
| `data/<id>/keystrokes/final_keystrokes.json` | Final filtered keyboard events |
| `trace/keystrokes/keystroke_job.json` | Async keystroke job progress (trace) |
| `cursor/raw_cursor_events.jsonl` | Unfiltered cursor detector output |
| `trace/cursor/cursor_events.jsonl` | Filtered cursor events (trace) |
| `trace/cursor/mouse_events.jsonl` | Normalized mouse events (trace) |
| `data/<id>/cursor/final_cursor_events.jsonl` | Final filtered cursor movement |
| `data/<id>/cursor/final_mouse_events.jsonl` | Final normalized mouse-button events |
| `data/<id>/actions/final_actions_opencua.json` | OpenCUA/AgentNet-style reduced actions (see `docs/opencua-action-reduction.md`) |
| `data/<id>/trace/final_processing_summary.json` | Finalization trace |
| `trace/intent/speech_full.json` | Full-video ASR trace |
| `trace/intent/speech_trimmed.json` | Trimmed-range ASR trace |
| `trace/intent/action_intent_pairs.json` | Action–Intent pairs trace |
| `trace/intent/intent_job.json` | Async intent job progress (trace) |
| `trace/summary/summary.json` | Intermediate task summary (trace) |
| `data/<id>/intent/final_speech_full.json` | Final full-video speech artifact |
| `data/<id>/intent/final_speech_trimmed.json` | Final trimmed speech artifact |
| `data/<id>/intent/final_action_intent_pairs.json` | Final Action–Intent pairs |
| `data/<id>/summary/final_summary.json` | Final task summary |
| `data/<id>/final_video.mp4` | Cropped, trimmed, white-masked final video |
| `data/<id>/final_video.json` | Final-video render manifest |
| `data/<id>/metadata.json` | Published artifact manifest |

### Workflow sample shape

```json
{
  "id": "<run-id>",
  "summary": "",
  "action_intent_pairs": [
    {"action": "...", "intent": "...", "start_t": 0.0, "end_t": 1.0}
  ],
  "raw_events": [
    {"type": "cursor", "t": 0.0, "x": 0, "y": 0, "confidence": 0.0, "click_candidate": false},
    {"type": "keystroke", "key": "A", "press_t": 0.0, "release_t": 0.1, "clipped": false}
  ]
}
```

Write an empty stub sample from an existing selection:

```bash
.venv/bin/python -m cursor stub-workflow runs/<id>
```

Or from Python:

```python
from cursor.workflow import write_stub_workflow_sample

write_stub_workflow_sample("runs/<id>")
```

### Dual speech ASR / Intent extraction

ASR and Action–Intent / summary both use the **OpenAI API**
(`whisper-1` + your chat model) via `OPENAI_API_KEY`.

```bash
cp .env.example .env   # set OPENAI_API_KEY
.venv/bin/python -m cursor extract-intent runs/<id>
```

## OpenCUA action reduction

`python -m cursor reduce-actions data/<id>` converts the extracted event
streams into the compact pyautogui action format of the OpenCUA paper
(arXiv:2508.09123): noisy cursor motion is dropped (moves only survive as
click/drag coordinates), key presses merge into `write`/`hotkey`/`press`
actions, drags and double/triple clicks are combined, and every action carries
timestamps plus an observation keyframe. The workbench runs this automatically
during **Generate final events + video**. Details, schema, and the M1/M2
button-mapping fix: `docs/opencua-action-reduction.md`.

## Train a YOLO cursor detector

Training source of truth in git is `data/<video-id>/selection.json`, **Cursor
annotations** under `data/<video-id>/templates/` (manifest + patch images), and
the published baseline at `artifacts/models/cursor/weights/best.pt`. The source
MP4 stays local; `selection.json` records its path (for example
`video/solidworks-tut.mp4`). Regenerated `data/<video-id>/yolo-dataset/` exports
are not versioned—rebuild them from selection + annotations when retraining.

```bash
.venv/bin/python scripts/train_yolo.py --selection data/<video-id>/selection.json
```

Device order is **CUDA → MPS → CPU** (`--device` to override). Appearance-class
stratified train/val counts print on prepare/train. Side-by-side `yolo11s` /
`yolo11m` commands (print only unless `--run`):

```bash
.venv/bin/python scripts/train_yolo_compare.py
# .venv/bin/python scripts/train_yolo_compare.py --run
```

Do not auto-overwrite `artifacts/models/cursor/weights/best.pt` — promote the
winner manually after comparing val metrics.

Weights land in `artifacts/models/cursor/weights/best.pt`. Audit annotations first:

```bash
.venv/bin/python scripts/audit_yolo_data.py --selection data/<video-id>/selection.json
```

Render a detection preview video:

```bash
.venv/bin/python scripts/predict_yolo_video.py --selection runs/<video-id>/selection.json
```

For a smaller QuickTime-friendly HEVC/H.265 MP4 with the source audio:

```bash
.venv/bin/python scripts/predict_yolo_video.py \
  --model artifacts/models/cleaned-yolo11m-adamw/weights/best.pt \
  --selection data/solidworks-tut/selection.json \
  --full-video \
  --hevc \
  --output artifacts/predictions/solidworks-tut/cursor-detected-hevc.mp4
```

Preview MP4 + detections JSONL go to `artifacts/predictions/<video-id>/`.

Reduce frame-level detections to the cursor track used by a Processing run:

```bash
python3 scripts/filter_cursor_events.py \
  --input artifacts/predictions/solidworks-tut/detections-cleaned-yolo11m.jsonl \
  --output runs/solidworks-tut/trace/cursor/cursor_events.jsonl
```

The raw detections are preserved. The filtered track uses confidence `0.4`,
one box per frame, and a configurable movement threshold (default **4** pixels;
editable in the Cursor → Extract tab). There is no time-based sampling or
stationary heartbeat. A `filter_summary.json` is written beside the output. If a
`keystrokes.json` artifact is available, pass `--keystrokes` to additionally
write normalized mouse-button events; the overlay convention is `M1` =
right-click and `M2` = left-click.

To split an existing keyboard artifact manually:

```bash
python3 scripts/split_mouse_events.py runs/<video-id>
```

The workbench's **Generate final events + video** button consumes the raw
artifacts already generated by the tabs, writes the filtered `final_` event
files, copies the final intent and summary artifacts, maps M1 to right-click
and M2 to left-click, and renders the final video. Workflow samples are not
generated by this button. Intermediate traces stay under
`runs/<video-id>/trace/`; published files go to `data/<video-id>/`.

## Render the final video

Render the saved screen region for its selected time range, mask the configured
corner regions with white overlays, and write a silent H.264/AVC video for
QuickTime compatibility:

```bash
.venv/bin/python scripts/render_final_video.py \
  --selection runs/solidworks-tut/selection.json
```

The output is
`data/solidworks-tut/final_video.mp4`, with a JSON render manifest
beside it. In the Screen tab, choose **Draw bottom-left** or **Draw
bottom-right** and drag the rectangle directly on the preview; save the
selection before rendering. Purple tip cards are retained.

Use repeated `--mask X,Y,WIDTH,HEIGHT` values to override the saved white masks
from the command line.

## Layout

- `frontend/` — Next.js multi-video labeling workbench
- `src/cursor/asr/` — ASR backends
- `src/cursor/intent/` — speech → summary / Action–Intent pairs
- `src/cursor/keypress/` — Keyboard ROI keystroke recovery
- `src/cursor/detector/` — Cursor annotations + Cursor observations
- `src/cursor/workflow/` — run contract / Workflow sample
- `src/cursor/cli/` — CLI entrypoints
- `scripts/` — YOLO audit / train / predict
- `video/` — source MP4s (local; not committed)
- `data/<id>/` — training source of truth (selection + Cursor annotations)
- `artifacts/models/cursor/weights/best.pt` — published baseline detector
- `runs/<id>/` — Processing run intermediates + Workflow sample

CLI:

```bash
.venv/bin/python -m cursor --help
.venv/bin/python -m cursor extract-intent --help
.venv/bin/python -m cursor extract-keystrokes --help
.venv/bin/python -m cursor extract-cursor --help
```
