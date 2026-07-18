import { promises as fs } from "node:fs";
import path from "node:path";
import { NextResponse } from "next/server";

import { keystrokeJobPath, keystrokesPath } from "@/lib/paths";
import {
  isValidProjectId,
  requireSelection,
  runDirRelative,
  spawnCursorDetached,
} from "@/lib/python";

export const runtime = "nodejs";
export const maxDuration = 60;

type KeystrokeJobStatus = {
  state?: string;
  progress?: number;
  error?: string | null;
  n_samples?: number;
  n_events?: number;
  message?: string;
  updated_at?: number;
  fps?: number;
  range?: {
    start_t?: number;
    end_t?: number;
  };
  stats?: unknown;
};

async function readJsonIfExists(filePath: string): Promise<unknown | null> {
  try {
    const text = await fs.readFile(filePath, "utf8");
    return JSON.parse(text);
  } catch {
    return null;
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

  const job = (await readJsonIfExists(keystrokeJobPath(id))) as KeystrokeJobStatus | null;
  const artifact = (await readJsonIfExists(keystrokesPath(id))) as {
    events?: unknown[];
    meta?: unknown;
  } | null;

  return NextResponse.json({
    ok: true,
    run_id: id,
    job: job,
    events: artifact?.events ?? [],
    meta: artifact?.meta ?? null,
    ready: Array.isArray(artifact?.events),
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
      { error: "Save a selection before running keyboard extraction" },
      { status: 400 },
    );
  }

  const existing = (await readJsonIfExists(keystrokeJobPath(id))) as KeystrokeJobStatus | null;
  if (existing?.state === "running" || existing?.state === "starting" || existing?.state === "detecting") {
    return NextResponse.json({
      ok: true,
      run_id: id,
      started: false,
      already_running: true,
      job: existing,
    });
  }

  await fs.mkdir(path.dirname(keystrokeJobPath(id)), { recursive: true });
  await fs.writeFile(
    keystrokeJobPath(id),
    JSON.stringify(
      {
        state: "starting",
        progress: 0,
        error: null,
        n_samples: 0,
        n_events: 0,
        message: "Starting keystroke job…",
        updated_at: Date.now() / 1000,
      },
      null,
      2,
    ) + "\n",
    "utf8",
  );

  const { pid } = spawnCursorDetached([
    "extract-keystrokes-async",
    runDirRelative(id),
    "--json",
  ]);

  return NextResponse.json({
    ok: true,
    run_id: id,
    started: true,
    pid: pid ?? null,
    message: "Keyboard extraction started",
  });
}
