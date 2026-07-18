"""CLI command handlers (kept separate from argparse wiring)."""

from __future__ import annotations

import argparse
import json
import sys

from ..detector.cursor_events import extract_cursor_events
from ..intent.intent import extract_intent
from ..intent.intent_jobs import run_intent_job
from ..keypress.keystrokes import extract_keystrokes, run_keystroke_job
from ..workflow.pipeline import PipelineError, run_pipeline
from ..workflow.workflow import write_stub_workflow_sample


def run_stub_workflow(args: argparse.Namespace) -> None:
    out_path = write_stub_workflow_sample(args.run_dir)
    print(f"Wrote stub Workflow sample to {out_path}")


def run_extract_intent(args: argparse.Namespace) -> None:
    paths = extract_intent(
        args.run_dir,
        chunk_s=args.chunk_s,
        asr_model=getattr(args, "asr_model", None),
    )
    for name, path in paths.items():
        print(f"Wrote {name} → {path}")


def run_extract_intent_async(args: argparse.Namespace) -> None:
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
    out_path = extract_keystrokes(
        args.run_dir,
        stride=args.stride,
        layout_name=args.layout,
    )
    print(f"Wrote Keystroke Raw events to {out_path}")


def run_extract_keystrokes_async(args: argparse.Namespace) -> None:
    result = run_keystroke_job(args.run_dir, layout_name=args.layout)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(
            f"Keystroke job {result.get('state')}: "
            f"{result.get('n_events', 0)} events → {result.get('path', '')}"
        )


def run_extract_cursor(args: argparse.Namespace) -> None:
    out_path = extract_cursor_events(args.run_dir, model_path=args.model)
    print(f"Wrote Cursor observations to {out_path}")


def run_pipeline_cmd(args: argparse.Namespace) -> None:
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
