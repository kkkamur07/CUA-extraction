# CUA extraction

This project extracts aligned multimodal tutorial evidence from screen-recorded
videos: **Cursor observations**, **Keystrokes**, and narrated **Action–Intent pairs**,
published as one **Workflow sample** per **Processing run**.

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

## Processing run directory contract

Each **Processing run** lives under `runs/<id>/`:

| Path | Role |
|------|------|
| `selection.json` | Project selection: Crop ROI, Keyboard ROI, time range, fps, video path |
| `keystrokes/keystrokes.json` | Keystroke Raw events from the keyboard detector |
| `keystrokes/keystroke_job.json` | Async keystroke job progress (UI polling) |
| `cursor/cursor_events.jsonl` | Cursor observation Raw events (one JSON object per line) |
| `intent/speech_full.json` | Full-video ASR (feeds the Workflow summary) |
| `intent/speech_trimmed.json` | Trimmed-range ASR (feeds Action–Intent pairs) |
| `intent/action_intent_pairs.json` | Ordered Action–Intent pairs (intermediate) |
| `intent/intent_job.json` | Async intent job progress (UI polling) |
| `summary/summary.json` | Optional task summary; prefer the `summary` field on the Workflow sample |
| `workflow_sample.json` | Published **Workflow sample** |

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

Preview MP4 + detections JSONL go to `artifacts/predictions/<video-id>/`.

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
