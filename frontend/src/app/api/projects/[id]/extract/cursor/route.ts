import { promises as fs } from "node:fs";
import { NextResponse } from "next/server";

import { getCursorWeightsStatus } from "@/lib/cursorConfig";
import { cursorEventsPath } from "@/lib/paths";
import {
  isValidProjectId,
  requireSelection,
  runCursor,
  runDirRelative,
} from "@/lib/python";

export const runtime = "nodejs";
export const maxDuration = 60 * 30;

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

export async function GET(
  _request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  if (!isValidProjectId(id)) {
    return NextResponse.json({ error: "Invalid project id" }, { status: 400 });
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
    ready: events.length > 0,
  });
}

export async function POST(
  _request: Request,
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

  const weights = await getCursorWeightsStatus();
  if (!weights.found) {
    return NextResponse.json(
      {
        ok: false,
        run_id: id,
        weights,
        error:
          `YOLO weights not found at ${weights.path}. ` +
          "Train first: .venv/bin/python scripts/train_yolo.py --selection runs/<id>/selection.json",
      },
      { status: 400 },
    );
  }

  const { code, stdout, stderr } = await runCursor([
    "extract-cursor",
    runDirRelative(id),
  ]);

  if (code !== 0) {
    return NextResponse.json(
      {
        ok: false,
        run_id: id,
        weights,
        error: stderr.trim() || stdout.trim() || `extract-cursor exited with code ${code}`,
        stderr: stderr.trim() || undefined,
      },
      { status: 500 },
    );
  }

  const events = await loadCursorEvents(id);
  return NextResponse.json({
    ok: true,
    run_id: id,
    events,
    weights,
    message: stdout.trim() || `Wrote ${events.length} cursor events`,
  });
}
