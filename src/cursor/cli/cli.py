"""Command-line entry point for cursor extraction and Workflow sample tools."""

from __future__ import annotations

import argparse
import sys

from .cli_handlers import (
    run_dump_frame,
    run_extract_cursor,
    run_extract_intent,
    run_extract_intent_async,
    run_extract_keystrokes,
    run_extract_keystrokes_async,
    run_pipeline_cmd,
    run_reduce_actions,
    run_stub_workflow,
    run_view_actions,
)

_DEFAULT_CURSOR_MODEL = "artifacts/models/cursor/weights/best.pt"


def _add_run_dir(parser: argparse.ArgumentParser, help_text: str) -> None:
    parser.add_argument("run_dir", help=help_text)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else None

    commands = {
        "stub-workflow",
        "extract-intent",
        "extract-intent-async",
        "extract-keystrokes",
        "extract-keystrokes-async",
        "extract-cursor",
        "run-pipeline",
        "dump-frame",
        "reduce-actions",
        "view-actions",
    }

    if cmd is None or cmd in {"-h", "--help"} or cmd not in commands:
        parser = argparse.ArgumentParser(
            prog="cursor",
            description=__doc__,
        )
        parser.add_argument(
            "command",
            nargs="?",
            help=(
                "stub-workflow | extract-intent | extract-intent-async | "
                "extract-keystrokes | extract-keystrokes-async | "
                "extract-cursor | run-pipeline | dump-frame | reduce-actions | view-actions"
            ),
        )
        parser.print_help()
        if cmd is not None and cmd not in {"-h", "--help"} and cmd not in commands:
            print(f"\nUnknown command: {cmd}", file=sys.stderr)
            raise SystemExit(2)
        return

    if cmd == "stub-workflow":
        parser = argparse.ArgumentParser(
            prog="cursor stub-workflow",
            description="Write an empty Workflow sample from an existing selection",
        )
        _add_run_dir(parser, "Processing run directory with selection.json")
        run_stub_workflow(parser.parse_args(argv[1:]))
        return

    if cmd == "extract-intent":
        parser = argparse.ArgumentParser(
            prog="cursor extract-intent",
            description="ASR + summary + Action–Intent pairs via OpenAI API",
        )
        _add_run_dir(parser, "Processing run directory with selection.json")
        parser.add_argument(
            "--chunk-s",
            type=int,
            default=600,
            help="Audio chunk length in seconds (default 600)",
        )
        parser.add_argument("--asr-model", default=None, help="ASR model (default whisper-1)")
        run_extract_intent(parser.parse_args(argv[1:]))
        return

    if cmd == "extract-intent-async":
        parser = argparse.ArgumentParser(
            prog="cursor extract-intent-async",
            description="Async Intent job with intent_job.json progress",
        )
        _add_run_dir(parser, "Processing run directory with selection.json")
        parser.add_argument("--chunk-s", type=int, default=600)
        parser.add_argument("--asr-model", default=None)
        parser.add_argument("--json", action="store_true")
        run_extract_intent_async(parser.parse_args(argv[1:]))
        return

    if cmd == "extract-keystrokes":
        parser = argparse.ArgumentParser(
            prog="cursor extract-keystrokes",
            description="Recover Keystrokes and write keystrokes.json",
        )
        _add_run_dir(parser, "Processing run directory with selection.json")
        parser.add_argument("--stride", type=int, default=1, help="Must be 1")
        parser.add_argument("--layout", default="tootalltoby.json")
        run_extract_keystrokes(parser.parse_args(argv[1:]))
        return

    if cmd == "extract-keystrokes-async":
        parser = argparse.ArgumentParser(
            prog="cursor extract-keystrokes-async",
            description="Async Keystroke job with keystroke_job.json progress",
        )
        _add_run_dir(parser, "Processing run directory with selection.json")
        parser.add_argument("--layout", default="tootalltoby.json")
        parser.add_argument("--json", action="store_true")
        run_extract_keystrokes_async(parser.parse_args(argv[1:]))
        return

    if cmd == "extract-cursor":
        parser = argparse.ArgumentParser(
            prog="cursor extract-cursor",
            description="Run YOLO over Crop ROI; write cursor_events.jsonl",
        )
        _add_run_dir(parser, "Processing run directory with selection.json")
        parser.add_argument("--model", type=str, default=_DEFAULT_CURSOR_MODEL)
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Raw cursor JSONL output path (default: cursor/cursor_events.jsonl)",
        )
        run_extract_cursor(parser.parse_args(argv[1:]))
        return

    if cmd == "dump-frame":
        parser = argparse.ArgumentParser(
            prog="cursor dump-frame",
            description=(
                "Write one frame as JPEG to stdout using the same OpenCV frame "
                "indexing as annotation saving and YOLO dataset export"
            ),
        )
        parser.add_argument("video", help="Path to the video file")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--frame", type=int, default=None, help="Frame number")
        group.add_argument(
            "--time",
            type=float,
            default=None,
            help="Timestamp in seconds (rounded to the nearest frame)",
        )
        run_dump_frame(parser.parse_args(argv[1:]))
        return

    if cmd == "run-pipeline":
        parser = argparse.ArgumentParser(
            prog="cursor run-pipeline",
            description="Run full Processing run and assemble workflow_sample.json",
        )
        _add_run_dir(parser, "Processing run directory with selection.json")
        parser.add_argument("--skip-existing", action="store_true")
        parser.add_argument("--json", action="store_true")
        run_pipeline_cmd(parser.parse_args(argv[1:]))
        return

    if cmd == "reduce-actions":
        parser = argparse.ArgumentParser(
            prog="cursor reduce-actions",
            description=(
                "Reduce extracted event streams into OpenCUA/AgentNet-style "
                "pyautogui actions (arXiv:2508.09123 Section 2.2). Consumes "
                "already-extracted artifacts only — never the video."
            ),
        )
        parser.add_argument(
            "project_dir",
            help="Published data/<id> directory (final_*) or a processing run directory",
        )
        parser.add_argument(
            "--output",
            default=None,
            help="Output JSON path (default: <project_dir>/actions/final_actions_opencua.json)",
        )
        parser.add_argument("--drag-min-px", type=float, default=12.0)
        parser.add_argument("--multi-click-gap-s", type=float, default=0.4)
        parser.add_argument("--write-max-gap-s", type=float, default=2.0)
        parser.add_argument(
            "--terminate-status",
            default="success",
            choices=["success", "failure", "none"],
            help="Status of the appended terminate action ('none' disables it)",
        )
        parser.add_argument(
            "--no-remap-buttons",
            action="store_true",
            help="Trust the button field of extracted mouse events as-is "
                 "(default remaps M1->left / M2->right via source_key, correcting "
                 "artifacts extracted with the previously inverted mapping)",
        )
        parser.add_argument("--json", action="store_true", help="Print full result JSON")
        run_reduce_actions(parser.parse_args(argv[1:]))
        return

    if cmd == "view-actions":
        parser = argparse.ArgumentParser(
            prog="cursor view-actions",
            description=(
                "Serve a local viewer that plays final_video.mp4 with the "
                "reduced OpenCUA actions overlaid (clicks, drags, keycast)"
            ),
        )
        parser.add_argument(
            "project_dir",
            help="Published data/<id> directory containing final_video.mp4 and "
                 "actions/final_actions_opencua.json",
        )
        parser.add_argument("--port", type=int, default=8899)
        parser.add_argument("--no-open", action="store_true",
                            help="Do not open the browser automatically")
        run_view_actions(parser.parse_args(argv[1:]))
        return
