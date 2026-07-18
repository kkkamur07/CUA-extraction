# Learnings

Notes from debugging the cursor-detector regression (Jul 2026), where models
trained on *more* data scored *worse* than earlier models trained on less.
Final outcome after the fixes below, same model/hypers/split: mAP50 0.51 → 0.86,
precision 0.71 → 0.95, recall 0.54 → 0.80 (`artifacts/models/cleaned-yolo11m-adamw`).

## 1. Label on the exact pixels you train on

The annotation preview was decoded with ffmpeg fast input seek by *timestamp*
(`-ss t` before `-i`), while training exported frames with OpenCV by *frame
number* (`CAP_PROP_POS_FRAMES`). The two can disagree by a frame, and at 30fps
a fast-moving cursor is tens of pixels away on the neighboring frame. Result:
~13% of old boxes and ~20% of newly added boxes sat off the cursor (some on
empty background), poisoning both train and val. This alone explains
"more data → worse model": the new annotation session added mostly-misaligned
labels.

Rule: every consumer of a labeled frame (preview, patch saving, dataset
export) must go through one shared decode path keyed by frame number. That is
what `cursor dump-frame` + the `/api/videos/[name]/frame?frame=N` route now
guarantee — the workbench canvas shows the identical pixels the trainer sees.

## 2. Trust placement checks, not eyeballs, for label QA

Template-matching each saved patch against its actual training frame catches
misalignment mechanically. Judge placement by the *offset* of the best match,
not the raw match score — patches that pass through a browser canvas are
double-JPEG-compressed, so scores run low (0.3–0.6) even for perfectly placed
boxes. A box whose patch matches in place at any score is fine; a box whose
patch is found >3px away needs snapping or review.

- `scripts/clean_cursor_manifest.py` snaps recoverable boxes, quarantines
  unrecoverable ones to `templates.review.jsonl`, and dedupes overlapping
  boxes per frame (re-annotating a frame previously *appended*, leaving two
  ground-truth boxes for one cursor — capping recall at ~50% on those frames).
- `scripts/audit_yolo_data.py` now has an `alignment` section; run it before
  any training. The cleanup pass turned 202 rows into 169 verified ones
  (13 snapped, 11 duplicates dropped, 22 sent to review).

## 3. Ultralytics epoch indexing is off by one between CSV and checkpoints

`results.csv` logs epochs 1-indexed (`self.epoch + 1`); `save_period`
checkpoints are named 0-indexed (`epoch{self.epoch}.pt`). So the best CSV
epoch N lives in `epoch{N-1}.pt`. Picking `epoch{N}.pt` silently loads the
*next* epoch's weights — on a noisy 47-image val set that cost ~5 mAP50
points. The tell: `summary.json`'s claimed selection metrics disagreed with
re-validating `best.pt`. After the fix they match to the 4th decimal.

## 4. Tuned hyperparameters are tied to their optimizer

`best_hyperparameters.yaml` from the tune does not record `optimizer`, and
`optimizer=auto` resolves to SGD. Reusing an AdamW-tuned lr0 (1e-3) with SGD
made training collapse immediately (mAP50 ~0.0004, frozen metrics). Always
pass `--optimizer AdamW --mosaic 0` alongside that YAML, and treat
flat/identical val metrics across epochs as divergence, not slow learning.

## 5. Small val sets make every decision noisy

With 47 val boxes, one missed cursor is ~2% recall, the mAP50 curve swings
±0.1 between adjacent epochs, and 10-epoch tuning trials mostly rank noise.
Prefer re-annotating the quarantined hard frames (fast-motion, dialogs) and
growing val before trusting further hyperparameter tuning. Also note screen
recordings blur/ghost fast cursors — some frames legitimately show two cursor
images; label the sharper one consistently or skip the frame.

## Operational checklist before a training run

1. `python scripts/audit_yolo_data.py` — expect 0 misaligned, 0 duplicates.
2. If not clean: `python scripts/clean_cursor_manifest.py` (backs up the
   manifest, writes `templates.review.jsonl` for manual re-labeling).
3. Re-label review frames in the workbench (preview is frame-accurate now).
4. Train with explicit `--optimizer` when using tuned hypers.
5. Check `summary.json`: `checkpoint_selection` metrics must match the final
   re-validated metrics; delete `weights/epoch*.pt` afterwards (~16GB per run).
