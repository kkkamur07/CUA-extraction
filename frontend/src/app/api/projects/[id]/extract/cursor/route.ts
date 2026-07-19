import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";

import {
  cursorFilterArgs,
  loadCursorFilter,
  normalizeCursorFilter,
  saveCursorFilter,
} from "@/lib/cursorFilter";
import { getCursorWeightsStatus } from "@/lib/cursorConfig";
import { cursorEventsPath, rawCursorEventsPath } from "@/lib/paths";
import type { CursorFilterCriteria } from "@/lib/types";
import {
  isValidProjectId,
  requireSelection,
  runCursor,
  runPythonScript,
  runDirRelative,
} from "@/lib/python";

export const runtime = "nodejs";
export const maxDuration = 1800;

async function loadCursorEvents(id: string) {
  try {
    const text = await fs.readFile(cursorEventsPath(id), "utf8");
    return text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  } catch {
    return [];
  }
}

async function rawExists(id: string): Promise<boolean> {
  try {
    await fs.access(rawCursorEventsPath(id));
    return true;
  } catch {
    return false;
  }
}

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  if (!isValidProjectId(id)) {
    return NextResponse.json({ error: "Invalid project id" }, { status: 400 });
  }

  const [events, weights, filter, hasRaw] = await Promise.all([
    loadCursorEvents(id),
    getCursorWeightsStatus(),
    loadCursorFilter(id),
    rawExists(id),
  ]);

  return NextResponse.json({
    ok: true,
    run_id: id,
    events,
    weights,
    filter,
    has_raw: hasRaw,
    ready: events.length > 0,
  });
}

export async function POST(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  if (!isValidProjectId(id)) {
    return NextResponse.json({ error: "Invalid project id" }, { status: 400 });
  }

  try {
    await requireSelection(id);
  } catch {
    return NextResponse.json(
      { error: "Save a selection before running cursor extraction" },
      { status: 400 },
    );
  }

  let body: Record<string, unknown> = {};
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    body = {};
  }

  const filterOnly = Boolean(body.filter_only);
  const savedFilter = await loadCursorFilter(id);
  const filter: CursorFilterCriteria = normalizeCursorFilter({
    ...savedFilter,
    ...body,
  });
  await saveCursorFilter(id, filter);

  const runDir = runDirRelative(id);
  const rawRelative = path.join(runDir, "cursor", "raw_cursor_events.jsonl");
  const filteredRelative = path.join(
    runDir,
    "trace",
    "cursor",
    "cursor_events.jsonl",
  );

  if (!filterOnly) {
    const weights = await getCursorWeightsStatus();
    if (!weights.found) {
      return NextResponse.json(
        {
          ok: false,
          run_id: id,
          weights,
          filter,
          error:
            `YOLO weights not found at ${weights.path}. ` +
            "Train first: .venv/bin/python scripts/train_yolo.py --selection runs/<id>/selection.json",
        },
        { status: 400 },
      );
    }

    const extraction = await runCursor([
      "extract-cursor",
      runDir,
      "--output",
      rawRelative,
    ]);

    if (extraction.code !== 0) {
      return NextResponse.json(
        {
          ok: false,
          run_id: id,
          weights,
          filter,
          error:
            extraction.stderr.trim() ||
            extraction.stdout.trim() ||
            `extract-cursor exited with code ${extraction.code}`,
          stderr: extraction.stderr.trim() || undefined,
        },
        { status: 500 },
      );
    }
  } else if (!(await rawExists(id))) {
    return NextResponse.json(
      {
        ok: false,
        run_id: id,
        filter,
        error: "No raw cursor events yet. Run full cursor extraction first.",
      },
      { status: 400 },
    );
  }

  const filtering = await runPythonScript("scripts/filter_cursor_events.py", [
    "--input",
    rawRelative,
    "--output",
    filteredRelative,
    ...cursorFilterArgs(filter),
  ]);
  if (filtering.code !== 0) {
    return NextResponse.json(
      {
        ok: false,
        run_id: id,
        filter,
        error:
          filtering.stderr.trim() ||
          filtering.stdout.trim() ||
          `cursor filtering exited with code ${filtering.code}`,
        stderr: filtering.stderr.trim() || undefined,
      },
      { status: 500 },
    );
  }

  const [events, weights] = await Promise.all([
    loadCursorEvents(id),
    getCursorWeightsStatus(),
  ]);
  return NextResponse.json({
    ok: true,
    run_id: id,
    events,
    weights,
    filter,
    has_raw: true,
    message:
      filtering.stdout.trim() ||
      `Wrote ${events.length} filtered cursor events`,
  });
}
