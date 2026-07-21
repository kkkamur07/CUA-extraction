"""CLI command handlers (kept separate from argparse wiring)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def run_stub_workflow(args: argparse.Namespace) -> None:
    from ..workflow.workflow import write_stub_workflow_sample

    out_path = write_stub_workflow_sample(args.run_dir)
    print(f"Wrote stub Workflow sample to {out_path}")


def run_extract_intent(args: argparse.Namespace) -> None:
    from ..intent.intent import extract_intent

    paths = extract_intent(
        args.run_dir,
        chunk_s=args.chunk_s,
        asr_model=getattr(args, "asr_model", None),
    )
    for name, path in paths.items():
        print(f"Wrote {name} → {path}")


def run_extract_intent_async(args: argparse.Namespace) -> None:
    from ..intent.intent_jobs import run_intent_job

    result = run_intent_job(
        args.run_dir,
        chunk_s=getattr(args, "chunk_s", 600),
        asr_model=getattr(args, "asr_model", None),
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        state = result.get("state")
        n = result.get("n_intents", 0)
        print(f"Intent job {state}: {n} pairs")
        if result.get("error"):
            print(result["error"], file=sys.stderr)
            raise SystemExit(1)


def run_extract_keystrokes(args: argparse.Namespace) -> None:
    from ..keypress.keystrokes import extract_keystrokes

    out_path = extract_keystrokes(
        args.run_dir,
        stride=args.stride,
        layout_name=args.layout,
    )
    print(f"Wrote Keystroke Raw events to {out_path}")


def run_extract_keystrokes_async(args: argparse.Namespace) -> None:
    from ..keypress.keystrokes import run_keystroke_job

    result = run_keystroke_job(args.run_dir, layout_name=args.layout)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(
            f"Keystroke job {result.get('state')}: "
            f"{result.get('n_events', 0)} events → {result.get('path', '')}"
        )


def run_extract_cursor(args: argparse.Namespace) -> None:
    from ..detector.cursor_events import extract_cursor_events

    events_path = getattr(args, "output", None)
    if events_path:
        events_path = Path(events_path)
        if not events_path.is_absolute():
            events_path = Path.cwd() / events_path
    out_path = extract_cursor_events(
        args.run_dir,
        model_path=args.model,
        events_path=events_path,
    )
    print(f"Wrote Cursor observations to {out_path}")


def run_dump_frame(args: argparse.Namespace) -> None:
    """Write one video frame as JPEG to stdout.

    Uses the same OpenCV frame indexing as annotation saving and YOLO dataset
    export, so the frame shown for labeling is exactly the frame trained on.
    """
    import cv2

    from ..detector.processor import read_frame

    video = cv2.VideoCapture(args.video)
    if not video.isOpened():
        print(f"Could not open video: {args.video}", file=sys.stderr)
        raise SystemExit(1)
    try:
        frame_number = args.frame
        if frame_number is None:
            fps = float(video.get(cv2.CAP_PROP_FPS) or 0.0) or 30.0
            frame_number = round(max(0.0, args.time) * fps)
        frame = read_frame(video, frame_number)
    finally:
        video.release()
    if frame is None:
        print(f"Could not read frame {frame_number}", file=sys.stderr)
        raise SystemExit(1)
    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        print("Could not encode frame as JPEG", file=sys.stderr)
        raise SystemExit(1)
    sys.stdout.buffer.write(encoded.tobytes())
    sys.stdout.buffer.flush()


def run_pipeline_cmd(args: argparse.Namespace) -> None:
    from ..workflow.pipeline import PipelineError, run_pipeline

    try:
        result = run_pipeline(
            args.run_dir,
            skip_existing=args.skip_existing,
            raise_on_error=True,
        )
    except PipelineError as exc:
        payload = exc.result.to_dict()
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"Processing run failed for {exc.result.run_id}", file=sys.stderr)
            for name, err in sorted(exc.result.errors.items()):
                print(f"  [{name}] {err}", file=sys.stderr)
            if exc.result.sample_path:
                print(f"Partial sample: {exc.result.sample_path}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"Processing run ok: {result.run_id}")
        for step in result.steps:
            detail = step.path or (", ".join(step.paths) if step.paths else "")
            suffix = f" → {detail}" if detail else ""
            print(f"  [{step.status}] {step.name}{suffix}")
        if result.sample_path:
            print(f"Wrote Workflow sample to {result.sample_path}")


def run_reduce_actions(args: argparse.Namespace) -> None:
    from ..reduce.opencua import ReduceParams, reduce_project

    status = None if args.terminate_status == "none" else args.terminate_status
    params = ReduceParams(
        drag_min_px=args.drag_min_px,
        multi_click_gap_s=args.multi_click_gap_s,
        write_max_gap_s=args.write_max_gap_s,
        terminate_status=status,
        button_map=None if args.no_remap_buttons else {"M1": "left", "M2": "right"},
    )
    doc = reduce_project(args.project_dir, output_path=args.output, params=params)
    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        stats = doc["stats"]
        print(f"Reduced {stats['n_raw_events']} raw events → {stats['n_actions']} actions "
              f"({stats['reduction_ratio']}:1)")
        for name, count in sorted(stats["action_histogram"].items(), key=lambda kv: -kv[1]):
            print(f"  {name:<12} {count}")
        print(f"Wrote {doc['output_path']}")


def run_view_actions(args: argparse.Namespace) -> None:
    from ..reduce.viewer import serve

    serve(args.project_dir, port=args.port, open_browser=not args.no_open)
